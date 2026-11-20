"""Text chat: the dashboard's test console and the public website widget (plain HTTP).

Voice calls run on hosted Sarvam Voice Agents (app/api/sarvam_agents.py).
"""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.manager import load_agent_bundle
from app.context.state import get_state_store
from app.core.config import get_settings
from app.llm.sarvam import SarvamLLM, get_llm
from app.core.deps import DB, Principal, tenant_scope
from app.models import Agent, Conversation
from app.orchestration.engine import AgentEngine, greeting_for
from app.orchestration.lifecycle import end_conversation, start_conversation
from app.schemas.api import ChatIn, ChatOut
from app.security.crypto import create_access_token, decode_token
from app.api.sarvam_agents import (
    mint_session, public_voice_info, sarvam_link_for, save_transcript, valid_interaction_id,
)

router = APIRouter(tags=["chat"])


@router.post("/public/agents/{agent_id}/session")
async def widget_session(agent_id: str, db: AsyncSession = DB):
    """Short-lived token for the website widget. Only for agents with public_widget_enabled."""
    a = (await db.execute(select(Agent).where(Agent.id == agent_id, Agent.is_active.is_(True)))).unique().scalar_one_or_none()
    if not a or not a.public_widget_enabled:
        raise HTTPException(404, "Agent not available")
    token = create_access_token(user_id=f"widget:{agent_id}", tenant_id=a.tenant_id, role="widget",
                                extra={"kind": "widget", "aid": agent_id}, expires_minutes=15)
    bundle = await load_agent_bundle(db, a.id, tenant_id=a.tenant_id)
    greeting = greeting_for(bundle, a.default_language) if bundle else ""
    business = bundle.profile.display_name if bundle and bundle.profile else ""
    return {"token": token, "expires_in": 15 * 60, "voice": await public_voice_info(db, a),
            "agent": {"id": a.id, "name": a.name, "languages": a.languages, "default_language": a.default_language,
                      "persona": bundle.config.persona_name if bundle else "", "business": business, "greeting": greeting}}


async def widget_agent_for_token(db: AsyncSession, token: str | None) -> Agent:
    """The agent a widget token was issued for. Tenant and agent come from the token, never the request body."""
    token = (token or "").removeprefix("Bearer ").strip()
    try:
        c = decode_token(token)
    except Exception:
        raise HTTPException(401, "Widget session expired") from None
    if c.get("kind") != "widget":
        raise HTTPException(401, "Not a widget session")
    a = (await db.execute(select(Agent).where(Agent.id == c.get("aid"), Agent.tenant_id == c.get("tid"),
                                              Agent.is_active.is_(True)))).unique().scalar_one_or_none()
    if not a or not a.public_widget_enabled:
        raise HTTPException(404, "Agent not available")
    return a


async def _widget_body(request: Request) -> dict:
    """The widget's JSON body, whatever its Content-Type.

    The widget runs on customers' sites. Some hosts (e.g. Catalyst AppSail's gateway) answer CORS preflights
    themselves and drop them, so the widget sends "simple" requests: text/plain bodies with the token inside,
    no custom headers. The Authorization header still works for clients that can use it.
    """
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Body must be JSON") from None
    if not isinstance(data, dict):
        raise HTTPException(422, "Body must be a JSON object")
    return data


@router.post("/public/chat", response_model=ChatOut)
async def widget_chat(request: Request, authorization: str | None = Header(default=None), db: AsyncSession = DB):
    """Text chat for the website widget (plain HTTP, so it works on hosts without WebSocket support)."""
    data = await _widget_body(request)
    a = await widget_agent_for_token(db, authorization or data.pop("token", None))
    try:
        body = ChatIn.model_validate(data)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    return await _text_turn(db, a.id, a.tenant_id, body, channel="widget")


