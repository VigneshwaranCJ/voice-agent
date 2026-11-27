"""Post-call analyst agent: sentiment, outcome, summary and follow-ups for one ended conversation.

The agent loop, in order:

1. **Gather evidence** (deterministic, tenant-scoped): the transcript, the tools the voice/chat agent ran, any
   escalations, and how the conversation ended.
2. **Reason**: the LLM reads the evidence and must hand in its findings through one tool, ``submit_analysis``, whose
   arguments are validated by a Pydantic schema.
3. **Self-correct**: if the submission is missing or invalid, the validation error goes back to the model and it tries
   again, up to ``MAX_ATTEMPTS`` times.
4. **Verify**: recorded facts beat the model's opinion. Quotes that aren't in the caller's words are dropped, a
   "booked" or "lead captured" outcome needs a successful tool run that did it, and an escalated conversation is
   reported as escalated. Each correction is kept in ``checks`` so people can see what was changed.
5. **Act**: save the analysis, fill the conversation's summary (and ``resolved`` when nothing else set it), and open a
   follow-up for the team when a person needs to call back and none is open yet.

Industry-agnostic: it only reads tool names and their registry flags, never industry tables.
"""

import asyncio
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.llm.base import LLMResponse
from app.llm.sarvam import SarvamLLM, get_llm
from app.models import (
    AnalyticsEvent, CallSession, Conversation, ConversationAnalysis, ConversationMessage, EscalationRecord,
    ToolExecution,
)
from app.notifications.email import escalation_alert
from app.sarvam.client import SarvamError
from app.tools.registry import get_tool

MAX_ATTEMPTS = 3
MAX_MESSAGES = 80  # the latest messages of very long calls
MAX_CHARS_PER_MESSAGE = 1000
SUBMIT = "submit_analysis"

Sentiment = Literal["positive", "neutral", "negative", "mixed"]
Outcome = Literal["resolved", "booked", "lead_captured", "information_only", "escalated", "unresolved", "abandoned"]
Priority = Literal["low", "normal", "high"]


class FollowUp(BaseModel):
    action: str = Field(min_length=3, max_length=300, description="One concrete next step for the business's team.")
    priority: Priority = "normal"


