"""Shared agent engine: guardrails → context → LLM ⇄ tools → reply. No industry logic here."""

import asyncio
import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.context.langdetect import detect_script_language
from app.context.manager import AgentBundle, ContextManager, reply_language_instruction
from app.context.state import ConversationState, get_state_store
from app.core.config import get_settings
from app.core.logging import log
from app.industries.registry import get_industry
from app.llm.base import LLMResponse
from app.llm.sarvam import get_llm
from app.models import AnalyticsEvent, ConversationMessage
from app.orchestration.guardrails import FALLBACK_REPLY, UNRESOLVED_REPLY, human_request_guard, pick
from app.sarvam.client import SarvamError
from app.tools.common import create_escalation
from app.tools.registry import ToolContext, execute_tool, tools_for

DEFAULT_GREETING = {
    "en-IN": "Hello, thank you for calling {business}. This is {persona}. How may I help you today?",
    "ta-IN": "வணக்கம், {business}-க்கு அழைத்ததற்கு நன்றி. நான் {persona} பேசுகிறேன். உங்களுக்கு எப்படி உதவலாம்?",
    "hi-IN": "नमस्ते, {business} में कॉल करने के लिए धन्यवाद। मैं {persona} बोल रही हूँ। मैं आपकी क्या मदद कर सकती हूँ?",
}


@dataclass
class TurnResult:
    reply: str
    language: str
    events: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    escalated: bool = False


def greeting_for(bundle: AgentBundle, lang: str) -> str:
    business = bundle.profile.display_name if bundle.profile else ""
    tpl = bundle.config.greeting.get(lang) or DEFAULT_GREETING.get(lang) or DEFAULT_GREETING["en-IN"]
    return tpl.format(business=business, persona=bundle.config.persona_name)


def _trim(history: list[dict], n: int) -> list[dict]:
    h = history[-n:]
    while h and h[0].get("role") != "user":  # never start on a dangling tool/assistant message
        h = h[1:]
    return h