@router.post("/public/chat/{conv_id}/end")
async def widget_chat_end(conv_id: str, request: Request, authorization: str | None = Header(default=None),
                          db: AsyncSession = DB):
    """Close a widget chat so it is summarised and shows as completed under Calls."""
    data = await _widget_body(request)
    a = await widget_agent_for_token(db, authorization or data.get("token"))
    state = await get_state_store().get(conv_id)
    if not state or state.tenant_id != a.tenant_id or state.agent_id != a.id:
        return {"ok": True, "already_ended": True}  # nothing to close (or not this widget's chat)
    await end_conversation(db, state, "ended_by_user")
    return {"ok": True}


@router.get("/public/sarvam/{agent_id}/{token}/orgs/{org_id}/workspaces/{workspace_id}/apps/{app_id}/url")
async def widget_voice_session(agent_id: str, token: str, org_id: str, workspace_id: str, app_id: str,
                               interaction_type: str | None = Query(default=None),
                               version: str | None = Query(default=None), db: AsyncSession = DB):
    """Signed Sarvam call URL for a website visitor (the widget's Call button).

    The Sarvam browser SDK requests ``{baseUrl}orgs/.../url`` and can only add headers, which would force a CORS
    preflight that some hosts drop; so the widget puts its 15-minute widget token in the path instead. It is bound
    to this agent, only works for agents with the public widget on, and grants nothing else.
    """
    a = await widget_agent_for_token(db, token)
    if a.id != agent_id:
        raise HTTPException(401, "Widget session is for another agent")
    return await mint_session(db, a, org_id, workspace_id, app_id, interaction_type, version)


@router.post("/public/sarvam/calls")
async def widget_voice_call_ended(request: Request, authorization: str | None = Header(default=None),
                                  db: AsyncSession = DB):
    """After a website visitor's call: store its transcript under Calls. Body: {token, interaction_id}.

    The visitor gets back only whether it was stored; the transcript itself goes to the business's dashboard.
    """
    data = await _widget_body(request)
    a = await widget_agent_for_token(db, authorization or data.get("token"))
    link = await sarvam_link_for(db, a)
    if not link:
        raise HTTPException(404, "This agent isn't linked to a Sarvam Voice Agent")
    r = await save_transcript(db, link, valid_interaction_id(data.get("interaction_id")))
    return {"ok": r["ok"], "pending": r["pending"]}


@router.post("/agents/{agent_id}/chat", response_model=ChatOut)
async def chat(agent_id: str, body: ChatIn, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """Text test console: same engine, tools and guardrails as the website widget."""
    return await _text_turn(db, agent_id, p.tenant_id, body, channel="web_text")


async def _text_turn(db: AsyncSession, agent_id: str, tenant_id: str, body: ChatIn, channel: str) -> ChatOut:
    bundle = await load_agent_bundle(db, agent_id, tenant_id=tenant_id)
    if not bundle:
        raise HTTPException(404, "Agent not found")
    if isinstance(get_llm(), SarvamLLM) and not get_settings().sarvam_configured:
        raise HTTPException(503, "SARVAM_API_KEY is not configured on the server")
    store = get_state_store()
    state = await store.get(body.conversation_id) if body.conversation_id else None
    # A conversation id only continues a chat with the same business *and* agent.
    if state and (state.tenant_id != tenant_id or state.agent_id != agent_id):
        raise HTTPException(404, "Conversation not found")
    engine = AgentEngine(db, bundle)
    if not state:
        state = await start_conversation(db, bundle, channel)
        if body.language:
            state.language = body.language
        await engine.record_greeting(state, greeting_for(bundle, state.language))
    result = await engine.handle_turn(state, body.text, body.language)
    return ChatOut(conversation_id=state.conversation_id, reply=result.reply, language=result.language,
                   events=result.events, tool_calls=result.tool_calls, escalated=result.escalated)


@router.post("/conversations/{conv_id}/end")
async def end_chat(conv_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    state = await get_state_store().get(conv_id)
    if not state or state.tenant_id != p.tenant_id:
        conv = (await db.execute(select(Conversation).where(Conversation.tenant_id == p.tenant_id,
                                                            Conversation.id == conv_id))).scalar_one_or_none()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        return {"ok": True, "already_ended": True}
    await end_conversation(db, state, "ended_by_user")
    return {"ok": True}