class AnalysisIn(BaseModel):
    """What the analyst must submit. Field descriptions double as instructions to the model."""

    summary: str = Field(min_length=10, max_length=1200, description=(
        "2-3 sentences in English for a human executive: what the caller needed, what was done (bookings, leads, "
        "answers), and anything still pending."))
    sentiment: Sentiment = Field(description="The caller's overall feeling across the whole conversation.")
    sentiment_score: float = Field(ge=-1, le=1, description="-1 very negative, 0 neutral, 1 very positive.")
    sentiment_trend: Literal["improving", "steady", "worsening"] = Field(
        description="How the caller's mood moved from the start of the call to the end.")
    emotions: list[str] = Field(default_factory=list, max_length=5, description=(
        "Up to 5 single-word emotions the caller showed, e.g. frustrated, relieved, anxious, satisfied."))
    outcome: Outcome = Field(description=(
        "resolved: question answered or problem solved. booked: an appointment/visit was booked. lead_captured: "
        "contact details saved for follow-up. information_only: caller got information, nothing else needed. "
        "escalated: handed to a person. unresolved: caller's need was not met. abandoned: caller left early."))
    resolved: bool = Field(description="True if the caller's main need was met by the end of the conversation.")
    topics: list[str] = Field(default_factory=list, max_length=6, description="Short topics, e.g. 'pricing', 'refund'.")
    key_quotes: list[str] = Field(default_factory=list, max_length=3, description=(
        "Up to 3 short phrases copied exactly from the CALLER's messages (original language) that show their "
        "sentiment. Never paraphrase; never quote the assistant."))
    needs_human: bool = Field(description=(
        "True only if a person from the business should contact the caller (complaint, unmet request, promise "
        "made, risk). False if the call was handled fully."))
    follow_ups: list[FollowUp] = Field(default_factory=list, max_length=5, description="Next steps for the team.")
    agent_issues: list[str] = Field(default_factory=list, max_length=5, description=(
        "Where the AI agent fell short (wrong info, ignored a question, robotic, wrong language). Empty if none."))

    @field_validator("emotions", "topics", "agent_issues")
    @classmethod
    def _clean_words(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            s = " ".join(str(item).split())[:80]
            if s and s.lower() not in (o.lower() for o in out):
                out.append(s)
        return out

    @field_validator("key_quotes")
    @classmethod
    def _clean_quotes(cls, v: list[str]) -> list[str]:
        return [" ".join(str(q).split())[:200] for q in v if str(q).strip()]


SYSTEM = """You are a customer-care quality analyst. You review ONE finished conversation between a business's AI \
agent and a caller, and report your findings by calling the `submit_analysis` tool exactly once.

Rules:
- Judge the CALLER's sentiment, not the agent's tone. Polite but unhappy callers are negative.
- Base every finding on the evidence given. Do not invent bookings, names, prices or promises.
- Tool runs show what the agent actually did; a booking only happened if a booking tool ran successfully.
- The transcript may be in Tamil, Hindi, English or a mix. Write the summary, topics and follow-ups in English, \
but copy key quotes exactly in the caller's original words.
- Do not include phone numbers or other personal details in the summary or follow-ups.
- Respond only by calling `submit_analysis`."""


def _inline_refs(schema: dict) -> dict:
    """Pydantic puts nested models under $defs; tool-calling APIs are happier with one self-contained schema."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return walk(dict(defs[ref.rsplit("/", 1)[1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def submit_tool() -> dict:
    return {"type": "function", "function": {
        "name": SUBMIT, "description": "Hand in the finished analysis of the conversation.",
        "parameters": _inline_refs(AnalysisIn.model_json_schema())}}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’.,!?;:()\[\]…-]", " ", text.lower())).strip()


class Evidence:
    """Everything the analyst may look at, loaded with the conversation's tenant_id only."""

    def __init__(self, conv: Conversation, messages: list[ConversationMessage], tools: list[ToolExecution],
                 escalations: list[EscalationRecord], call: CallSession | None):
        self.conv, self.messages, self.tools, self.escalations, self.call = conv, messages, tools, escalations, call
        self.caller_lines = [m.content for m in messages if m.role == "user" and m.content]

    @classmethod
    async def load(cls, db: AsyncSession, tenant_id: str, conversation_id: str) -> "Evidence | None":
        conv = (await db.execute(select(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.id == conversation_id))).scalar_one_or_none()
        if not conv:
            return None
        msgs = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.tenant_id == tenant_id, ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role.in_(("user", "assistant"))).order_by(ConversationMessage.created_at))).scalars().all()
        tools = (await db.execute(select(ToolExecution).where(
            ToolExecution.tenant_id == tenant_id, ToolExecution.conversation_id == conversation_id)
            .order_by(ToolExecution.created_at))).scalars().all()
        escs = (await db.execute(select(EscalationRecord).where(
            EscalationRecord.tenant_id == tenant_id, EscalationRecord.conversation_id == conversation_id))).scalars().all()
        call = (await db.execute(select(CallSession).where(
            CallSession.tenant_id == tenant_id, CallSession.conversation_id == conversation_id))).scalars().first()
        return cls(conv, list(msgs), list(tools), list(escs), call)

    def successful_tools(self, *, booking: bool = False) -> list[str]:
        names = []
        for t in self.tools:
            spec = get_tool(t.tool_name)
            ok = t.status == "success" and (not isinstance(t.result, dict) or t.result.get("ok", True) is not False)
            if ok and spec and (spec.requires_confirmation if booking else spec.is_write):
                names.append(t.tool_name)
        return names

    def brief(self) -> str:
        lines = [f"Channel: {self.conv.channel}. Recorded status: {self.conv.status}."]
        if self.call and self.call.duration_seconds:
            lines.append(f"Call length: {round(self.call.duration_seconds)} seconds.")
        lines.append("\nTranscript (oldest first):")
        for m in self.messages[-MAX_MESSAGES:]:
            who = "CALLER" if m.role == "user" else "AGENT"
            lines.append(f"{who}: {' '.join(m.content.split())[:MAX_CHARS_PER_MESSAGE]}")
        lines.append("\nTools the agent ran:")
        lines += [f"- {t.tool_name}: {t.status}" + (f" ({t.error[:120]})" if t.error else "") for t in self.tools] or ["- none"]
        lines.append("\nEscalations to a person:")
        lines += [f"- {e.reason} ({e.priority}): {e.summary[:200]}" for e in self.escalations] or ["- none"]
        return "\n".join(lines)