class AgentEngine:
    def __init__(self, db: AsyncSession, bundle: AgentBundle, llm=None):
        self.db, self.bundle = db, bundle
        self.llm = llm or get_llm()
        self.settings = get_settings()
        self.ctx_mgr = ContextManager(db, bundle)
        self.industry = get_industry(bundle.agent.industry)
        # Defence in depth: a stale config (e.g. saved before an industry change) can't enable another
        # industry's tools — only tools this industry offers are ever exposed.
        allowed = set(self.industry.default_tools)
        configured = [t for t in (bundle.config.enabled_tools or []) if t in allowed]
        self.enabled_tools = configured or list(self.industry.default_tools)

    def _set_language(self, state: ConversationState, detected: str | None) -> None:
        if detected and detected in (self.bundle.agent.languages or []) and detected != state.language:
            state.language = detected
        if state.language not in state.languages_used:
            state.languages_used.append(state.language)

    async def _record(self, state: ConversationState, role: str, content: str, **meta) -> None:
        self.db.add(ConversationMessage(tenant_id=state.tenant_id, conversation_id=state.conversation_id, role=role,
                                        content=content, language=state.language, meta=meta))

    async def record_greeting(self, state: ConversationState, text: str) -> None:
        state.history.append({"role": "assistant", "content": text})
        await self._record(state, "assistant", text, kind="greeting")
        await self.db.commit()
        await get_state_store().put(state)

    async def handle_turn(self, state: ConversationState, user_text: str, detected_language: str | None = None) -> TurnResult:
        """One caller turn (text chat and the website widget)."""
        # Typed text has no STT language; infer from script. Romanised Tamil (Tanglish) keeps the current language.
        if detected_language is None:
            hint = detect_script_language(user_text)
            if hint and hint != "en-IN":
                detected_language = hint
        self._set_language(state, detected_language)
        state.turn_count += 1
        state.history.append({"role": "user", "content": user_text})
        await self._record(state, "user", user_text)
        await self.db.commit()  # persist the caller's words before any tool can roll the session back
        tool_ctx = ToolContext(db=self.db, tenant_id=state.tenant_id, agent_id=state.agent_id, state=state,
                               business_timezone=self.ctx_mgr.tz)

        result = await self._guarded(state, user_text, tool_ctx)
        if result is None:
            result = await self._llm_turn(state, user_text, tool_ctx)

        state.history.append({"role": "assistant", "content": result.reply})
        state.history = _trim(state.history, self.settings.history_max_messages)
        await self._record(state, "assistant", result.reply, tool_calls=result.tool_calls)
        self.db.add(AnalyticsEvent(tenant_id=state.tenant_id, agent_id=state.agent_id,
                                   conversation_id=state.conversation_id, name="turn",
                                   properties={"language": state.language, "tools": [t["name"] for t in result.tool_calls],
                                               "escalated": result.escalated}))
        await self.db.commit()
        await get_state_store().put(state)
        result.events = tool_ctx.events
        result.escalated = state.escalated
        return result

    async def _guarded(self, state: ConversationState, text: str, tool_ctx: ToolContext) -> TurnResult | None:
        for guard in [*self.industry.guards, human_request_guard]:
            g = guard(text)
            if not g:
                continue
            if g.escalate_reason and not state.escalated:
                await create_escalation(tool_ctx, g.escalate_reason, f"Caller said: {text[:300]}", g.priority)
            log.info("guard_triggered", reason=g.escalate_reason, conversation=state.conversation_id)
            return TurnResult(reply=pick(g.reply, state.language), language=state.language)
        return None

    async def _ask(self, messages: list[dict], tools: list[dict] | None, opts: dict) -> LLMResponse:
        """One LLM round."""
        return await asyncio.wait_for(self.llm.complete(messages, tools=tools, **opts), timeout=self.settings.llm_timeout_seconds)

    async def _llm_turn(self, state: ConversationState, user_text: str, tool_ctx: ToolContext) -> TurnResult:
        system = await self.ctx_mgr.system_prompt(state, user_text)
        history = [dict(m) for m in _trim(state.history, self.settings.history_max_messages)]
        if history and history[-1].get("role") == "user":
            # Models follow the reply language far better when it sits next to the latest utterance.
            note = reply_language_instruction(state.language)
            history[-1]["content"] = f"{history[-1]['content']}\n\n({note})"
        messages = [{"role": "system", "content": system}, *history]
        tools = [t.openai_schema() for t in tools_for(self.enabled_tools)]
        executed: list[dict] = []
        opts = dict(self.bundle.config.llm_settings or {})

        def done(reply: str) -> TurnResult:
            return TurnResult(reply=reply, language=state.language, tool_calls=executed)

        try:
            for _ in range(self.settings.max_tool_rounds):
                resp = await self._ask(messages, tools or None, opts)
                if not resp.tool_calls:
                    if not resp.content:
                        raise ValueError("empty LLM response")
                    state.consecutive_failures = 0
                    return done(resp.content)
                messages.append(resp.assistant_message())
                for call in resp.tool_calls:
                    out = await execute_tool(tool_ctx, call.name, call.arguments, self.enabled_tools)
                    executed.append({"name": call.name, "ok": bool(out.get("ok"))})
                    if call.name not in state.intents:
                        state.intents.append(call.name)
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": json.dumps(out, ensure_ascii=False, default=str)})
            # Tool budget exhausted: force a final answer. Sarvam requires `tools` whenever tool messages
            # are present, so keep them and disable calling via tool_choice="none".
            resp = await self._ask(messages, tools or None, {**opts, "tool_choice": "none"})
            if resp.content:
                return done(resp.content)
            raise ValueError("no final answer")
        except Exception as e:
            log.warning("llm_turn_failed", error=str(e), error_type=type(e).__name__, conversation=state.conversation_id)
            if isinstance(e, SarvamError) and e.status in (401, 402, 403):
                tool_ctx.events.append({"type": "error", "message": f"Sarvam AI model refused the request: {e}"})
            state.consecutive_failures += 1
            if state.consecutive_failures >= 2 and not state.escalated:
                await create_escalation(tool_ctx, "unresolved", f"Assistant failed repeatedly. Last caller message: {user_text[:300]}")
                fallback = pick(UNRESOLVED_REPLY, state.language)
            else:
                fallback = pick(FALLBACK_REPLY, state.language)
            return done(fallback)
