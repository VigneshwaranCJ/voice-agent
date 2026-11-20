"""Builds the per-turn context: business + customer + conversation. Only what the turn needs."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.state import ConversationState
from app.industries.registry import get_industry
from app.knowledge.retrieval import search
from app.models import Agent, AgentConfiguration, BusinessProfile, Customer

LANG_NAMES = {"en-IN": "English", "ta-IN": "Tamil", "hi-IN": "Hindi", "te-IN": "Telugu", "kn-IN": "Kannada",
              "ml-IN": "Malayalam", "bn-IN": "Bengali", "mr-IN": "Marathi", "gu-IN": "Gujarati",
              "pa-IN": "Punjabi", "od-IN": "Odia"}

VOICE_STYLE = """Voice style (you are speaking on a phone/voice call, not writing):
- Sound like a warm, calm, patient customer-care executive. Gentle and respectful, never pushy or over-excited.
- Keep replies short: 1-2 sentences (max ~35 words). Ask one question at a time.
- No markdown, lists, emojis, URLs or symbols. Write numbers the way they are spoken.
- Don't repeat greetings or the caller's words back unnecessarily. Vary your phrasing.
- If you didn't understand, politely ask the caller to repeat."""


@dataclass
class AgentBundle:
    agent: Agent
    config: AgentConfiguration
    profile: BusinessProfile | None


async def load_agent_bundle(db: AsyncSession, agent_id: str, tenant_id: str | None = None) -> AgentBundle | None:
    q = select(Agent).where(Agent.id == agent_id, Agent.is_active.is_(True))
    if tenant_id:
        q = q.where(Agent.tenant_id == tenant_id)
    agent = (await db.execute(q)).unique().scalar_one_or_none()
    if not agent:
        return None
    cfg = (await db.execute(select(AgentConfiguration).where(
        AgentConfiguration.agent_id == agent.id, AgentConfiguration.tenant_id == agent.tenant_id,
        AgentConfiguration.is_active.is_(True)).order_by(AgentConfiguration.version.desc()))).scalars().first()
    if not cfg:
        return None
    profile = (await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == agent.tenant_id))).scalar_one_or_none()
    # Detach: the bundle lives for the whole call, and a rollback (e.g. after a failed tool) would otherwise
    # expire these objects and force a lazy reload outside the async context.
    for obj in (agent, cfg, profile):
        if obj is not None and obj in db:
            db.expunge(obj)
    return AgentBundle(agent, cfg, profile)


def reply_language_instruction(lang: str) -> str:
    name = LANG_NAMES.get(lang, lang)
    if lang == "en-IN":
        return ("LANGUAGE: The caller is speaking English right now. Reply ONLY in simple Indian English, even if "
                "earlier turns were in another language.")
    return (f"LANGUAGE: The caller is speaking {name} right now. Reply in {name}, written in {name} script, even if "
            f"earlier turns were in English. Natural code-mixing is fine (keep common English words like "
            f"'appointment', 'BHK', 'doctor' in Latin script) — speak the way people actually talk, not formal "
            f"literary {name}.")


class ContextManager:
    def __init__(self, db: AsyncSession, bundle: AgentBundle):
        self.db, self.bundle = db, bundle

    @property
    def tz(self) -> str:
        return self.bundle.profile.timezone if self.bundle.profile else "Asia/Kolkata"

    def business_context(self) -> str:
        p = self.bundle.profile
        if not p:
            return ""
        lines = [f"Business: {p.display_name}. {p.description}".strip()]
        if p.operating_hours:
            lines.append("Hours: " + "; ".join(f"{k}: {v}" for k, v in p.operating_hours.items()))
        if p.locations:
            lines.append("Locations: " + "; ".join(
                loc.get("address", str(loc)) if isinstance(loc, dict) else str(loc) for loc in p.locations))
        if p.phone:
            lines.append(f"Phone: {p.phone}")
        if p.services:
            lines.append("Services: " + ", ".join(map(str, p.services)))
        return "\n".join(lines)

    async def customer_context(self, state: ConversationState) -> str:
        if not state.customer_id:
            return "Caller not identified yet. Ask for their mobile number only when needed for an action."
        c = (await self.db.execute(select(Customer).where(
            Customer.tenant_id == state.tenant_id, Customer.id == state.customer_id))).scalar_one_or_none()
        if not c:
            return ""
        # Identified by phone only (unverified): never put stored PII into the prompt.
        return ("Caller gave a mobile number (NOT verified). Do not reveal stored details about them; "
                "use only what they tell you in this call.")

    async def knowledge_context(self, state: ConversationState, user_text: str) -> str:
        hits = await search(self.db, tenant_id=state.tenant_id, agent_id=state.agent_id, query=user_text, k=2)
        hits = [h for h in hits if h.score > 1.0]
        if not hits:
            return ""
        return "Possibly relevant knowledge (use only if it answers the question):\n" + "\n---\n".join(
            f"[{h.title}] {h.content[:600]}" for h in hits)

    async def system_prompt(self, state: ConversationState, user_text: str) -> str:
        cfg, agent = self.bundle.config, self.bundle.agent
        industry = get_industry(agent.industry)
        now = datetime.now(ZoneInfo(self.tz))
        parts = [
            f"You are {cfg.persona_name}, the customer care voice assistant for "
            f"{self.bundle.profile.display_name if self.bundle.profile else 'this business'}.",
            cfg.personality.strip(),
            VOICE_STYLE,
            "Grounding rules: never invent availability, prices, schedules, bookings or customer details. Use tools "
            "for facts; if a tool fails or returns nothing, say so honestly and offer an alternative or a human. "
            "Confirm before any booking, cancellation or change.",
            industry.default_instructions,
            cfg.system_instructions.strip(),
            f"Current date/time: {now.strftime('%A %d %B %Y, %I:%M %p')} ({self.tz}). Resolve 'today', "
            f"'tomorrow', weekday names to YYYY-MM-DD.",
            "## Business context\n" + self.business_context(),
            "## Caller\n" + await self.customer_context(state),
        ]
        if state.collected:
            parts.append(f"Already collected this call: {state.collected}")
        kb = await self.knowledge_context(state, user_text)
        if kb:
            parts.append(kb)
        parts.append(reply_language_instruction(state.language))
        return "\n\n".join(p for p in parts if p)