def _extract(resp: LLMResponse) -> tuple[dict | None, str | None, str]:
    """(arguments, tool_call_id, problem). Accepts the submit_analysis call, or plain JSON content as a fallback."""
    for c in resp.tool_calls:
        if c.name == SUBMIT:
            try:
                args = json.loads(c.arguments or "{}")
            except json.JSONDecodeError as e:
                return None, c.id, f"The arguments were not valid JSON ({e.msg})."
            return (args, c.id, "") if isinstance(args, dict) else (None, c.id, "The arguments must be a JSON object.")
    if resp.tool_calls:
        return None, resp.tool_calls[0].id, f"Unknown tool {resp.tool_calls[0].name!r}; call {SUBMIT} instead."
    m = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
    if m:
        try:
            args = json.loads(m.group(0))
            if isinstance(args, dict):
                return args, None, ""
        except json.JSONDecodeError:
            pass
    return None, None, f"No analysis was submitted. Call {SUBMIT} with the full analysis."


def _errors(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in err['loc']) or 'body'}: {err['msg']}" for err in e.errors()[:8])


async def _reason(llm, evidence: Evidence) -> tuple[AnalysisIn | None, int, str | None]:
    """The reason → validate → self-correct loop. Returns (analysis, attempts, last problem)."""
    settings = get_settings()
    tools = [submit_tool()]
    messages: list[dict] = [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": evidence.brief()}]
    problem: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = await asyncio.wait_for(
            llm.complete(messages, tools=tools, temperature=0.1, max_tokens=900),
            timeout=settings.llm_timeout_seconds)
        args, call_id, problem = _extract(resp)
        if args is not None:
            try:
                return AnalysisIn.model_validate(args), attempt, None
            except ValidationError as e:
                problem = f"The analysis was rejected: {_errors(e)}. Fix these fields and call {SUBMIT} again."
        # Feed the problem back. Sarvam needs `tools` whenever tool messages are present; we always send them.
        messages.append(resp.assistant_message())
        if call_id:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps({"ok": False, "error": problem})})
        else:
            messages.append({"role": "user", "content": problem})
    return None, MAX_ATTEMPTS, problem


def _verify(a: AnalysisIn, ev: Evidence) -> list[str]:
    """Correct the model's answer where recorded facts disagree. Returns what was changed."""
    checks: list[str] = []
    said = _norm(" \n ".join(ev.caller_lines))
    kept = [q for q in a.key_quotes if _norm(q) and _norm(q) in said]
    if len(kept) != len(a.key_quotes):
        checks.append(f"Dropped {len(a.key_quotes) - len(kept)} quote(s) not found in the caller's words.")
        a.key_quotes = kept
    if ev.conv.status == "escalated" or ev.escalations:
        if a.outcome != "escalated":
            checks.append(f"Outcome changed from {a.outcome} to escalated: the conversation was handed to a person.")
            a.outcome = "escalated"
    elif a.outcome == "booked" and not ev.successful_tools(booking=True):
        checks.append("Outcome changed from booked: no booking tool succeeded in this conversation.")
        a.outcome, a.resolved = "unresolved", False
    elif a.outcome == "lead_captured" and not ev.successful_tools():
        checks.append("Outcome changed from lead_captured: no tool saved the caller's details.")
        a.outcome, a.resolved = "unresolved", False
    if a.outcome in ("unresolved", "abandoned", "escalated") and a.resolved:
        checks.append(f"Marked not resolved: the outcome is {a.outcome}.")
        a.resolved = False
    if a.sentiment == "positive" and a.sentiment_score < 0 or a.sentiment == "negative" and a.sentiment_score > 0:
        checks.append("Score sign didn't match the sentiment label; set to 0.")
        a.sentiment_score = 0.0
    return checks


async def _open_follow_up(db: AsyncSession, ev: Evidence, a: AnalysisIn) -> EscalationRecord | None:
    """A follow-up in the team's queue when a person should contact the caller and nothing is open for this call."""
    if not a.needs_human or not get_settings().analysis_auto_follow_up:
        return None
    if any(e.status in ("open", "assigned") for e in ev.escalations):
        return None
    priority = "high" if any(f.priority == "high" for f in a.follow_ups) or a.sentiment == "negative" else "normal"
    steps = "; ".join(f.action for f in a.follow_ups[:3])
    rec = EscalationRecord(tenant_id=ev.conv.tenant_id, conversation_id=ev.conv.id, reason="follow_up",
                           priority=priority, summary=(a.summary + (f" Next: {steps}" if steps else ""))[:1500],
                           context={"source": "post_call_analysis", "sentiment": a.sentiment,
                                    "language": ev.conv.language})
    db.add(rec)
    await db.flush()
    return rec


def _llm_ready(llm) -> bool:
    return not isinstance(llm, SarvamLLM) or get_settings().sarvam_configured


