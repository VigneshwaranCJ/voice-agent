"""Hosted Sarvam Voice Agents (Samvaad): link an agent, serve its tool calls, and mint call sessions.

Sarvam runs the call itself (speech in, LLM, speech out). This module gives it:

* a tool webhook, POST /sarvam/tools/{tool_name}, authenticated by a per-agent bearer token that Sarvam sends as a
  static header. The tenant and agent come from that token's link row, never from the body or the model;
* a session route the Sarvam browser SDK uses as its ``baseUrl``. It forwards the SDK's "signed URL" request to
  Sarvam with our server-side API key, so the key never reaches the browser, and the call's audio then flows
  between the browser and Sarvam directly (no WebSocket through our host).

Only read-only tools run here for now. Writes that need the caller's explicit yes (bookings) are refused: Sarvam's
tool call doesn't carry the caller's own words in a form we can check, and the model's word alone is not consent.
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.manager import load_agent_bundle
from app.context.state import ConversationState
from app.core.config import get_settings
from app.core.deps import DB, Principal, audit, tenant_admin_scope, tenant_scope
from app.core.logging import log
from app.core.timeutil import as_utc
from app.models import Agent, AnalyticsEvent, CallSession, Conversation, ConversationMessage, SarvamAgentLink
from app.orchestration.lifecycle import summarise
from app.security.crypto import new_token
from app.seed import LANGS
from app.tools.registry import ToolContext, execute_tool, get_tool

router = APIRouter(tags=["sarvam-agents"])

CHANNEL = "sarvam_voice"
_CONV_NS = uuid.UUID("6f1d3c52-8a0e-4b8e-9d2a-5a1f0c7e2b44")  # namespace for Sarvam interaction -> conversation ids


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LinkIn(BaseModel):
    org_id: str = Field(default="", max_length=100)
    workspace_id: str = Field(default="", max_length=100)
    app_id: str = Field(default="", max_length=100)
    enabled: bool = False


def effective_ids(link: SarvamAgentLink | None) -> tuple[str, str, str]:
    """(org, workspace, app) for a link: its own values, else the SARVAM_AGENTS_*_ID defaults."""
    s = get_settings()
    own = (link.org_id, link.workspace_id, link.app_id) if link else ("", "", "")
    defaults = (s.sarvam_agents_org_id, s.sarvam_agents_workspace_id, s.sarvam_agents_app_id)
    return tuple((v or (d or "")).strip() for v, d in zip(own, defaults, strict=True))  # type: ignore[return-value]


def _link_out(link: SarvamAgentLink | None, request: Request) -> dict:
    s = get_settings()
    tool_url = str(request.url_for("sarvam_tool", tool_name="TOOL_NAME"))
    org, ws, app = effective_ids(link)
    common = {"tool_url": tool_url, "effective": {"org_id": org, "workspace_id": ws, "app_id": app},
              "voice_configured": bool(s.sarvam_agents_api_key)}
    if not link:
        return {"linked": False, "org_id": "", "workspace_id": "", "app_id": "", "enabled": False,
                "has_token": False, **common}
    return {"linked": True, "org_id": link.org_id, "workspace_id": link.workspace_id, "app_id": link.app_id,
            "enabled": link.enabled, "has_token": bool(link.tool_token_hash), **common}


async def _own_agent(db: AsyncSession, agent_id: str, tenant_id: str) -> Agent:
    a = (await db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))).unique().scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Agent not found")
    return a


async def _link_for(db: AsyncSession, agent: Agent) -> SarvamAgentLink | None:
    return (await db.execute(select(SarvamAgentLink).where(
        SarvamAgentLink.agent_id == agent.id, SarvamAgentLink.tenant_id == agent.tenant_id))).scalar_one_or_none()


# ---- Management (dashboard) ---------------------------------------------------------------------------------------

@router.get("/agents/{agent_id}/sarvam")
async def get_link(agent_id: str, request: Request, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    agent = await _own_agent(db, agent_id, p.tenant_id)
    return _link_out(await _link_for(db, agent), request)


@router.put("/agents/{agent_id}/sarvam")
async def put_link(agent_id: str, body: LinkIn, request: Request, p: Principal = Depends(tenant_admin_scope),
                   db: AsyncSession = DB):
    agent = await _own_agent(db, agent_id, p.tenant_id)
    link = await _link_for(db, agent)
    if not link:
        link = SarvamAgentLink(tenant_id=agent.tenant_id, agent_id=agent.id)
        db.add(link)
    link.org_id, link.workspace_id, link.app_id = body.org_id.strip(), body.workspace_id.strip(), body.app_id.strip()
    link.enabled = body.enabled
    await audit(db, request, p, "sarvam_link.update", "agent", agent.id, enabled=body.enabled)
    await db.commit()
    return _link_out(link, request)


@router.post("/agents/{agent_id}/sarvam/token")
async def rotate_token(agent_id: str, request: Request, p: Principal = Depends(tenant_admin_scope),
                       db: AsyncSession = DB):
    """New tool token for Sarvam's tool auth (Bearer). Shown once; only its hash is stored."""
    agent = await _own_agent(db, agent_id, p.tenant_id)
    link = await _link_for(db, agent)
    if not link:
        link = SarvamAgentLink(tenant_id=agent.tenant_id, agent_id=agent.id)
        db.add(link)
    token = "svt_" + new_token(32)
    link.tool_token_hash = hash_token(token)
    await audit(db, request, p, "sarvam_link.rotate_token", "agent", agent.id)
    await db.commit()
    return {"token": token, **_link_out(link, request)}


# ---- Tool webhook (called by Sarvam) -----------------------------------------------------------------------------

async def _link_from_token(db: AsyncSession, authorization: str | None) -> SarvamAgentLink:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Missing tool token")
    link = (await db.execute(select(SarvamAgentLink).where(
        SarvamAgentLink.tool_token_hash == hash_token(token)))).scalar_one_or_none()
    if not link or not link.enabled:
        raise HTTPException(401, "Invalid or disabled tool token")
    return link


_INTERACTION = re.compile(r"^[A-Za-z0-9_.:/-]{1,200}$")


def valid_interaction_id(value: object) -> str:
    v = str(value or "").strip()
    if not _INTERACTION.match(v):
        raise HTTPException(422, "Invalid interaction_id")
    return v


async def _conversation_for(db: AsyncSession, link: SarvamAgentLink, interaction_id: str | None) -> str:
    """One conversation (and call record) per Sarvam interaction, with a stable id derived from it, so a call's
    tool runs and its transcript land together under Calls."""
    if not interaction_id:
        conv_id = str(uuid.uuid4())
    else:
        conv_id = str(uuid.uuid5(_CONV_NS, f"{link.id}:{interaction_id}"))
        existing = await db.get(Conversation, conv_id)
        if existing:
            if existing.tenant_id != link.tenant_id or existing.agent_id != link.agent_id:
                raise HTTPException(409, "Interaction belongs to another agent")
            return conv_id
    db.add(Conversation(id=conv_id, tenant_id=link.tenant_id, agent_id=link.agent_id, channel=CHANNEL))
    if interaction_id:
        db.add(CallSession(tenant_id=link.tenant_id, conversation_id=conv_id, agent_id=link.agent_id, channel=CHANNEL,
                           external_ref=interaction_id, answered_at=datetime.now(UTC)))
    db.add(AnalyticsEvent(tenant_id=link.tenant_id, agent_id=link.agent_id, conversation_id=conv_id,
                          name="conversation_started", properties={"channel": CHANNEL}))
    await db.commit()
    return conv_id


# ---- Transcripts (Sarvam Analytics API) ---------------------------------------------------------------------------

_LANG_CODES = {name.lower(): code for code, name in LANGS}


async def _fetch_transcript(link: SarvamAgentLink, interaction_id: str) -> list[dict]:
    s = get_settings()
    if not s.sarvam_agents_api_key:
        raise HTTPException(503, "Sarvam Voice Agents is not configured (set SARVAM_AGENTS_API_KEY)")
    org, ws, app = effective_ids(link)
    url = (f"{s.sarvam_agents_analytics_url.rstrip('/')}/{quote(org, safe='')}/{quote(ws, safe='')}/{quote(app, safe='')}"
           f"/transcripts/{quote(interaction_id, safe='')}")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers={"X-API-Key": s.sarvam_agents_api_key})
    except httpx.HTTPError as e:
        log.warning("sarvam_transcript_failed", error=type(e).__name__)
        raise HTTPException(502, "Couldn't reach Sarvam") from None
    if r.status_code in (401, 403):  # never retried: a bad key stays bad
        raise HTTPException(502, "Sarvam rejected the Voice Agents API key")
    if r.status_code == 429:
        raise HTTPException(429, "Sarvam is rate limiting; try again shortly")
    if r.status_code >= 400:
        raise HTTPException(502, f"Sarvam error {r.status_code}")
    data = r.json() if r.content else {}
    msgs = data.get("messages") if isinstance(data, dict) else None
    return [m for m in (msgs or []) if isinstance(m, dict) and m.get("content")]