async def _row(db: AsyncSession, tenant_id: str, ev: Evidence) -> ConversationAnalysis:
    row = (await db.execute(select(ConversationAnalysis).where(
        ConversationAnalysis.tenant_id == tenant_id, ConversationAnalysis.conversation_id == ev.conv.id))).scalar_one_or_none()
    if not row:
        row = ConversationAnalysis(tenant_id=tenant_id, conversation_id=ev.conv.id, agent_id=ev.conv.agent_id)
        db.add(row)
    # A re-run starts clean: nothing from the previous run survives except the follow-up it opened.
    for name in ("sentiment", "sentiment_score", "sentiment_trend", "outcome", "resolved", "summary", "model", "error"):
        setattr(row, name, None)
    for name in ("emotions", "topics", "key_quotes", "follow_ups", "agent_issues", "checks"):
        setattr(row, name, [])
    row.needs_human, row.attempts = False, 0
    return row


async def analyse_conversation(db: AsyncSession, tenant_id: str, conversation_id: str, llm=None) -> ConversationAnalysis | None:
    """Run the analyst on one conversation and store the result. Never raises for model trouble: the row's
    ``status`` says what happened. Returns None only if the conversation isn't this tenant's."""
    ev = await Evidence.load(db, tenant_id, conversation_id)
    if not ev:
        return None
    row = await _row(db, tenant_id, ev)
    llm = llm or get_llm()
    alert: dict | None = None  # sent after the commit, so an email never describes a follow-up that wasn't saved
    if not ev.caller_lines:
        row.status, row.outcome, row.error = "skipped", "abandoned", "The caller said nothing, so there is nothing to analyse."
    elif not _llm_ready(llm):
        row.status, row.error = "not_configured", "Set SARVAM_API_KEY to analyse conversations."
    else:
        try:
            analysis, row.attempts, problem = await _reason(llm, ev)
        except Exception as e:  # the analysis is best-effort; the call itself is already saved
            analysis, problem = None, f"{type(e).__name__}: {e}"[:500]
            if isinstance(e, SarvamError) and e.status == 402:
                problem = "Sarvam account is out of credits."
        if analysis is None:
            row.status, row.error = "failed", problem
            log.warning("analysis_failed", conversation=conversation_id, error=problem)
        else:
            row.checks = _verify(analysis, ev)
            row.status, row.model = "done", get_settings().sarvam_llm_model if isinstance(llm, SarvamLLM) else type(llm).__name__
            row.sentiment, row.sentiment_score = analysis.sentiment, round(analysis.sentiment_score, 3)
            row.sentiment_trend, row.emotions = analysis.sentiment_trend, analysis.emotions
            row.outcome, row.resolved, row.summary = analysis.outcome, analysis.resolved, analysis.summary
            row.topics, row.key_quotes, row.agent_issues = analysis.topics, analysis.key_quotes, analysis.agent_issues
            row.follow_ups = [f.model_dump() for f in analysis.follow_ups]
            row.needs_human = analysis.needs_human
            ev.conv.summary = analysis.summary
            if ev.conv.resolved is None and ev.conv.status != "active":
                ev.conv.resolved = analysis.resolved
            if not row.escalation_id:  # a re-run never opens a second follow-up for the same call
                rec = await _open_follow_up(db, ev, analysis)
                if rec:
                    row.escalation_id = rec.id
                    alert = {"reason": rec.reason, "priority": rec.priority, "summary": rec.summary}
    db.add(AnalyticsEvent(tenant_id=tenant_id, agent_id=ev.conv.agent_id, conversation_id=ev.conv.id,
                          name="conversation_analysed", properties={"status": row.status, "sentiment": row.sentiment,
                                                                    "outcome": row.outcome}))
    await db.commit()
    if alert:
        escalation_alert(tenant_id, **alert)
    return row


def analysis_out(row: ConversationAnalysis | None) -> dict | None:
    if not row:
        return None
    return {"status": row.status, "sentiment": row.sentiment, "sentiment_score": row.sentiment_score,
            "sentiment_trend": row.sentiment_trend, "emotions": row.emotions, "outcome": row.outcome,
            "resolved": row.resolved, "summary": row.summary, "topics": row.topics, "key_quotes": row.key_quotes,
            "follow_ups": row.follow_ups, "needs_human": row.needs_human, "agent_issues": row.agent_issues,
            "checks": row.checks, "escalation_id": row.escalation_id, "attempts": row.attempts, "model": row.model,
            "error": row.error, "updated_at": row.updated_at}