async def save_transcript(db: AsyncSession, link: SarvamAgentLink, interaction_id: str) -> dict:
    """Fetch a finished call's transcript from Sarvam and store it as that call's conversation.

    Idempotent: messages are replaced each time. Sarvam returns an empty list while the transcript isn't ready
    (or for an unknown id); then nothing is stored and ``pending`` is true so the caller can retry later.
    """
    conv_id = await _conversation_for(db, link, interaction_id)
    messages = await _fetch_transcript(link, interaction_id)
    if not messages:
        return {"ok": True, "pending": True, "conversation_id": conv_id, "messages": 0}
    conv = await db.get(Conversation, conv_id)
    call = (await db.execute(select(CallSession).where(
        CallSession.tenant_id == link.tenant_id, CallSession.conversation_id == conv_id))).scalars().first()
    await db.execute(delete(ConversationMessage).where(
        ConversationMessage.tenant_id == link.tenant_id, ConversationMessage.conversation_id == conv_id))
    base = as_utc(conv.created_at) if conv.created_at else datetime.now(UTC)
    langs: list[str] = []
    history: list[dict] = []
    for i, m in enumerate(messages):
        role = "user" if str(m.get("role")) == "user" else "assistant"
        lang = _LANG_CODES.get(str(m.get("language_name") or "").lower())
        if lang and lang not in langs:
            langs.append(lang)
        db.add(ConversationMessage(tenant_id=link.tenant_id, conversation_id=conv_id, role=role,
                                   content=str(m["content"])[:8000], language=lang,
                                   meta={"source": "sarvam", "turn_id": m.get("turn_id")},
                                   created_at=base + timedelta(milliseconds=i)))
        history.append({"role": role, "content": str(m["content"])})
    now = datetime.now(UTC)
    user_turns = sum(1 for h in history if h["role"] == "user")
    conv.status = "completed" if user_turns else "abandoned"
    conv.ended_at = conv.ended_at or now
    conv.languages_used = langs or conv.languages_used
    conv.language = langs[0] if langs else conv.language
    if call:
        call.status = "completed" if user_turns else "missed"
        call.ended_at = call.ended_at or now
        call.end_reason = call.end_reason or "sarvam_call_ended"
    await db.commit()
    state = ConversationState(conversation_id=conv_id, tenant_id=link.tenant_id, agent_id=link.agent_id,
                              channel=CHANNEL, history=history)
    summary = await summarise(state)  # best-effort; None without an LLM key
    if summary:
        conv.summary = summary
        await db.commit()
    return {"ok": True, "pending": False, "conversation_id": conv_id, "messages": len(messages)}


class CallIn(BaseModel):
    interaction_id: str = Field(max_length=200)


@router.post("/agents/{agent_id}/sarvam/calls")
async def save_dashboard_call(agent_id: str, body: CallIn, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """After a dashboard test call: store its transcript under Calls."""
    agent = await _own_agent(db, agent_id, p.tenant_id)
    link = await _link_for(db, agent)
    if not _callable(link):
        raise HTTPException(404, "This agent isn't linked to a Sarvam Voice Agent")
    return await save_transcript(db, link, valid_interaction_id(body.interaction_id))


@router.post("/conversations/{conv_id}/sarvam-transcript")
async def refresh_transcript(conv_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """Re-fetch a Sarvam call's transcript (e.g. if it wasn't ready when the call ended)."""
    call = (await db.execute(select(CallSession).where(
        CallSession.tenant_id == p.tenant_id, CallSession.conversation_id == conv_id,
        CallSession.external_ref.is_not(None)))).scalars().first()
    if not call:
        raise HTTPException(404, "Not a Sarvam call")
    link = (await db.execute(select(SarvamAgentLink).where(
        SarvamAgentLink.tenant_id == p.tenant_id, SarvamAgentLink.agent_id == call.agent_id))).scalar_one_or_none()
    if not link or not all(effective_ids(link)):
        raise HTTPException(404, "This agent isn't linked to a Sarvam Voice Agent")
    return await save_transcript(db, link, call.external_ref)


@router.post("/sarvam/tools/{tool_name}", name="sarvam_tool")
async def sarvam_tool(tool_name: str, args: dict = Body(default_factory=dict),
                      authorization: str | None = Header(default=None),
                      x_interaction_id: str | None = Header(default=None), db: AsyncSession = DB):
    """Run one of the linked agent's read-only tools. Body = the tool's arguments as a JSON object.

    Configure the Sarvam tool as POST {tool_url} with Bearer auth = the agent's tool token. Optionally send the
    call's Interaction ID in an ``X-Interaction-Id`` header (or an ``interaction_id`` body field) so all tool runs
    of one call are grouped. Errors the caller should hear come back as 200 with ok=false, so the agent can say so.
    """
    link = await _link_from_token(db, authorization)
    bundle = await load_agent_bundle(db, link.agent_id, tenant_id=link.tenant_id)
    if not bundle:
        raise HTTPException(404, "Agent not available")
    args = dict(args or {})
    interaction_id = x_interaction_id or args.pop("interaction_id", None)
    spec = get_tool(tool_name)
    enabled = bundle.config.enabled_tools or []
    if spec and spec.is_write:
        return {"ok": False, "error": "This action isn't available on this line yet. Offer to have the team "
                                      "call back, or share the business phone number."}
    allowed = [n for n in enabled if (s := get_tool(n)) and not s.is_write]
    try:
        interaction_id = valid_interaction_id(interaction_id) if interaction_id else None
    except HTTPException:
        interaction_id = None  # an odd id shouldn't fail the caller's tool call; it just won't be grouped
    conv_id = await _conversation_for(db, link, interaction_id)
    state = ConversationState(conversation_id=conv_id, tenant_id=link.tenant_id, agent_id=link.agent_id,
                              channel=CHANNEL, language=bundle.agent.default_language)
    ctx = ToolContext(db=db, tenant_id=link.tenant_id, agent_id=link.agent_id, state=state,
                      business_timezone=bundle.profile.timezone if bundle.profile else "Asia/Kolkata")
    return await execute_tool(ctx, tool_name, args, allowed)


# ---- Call sessions (Sarvam browser SDK proxy) ----------------------------------------------------------------------

def _callable(link: SarvamAgentLink | None) -> bool:
    return bool(link and link.enabled and all(effective_ids(link)))


async def sarvam_link_for(db: AsyncSession, agent: Agent) -> SarvamAgentLink | None:
    """This agent's link if it can take Sarvam calls, else None."""
    link = await _link_for(db, agent)
    return link if _callable(link) else None


def _short(value: object, limit: int = 300) -> str:
    return " ".join(str(value).split())[:limit]


async def business_context(db: AsyncSession, agent: Agent) -> dict[str, str] | None:
    """Business facts for the Sarvam agent's prompt, sent as agent_variables when a call starts.

    Off unless SARVAM_AGENTS_SEND_CONTEXT is on, since the Sarvam agent must declare these variables first.
    Only public business information: never customer data.
    """
    if not get_settings().sarvam_agents_send_context:
        return None
    bundle = await load_agent_bundle(db, agent.id, tenant_id=agent.tenant_id)
    if not bundle:
        return None
    p = bundle.profile
    hours = "; ".join(f"{k}: {v}" for k, v in (p.operating_hours or {}).items()) if p else ""
    return {
        "business_name": _short(p.display_name if p else ""),
        "business_phone": _short(p.phone if p else ""),
        "business_hours": _short(hours),
        "business_services": _short(", ".join(p.services or []) if p else ""),
        "persona_name": _short(bundle.config.persona_name),
        "languages": ", ".join(agent.languages or []),
    }


async def call_config(db: AsyncSession, agent: Agent) -> dict | None:
    """What a browser needs to start a Sarvam call to this agent (no secrets), or None if it can't take calls."""
    if not get_settings().sarvam_agents_api_key:
        return None
    link = await _link_for(db, agent)
    if not _callable(link):
        return None
    org, ws, app = effective_ids(link)
    cfg: dict = {"org_id": org, "workspace_id": ws, "app_id": app}
    variables = await business_context(db, agent)
    if variables:
        cfg["agent_variables"] = variables
    return cfg


public_voice_info = call_config  # the website widget's session response uses the same shape


async def mint_session(db: AsyncSession, agent: Agent, org_id: str, workspace_id: str, app_id: str,
                       interaction_type: str | None, version: str | None) -> dict:
    """Signed WebSocket URL for one call to this agent's Sarvam app, fetched with our server-side key."""
    s = get_settings()
    link = await _link_for(db, agent)
    if not _callable(link):
        raise HTTPException(404, "This agent isn't linked to a Sarvam Voice Agent")
    if (org_id, workspace_id, app_id) != effective_ids(link):
        raise HTTPException(400, "Sarvam app ids don't match this agent's link")
    if not s.sarvam_agents_api_key:
        raise HTTPException(503, "Sarvam Voice Agents is not configured (set SARVAM_AGENTS_API_KEY)")
    params = {k: v for k, v in (("interaction_type", interaction_type), ("version", version)) if v}
    url = f"{s.sarvam_agents_base_url.rstrip('/')}/orgs/{org_id}/workspaces/{workspace_id}/apps/{app_id}/url"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params, headers={"X-API-Key": s.sarvam_agents_api_key})
    except httpx.HTTPError as e:
        log.warning("sarvam_session_failed", error=type(e).__name__)
        raise HTTPException(502, "Couldn't reach Sarvam") from None
    if r.status_code in (401, 403):  # never retried: a bad key stays bad
        raise HTTPException(502, "Sarvam rejected the Voice Agents API key")
    if r.status_code == 402:
        raise HTTPException(402, "Sarvam account is out of credits")
    if r.status_code == 404:
        raise HTTPException(404, "Sarvam app not found (check org, workspace and app ids)")
    if r.status_code == 429:
        raise HTTPException(429, "Sarvam is rate limiting calls; try again shortly")
    if r.status_code >= 400:
        raise HTTPException(502, f"Sarvam error {r.status_code}")
    data = r.json()
    if not isinstance(data, dict) or not data.get("url") or not data.get("reference_id"):
        raise HTTPException(502, "Unexpected response from Sarvam")
    return {"url": data["url"], "reference_id": data["reference_id"]}


@router.get("/agents/{agent_id}/sarvam/call-config")
async def dashboard_call_config(agent_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """Ids (and optional business context) for a dashboard test call. 404 when the agent can't take calls."""
    agent = await _own_agent(db, agent_id, p.tenant_id)
    cfg = await call_config(db, agent)
    if not cfg:
        raise HTTPException(404, "Voice isn't set up for this agent (link, ids and SARVAM_AGENTS_API_KEY)")
    return cfg


@router.post("/agents/{agent_id}/sarvam/check")
async def check_agent_connection(agent_id: str, request: Request, p: Principal = Depends(tenant_admin_scope),
                                 db: AsyncSession = DB):
    """Server-side connection check with Sarvam's Python SDK: a ~10 s headless call that waits for the greeting.

    Verifies the key, ids, committed agent version and credits without a microphone. Uses a little call time.
    """
    from app.sarvam.voice_agent import CheckBusy, check_connection

    agent = await _own_agent(db, agent_id, p.tenant_id)
    link = await _link_for(db, agent)
    org, ws, app = effective_ids(link)
    if not (org and ws and app):
        raise HTTPException(422, "Set the Sarvam org, workspace and app ids first")
    variables = await business_context(db, agent)
    await audit(db, request, p, "sarvam_link.check", "agent", agent.id)
    await db.commit()
    try:
        result = await check_connection(f"{agent.tenant_id}:{agent.id}", org, ws, app, variables)
    except CheckBusy as e:
        raise HTTPException(409, str(e)) from None
    return result.as_dict()


@router.get("/sarvam/runtime/{agent_id}/orgs/{org_id}/workspaces/{workspace_id}/apps/{app_id}/url")
async def sarvam_session_url(agent_id: str, org_id: str, workspace_id: str, app_id: str,
                             interaction_type: str | None = Query(default=None),
                             version: str | None = Query(default=None),
                             p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """Dashboard test calls. The Sarvam browser SDK requests ``{baseUrl}orgs/{org}/workspaces/{ws}/apps/{app}/url``;
    the dashboard sets baseUrl to ``/api/v1/sarvam/runtime/{agent_id}/`` and sends the user's login in customHeaders.
    """
    agent = await _own_agent(db, agent_id, p.tenant_id)
    return await mint_session(db, agent, org_id, workspace_id, app_id, interaction_type, version)
