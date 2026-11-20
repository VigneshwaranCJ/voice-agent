"""Hosted Sarvam Voice Agents: tool webhook isolation, write refusal, and the SDK session proxy."""

import httpx
import pytest
from sqlalchemy import func, select

from app.api import sarvam_agents as sa_mod
from app.core.config import get_settings
from app.models import Appointment, Conversation, Lead, SarvamAgentLink, ToolExecution
from tests.conftest import agent_for, login

IDS = {"org_id": "org1", "workspace_id": "ws1", "app_id": "app1"}


def _setup(client, db_agent_id: str, email: str, enabled: bool = True) -> tuple[dict, str]:
    h = login(client, email)
    r = client.put(f"/api/v1/agents/{db_agent_id}/sarvam", json={**IDS, "enabled": enabled}, headers=h)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/agents/{db_agent_id}/sarvam/token", headers=h)
    assert r.status_code == 200, r.text
    return h, r.json()["token"]


def _tool(client, token: str, name: str, body: dict | None = None, interaction: str | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    if interaction:
        headers["X-Interaction-Id"] = interaction
    return client.post(f"/api/v1/sarvam/tools/{name}", json=body or {}, headers=headers)


async def test_tool_runs_only_on_the_tokens_own_tenant(client, db):
    sunrise = await agent_for(db, "sunrise-realty")
    carewell = await agent_for(db, "carewell-hospital")
    _, s_token = _setup(client, sunrise.id, "admin@sunrise.local")
    _, c_token = _setup(client, carewell.id, "admin@carewell.local")

    r = _tool(client, s_token, "search_properties", {"city": "Coimbatore", "bhk": 2})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["count"] >= 1
    assert all(p["city"] == "Coimbatore" for p in r.json()["properties"])

    # The hospital's token can't reach real-estate tools, and a tenant_id in the body changes nothing.
    r = _tool(client, c_token, "search_properties", {"city": "Coimbatore", "tenant_id": sunrise.tenant_id})
    assert r.json()["ok"] is False
    r = _tool(client, c_token, "search_knowledge", {"query": "site visit pickup", "tenant_id": sunrise.tenant_id})
    assert r.json()["ok"]
    assert all("Sunrise" not in hit["source"] for hit in r.json()["results"])

    logged = (await db.execute(select(ToolExecution).where(ToolExecution.tool_name == "search_properties"))).scalars().all()
    assert {t.tenant_id for t in logged} <= {sunrise.tenant_id, carewell.tenant_id}
    assert any(t.tenant_id == sunrise.tenant_id and t.status == "success" for t in logged)
    assert all(t.status != "success" for t in logged if t.tenant_id == carewell.tenant_id)


async def test_writes_are_refused_without_caller_confirmation(client, db):
    sunrise = await agent_for(db, "sunrise-realty")
    _, token = _setup(client, sunrise.id, "admin@sunrise.local")
    prop = _tool(client, token, "search_properties", {"city": "Coimbatore"}).json()["properties"][0]
    r = _tool(client, token, "schedule_site_visit", {"property_id": prop["property_id"], "confirmed": True,
                                                       "name": "Test", "phone": "9876543210",
                                                       "date": "2030-01-05", "time": "11:00"})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert (await db.execute(select(func.count()).select_from(Appointment))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(Lead))).scalar_one() == 0
    r = _tool(client, token, "identify_customer", {"phone": "9876543210"})
    assert r.json()["ok"] is False


async def test_bad_disabled_or_missing_tokens_are_rejected(client, db):
    sunrise = await agent_for(db, "sunrise-realty")
    h, token = _setup(client, sunrise.id, "admin@sunrise.local", enabled=False)
    assert _tool(client, token, "get_business_info").status_code == 401
    assert _tool(client, "svt_not-a-real-token", "get_business_info").status_code == 401
    assert client.post("/api/v1/sarvam/tools/get_business_info", json={}).status_code == 401
    # Rotating replaces the old token.
    client.put(f"/api/v1/agents/{sunrise.id}/sarvam", json={**IDS, "enabled": True}, headers=h)
    new = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/token", headers=h).json()["token"]
    assert _tool(client, token, "get_business_info").status_code == 401
    assert _tool(client, new, "get_business_info").json()["ok"]
    # Only the hash is stored, and the dashboard never gets the token back.
    link = (await db.execute(select(SarvamAgentLink).where(SarvamAgentLink.agent_id == sunrise.id))).scalar_one()
    assert new not in (link.tool_token_hash or "")
    assert "token" not in client.get(f"/api/v1/agents/{sunrise.id}/sarvam", headers=h).json()


async def test_one_conversation_per_sarvam_interaction(client, db):
    sunrise = await agent_for(db, "sunrise-realty")
    _, token = _setup(client, sunrise.id, "admin@sunrise.local")
    before = (await db.execute(select(func.count()).select_from(Conversation))).scalar_one()
    _tool(client, token, "get_business_info", interaction="int-1")
    _tool(client, token, "search_knowledge", {"query": "home loans"}, interaction="int-1")
    _tool(client, token, "get_business_info", interaction="int-2")
    convs = (await db.execute(select(Conversation).where(Conversation.channel == "sarvam_voice"))).scalars().all()
    assert len(convs) == 2 and before + 2 == (await db.execute(select(func.count()).select_from(Conversation))).scalar_one()
    assert {c.tenant_id for c in convs} == {sunrise.tenant_id}


async def test_link_management_is_tenant_isolated(client, db):
    sunrise = await agent_for(db, "sunrise-realty")
    hc = login(client, "admin@carewell.local")
    assert client.get(f"/api/v1/agents/{sunrise.id}/sarvam", headers=hc).status_code == 404
    assert client.put(f"/api/v1/agents/{sunrise.id}/sarvam", json=IDS, headers=hc).status_code == 404
    assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/token", headers=hc).status_code == 404


@pytest.fixture
def sarvam_upstream(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"url": "wss://apps.sarvam.ai/signed?x=1", "reference_id": "ref-1"})

    real = httpx.AsyncClient
    monkeypatch.setattr(sa_mod.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    yield seen


async def test_session_proxy_adds_key_server_side(client, db, monkeypatch, sarvam_upstream):
    sunrise = await agent_for(db, "sunrise-realty")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    path = f"/api/v1/sarvam/runtime/{sunrise.id}/orgs/org1/workspaces/ws1/apps/app1/url"

    assert client.get(path, headers=h).status_code == 503  # key not configured: a clear error, no fake success
    monkeypatch.setattr(get_settings(), "sarvam_agents_api_key", "test-agents-key")
    r = client.get(path + "?interaction_type=call", headers=h)
    assert r.status_code == 200 and r.json() == {"url": "wss://apps.sarvam.ai/signed?x=1", "reference_id": "ref-1"}
    sent = sarvam_upstream[-1]
    assert sent.headers["X-API-Key"] == "test-agents-key"
    assert str(sent.url).endswith("/orgs/org1/workspaces/ws1/apps/app1/url?interaction_type=call")

    # Ids must match the saved link; other tenants and anonymous callers get nothing.
    bad = f"/api/v1/sarvam/runtime/{sunrise.id}/orgs/other/workspaces/ws1/apps/app1/url"
    assert client.get(bad, headers=h).status_code == 400
    assert client.get(path, headers=login(client, "admin@carewell.local")).status_code == 404
    assert client.get(path).status_code == 401
    assert len(sarvam_upstream) == 1


async def test_session_proxy_maps_out_of_credits(client, db, monkeypatch):
    sunrise = await agent_for(db, "sunrise-realty")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    monkeypatch.setattr(get_settings(), "sarvam_agents_api_key", "k")
    real = httpx.AsyncClient
    monkeypatch.setattr(sa_mod.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda req: httpx.Response(402, json={})), **kw))
    r = client.get(f"/api/v1/sarvam/runtime/{sunrise.id}/orgs/org1/workspaces/ws1/apps/app1/url", headers=h)
    assert r.status_code == 402


async def test_widget_voice_needs_link_and_key_and_its_own_widget_token(client, db, monkeypatch, sarvam_upstream):
    sunrise = await agent_for(db, "sunrise-realty")
    carewell = await agent_for(db, "carewell-hospital")
    _setup(client, sunrise.id, "admin@sunrise.local")
    s = client.post(f"/api/v1/public/agents/{sunrise.id}/session").json()
    assert s["voice"] is None  # no Voice Agents key on the server yet: no Call button

    monkeypatch.setattr(get_settings(), "sarvam_agents_api_key", "test-agents-key")
    s = client.post(f"/api/v1/public/agents/{sunrise.id}/session").json()
    assert s["voice"] == {"org_id": "org1", "workspace_id": "ws1", "app_id": "app1"}
    assert client.post(f"/api/v1/public/agents/{carewell.id}/session").json()["voice"] is None  # not linked

    base = f"/api/v1/public/sarvam/{sunrise.id}/{s['token']}/orgs/org1/workspaces/ws1/apps/app1/url"
    r = client.get(base + "?interaction_type=call", headers={"Origin": "https://customer.example"})
    assert r.status_code == 200 and r.json()["reference_id"] == "ref-1"
    assert r.headers["access-control-allow-origin"] == "*"
    assert sarvam_upstream[-1].headers["X-API-Key"] == "test-agents-key"

    # Another agent's widget token, a login token, a junk token, or wrong ids: refused.
    c_token = client.post(f"/api/v1/public/agents/{carewell.id}/session").json()["token"]
    other = f"/api/v1/public/sarvam/{sunrise.id}/{c_token}/orgs/org1/workspaces/ws1/apps/app1/url"
    assert client.get(other).status_code == 401
    jwt = login(client, "admin@sunrise.local")["Authorization"].split()[1]
    assert client.get(f"/api/v1/public/sarvam/{sunrise.id}/{jwt}/orgs/org1/workspaces/ws1/apps/app1/url").status_code == 401
    assert client.get(f"/api/v1/public/sarvam/{sunrise.id}/junk/orgs/org1/workspaces/ws1/apps/app1/url").status_code == 401
    assert client.get(base.replace("/apps/app1/", "/apps/other/")).status_code == 400
    assert len(sarvam_upstream) == 1

    # Turning the public widget off closes the voice route too.
    agent_row = await db.get(type(sunrise), sunrise.id)
    agent_row.public_widget_enabled = False
    await db.commit()
    assert client.get(base).status_code == 404


TRANSCRIPT = {"interaction_id": "20261120/abc123", "messages": [
    {"turn_id": 1, "role": "assistant", "content": "Hello, this is Kavya from Sunrise Realty.", "language_name": "English"},
    {"turn_id": 2, "role": "user", "content": "Do you have 2BHK flats in Coimbatore?", "language_name": "English"},
    {"turn_id": 3, "role": "assistant", "content": "Yes, Sunrise Meadows 2BHK in Saravanampatti.", "language_name": "Tamil"},
]}


@pytest.fixture
def sarvam_analytics(monkeypatch):
    """Fake Sarvam Analytics API: empty (not ready) until `ready` is set, then the transcript."""
    state = {"ready": False, "seen": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["seen"].append(request)
        return httpx.Response(200, json=TRANSCRIPT if state["ready"] else {"interaction_id": "x", "messages": []})

    real = httpx.AsyncClient
    monkeypatch.setattr(sa_mod.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(get_settings(), "sarvam_agents_api_key", "test-agents-key")
    yield state


async def test_transcript_saved_under_calls_and_grouped_with_tool_runs(client, db, sarvam_analytics):
    from app.models import CallSession, ConversationMessage

    sunrise = await agent_for(db, "sunrise-realty")
    h, token = _setup(client, sunrise.id, "admin@sunrise.local")
    iid = "20261120/abc123"
    _tool(client, token, "get_business_info", interaction=iid)  # a tool run during the call

    r = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/calls", json={"interaction_id": iid}, headers=h)
    assert r.status_code == 200 and r.json()["pending"] is True  # Sarvam not ready yet: nothing stored
    sarvam_analytics["ready"] = True
    r = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/calls", json={"interaction_id": iid}, headers=h)
    assert r.json()["pending"] is False and r.json()["messages"] == 3
    conv_id = r.json()["conversation_id"]
    sent = sarvam_analytics["seen"][-1]
    assert sent.headers["X-API-Key"] == "test-agents-key"
    assert str(sent.url).endswith("/org1/ws1/app1/transcripts/20261120%2Fabc123")

    detail = client.get(f"/api/v1/conversations/{conv_id}", headers=h).json()
    assert [m["role"] for m in detail["messages"]] == ["assistant", "user", "assistant"]
    assert detail["conversation"]["channel"] == "sarvam_voice" and detail["conversation"]["status"] == "completed"
    assert set(detail["conversation"]["languages_used"]) == {"en-IN", "ta-IN"}
    assert [t["tool"] for t in detail["tool_executions"]] == ["get_business_info"]  # same call, same conversation
    # Saving again (or refreshing) replaces rather than duplicates.
    assert client.post(f"/api/v1/conversations/{conv_id}/sarvam-transcript", headers=h).json()["messages"] == 3
    n = (await db.execute(select(func.count()).select_from(ConversationMessage)
                          .where(ConversationMessage.conversation_id == conv_id))).scalar_one()
    assert n == 3
    calls = (await db.execute(select(CallSession).where(CallSession.conversation_id == conv_id))).scalars().all()
    assert len(calls) == 1 and calls[0].external_ref == iid and calls[0].status == "completed"


async def test_transcript_routes_are_tenant_isolated_and_validated(client, db, sarvam_analytics):
    sarvam_analytics["ready"] = True
    sunrise = await agent_for(db, "sunrise-realty")
    carewell = await agent_for(db, "carewell-hospital")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    hc = login(client, "admin@carewell.local")
    conv_id = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/calls", json={"interaction_id": "20261120/x1"},
                          headers=h).json()["conversation_id"]
    # Another business can't save into, refresh, or read this agent's calls.
    assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/calls", json={"interaction_id": "a/b"},
                       headers=hc).status_code == 404
    assert client.post(f"/api/v1/conversations/{conv_id}/sarvam-transcript", headers=hc).status_code == 404
    assert client.get(f"/api/v1/conversations/{conv_id}", headers=hc).status_code == 404
    # An unlinked agent, a bad id, and a non-Sarvam conversation are refused.
    assert client.post(f"/api/v1/agents/{carewell.id}/sarvam/calls", json={"interaction_id": "a/b"},
                       headers=hc).status_code == 404
    assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/calls", json={"interaction_id": "../../etc?x=1"},
                       headers=h).status_code == 422


async def test_widget_saves_transcript_but_never_returns_it(client, db, sarvam_analytics):
    import json as _json

    sarvam_analytics["ready"] = True
    sunrise = await agent_for(db, "sunrise-realty")
    carewell = await agent_for(db, "carewell-hospital")
    _setup(client, sunrise.id, "admin@sunrise.local")
    token = client.post(f"/api/v1/public/agents/{sunrise.id}/session").json()["token"]
    plain = {"Content-Type": "text/plain;charset=UTF-8"}
    r = client.post("/api/v1/public/sarvam/calls", headers=plain,
                    content=_json.dumps({"token": token, "interaction_id": "20261120/w1"}))
    assert r.status_code == 200 and r.json() == {"ok": True, "pending": False}
    assert r.headers["access-control-allow-origin"] == "*"
    # Unlinked agent's widget, and junk tokens: refused.
    c_token = client.post(f"/api/v1/public/agents/{carewell.id}/session").json()["token"]
    assert client.post("/api/v1/public/sarvam/calls", headers=plain,
                       content=_json.dumps({"token": c_token, "interaction_id": "a/b"})).status_code == 404
    assert client.post("/api/v1/public/sarvam/calls", headers=plain,
                       content=_json.dumps({"token": "junk", "interaction_id": "a/b"})).status_code == 401


# ---- env defaults, call config, business context ------------------------------------------------------------------

async def test_env_default_ids_and_call_config(client, db, monkeypatch):
    s = get_settings()
    sunrise = await agent_for(db, "sunrise-realty")
    h = login(client, "admin@sunrise.local")
    # Only the app id on the link; org and workspace come from the server defaults.
    client.put(f"/api/v1/agents/{sunrise.id}/sarvam", json={"app_id": "app9", "enabled": True}, headers=h)
    assert client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config", headers=h).status_code == 404  # no key yet
    monkeypatch.setattr(s, "sarvam_agents_api_key", "k")
    assert client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config", headers=h).status_code == 404  # no org/ws
    monkeypatch.setattr(s, "sarvam_agents_org_id", "org-default")
    monkeypatch.setattr(s, "sarvam_agents_workspace_id", "ws-default")
    cfg = client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config", headers=h).json()
    assert cfg == {"org_id": "org-default", "workspace_id": "ws-default", "app_id": "app9"}
    link = client.get(f"/api/v1/agents/{sunrise.id}/sarvam", headers=h).json()
    assert link["effective"] == cfg and link["voice_configured"] is True and link["org_id"] == ""
    # Another business can't read this agent's call config.
    assert client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config",
                      headers=login(client, "admin@carewell.local")).status_code == 404


async def test_business_context_only_when_enabled_and_never_customer_data(client, db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sarvam_agents_api_key", "k")
    sunrise = await agent_for(db, "sunrise-realty")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    assert "agent_variables" not in client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config", headers=h).json()
    monkeypatch.setattr(s, "sarvam_agents_send_context", True)
    v = client.get(f"/api/v1/agents/{sunrise.id}/sarvam/call-config", headers=h).json()["agent_variables"]
    assert v["business_name"] == "Sunrise Realty" and v["persona_name"] == "Kavya" and "Apartments" in v["business_services"]
    assert set(v) == {"business_name", "business_phone", "business_hours", "business_services", "persona_name", "languages"}
    widget = client.post(f"/api/v1/public/agents/{sunrise.id}/session").json()["voice"]
    assert widget["agent_variables"]["business_name"] == "Sunrise Realty"


# ---- Python SDK connection check (headless AsyncSamvaadAgent) ------------------------------------------------------

class FakeSamvaadAgent:
    """Stands in for sarvam_conv_ai_sdk.AsyncSamvaadAgent; records the call sequence."""
    instances: list["FakeSamvaadAgent"] = []
    mode = "ok"  # ok | silent | start_fails | auth_fails

    def __init__(self, *, api_key, config, base_url, transcript_callback, audio_callback, event_callback, **kw):
        self.api_key, self.config, self.calls = api_key, config, []
        self.cb_t, self.cb_a, self.cb_e = transcript_callback, audio_callback, event_callback
        FakeSamvaadAgent.instances.append(self)

    async def start(self):
        self.calls.append("start")
        if self.mode == "start_fails":
            raise RuntimeError("network down")
        if self.mode == "auth_fails":
            raise type("AuthenticationError", (Exception,), {})("bad key")

    async def wait_for_connect(self, timeout=5.0):
        self.calls.append("wait_for_connect")
        return True

    def get_interaction_id(self):
        return "20261120/check1"

    def is_connected(self):
        return True

    async def send_audio(self, data: bytes):
        self.calls.append("send_audio")
        assert isinstance(data, bytes) and len(data) == 3200  # 100 ms of 16 kHz 16-bit mono
        if self.mode == "ok" and self.calls.count("send_audio") == 2:
            import time

            from sarvam_conv_ai_sdk import Role, ServerTranscriptMsg
            await self.cb_t(ServerTranscriptMsg(timestamp=time.time(), role=Role.BOT,
                                                content="Hello, this is Kavya from Sunrise Realty."))

    async def stop(self):
        self.calls.append("stop")


@pytest.fixture
def fake_sdk(monkeypatch):
    import sarvam_conv_ai_sdk

    FakeSamvaadAgent.instances = []
    FakeSamvaadAgent.mode = "ok"
    monkeypatch.setattr(sarvam_conv_ai_sdk, "AsyncSamvaadAgent", FakeSamvaadAgent)
    monkeypatch.setattr(get_settings(), "sarvam_agents_api_key", "secret-voice-key")
    yield FakeSamvaadAgent


async def test_connection_check_uses_sdk_lifecycle_and_always_stops(client, db, fake_sdk):
    sunrise = await agent_for(db, "sunrise-realty")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    r = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] and body["error"] is None and body["interaction_id"] == "20261120/check1"
    assert body["first_agent_text"].startswith("Hello, this is Kavya")
    agent = fake_sdk.instances[-1]
    assert agent.calls[:3] == ["start", "wait_for_connect", "send_audio"] and agent.calls[-1] == "stop"
    assert agent.api_key.get_secret_value() == "secret-voice-key" and "secret-voice-key" not in r.text
    assert (agent.config.org_id, agent.config.app_id, agent.config.interaction_type.value) == ("org1", "app1", "call")
    assert agent.config.sample_rate == 16000

    fake_sdk.mode = "start_fails"
    body = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check", headers=h).json()
    assert body["connected"] is False and "network down" in body["error"]
    assert fake_sdk.instances[-1].calls == ["start", "stop"]  # cleaned up even though start() failed

    fake_sdk.mode = "auth_fails"
    body = client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check", headers=h).json()
    assert body["error"] == "Sarvam rejected the Voice Agents API key." and fake_sdk.instances[-1].calls[-1] == "stop"


async def test_connection_check_is_admin_only_isolated_and_not_duplicated(client, db, fake_sdk):
    from app.sarvam import voice_agent

    sunrise = await agent_for(db, "sunrise-realty")
    h, _ = _setup(client, sunrise.id, "admin@sunrise.local")
    assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check",
                       headers=login(client, "admin@carewell.local")).status_code == 404
    voice_agent._running.add(f"{sunrise.tenant_id}:{sunrise.id}")  # a check already in flight
    try:
        assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check", headers=h).status_code == 409
    finally:
        voice_agent._running.clear()
    assert client.post(f"/api/v1/agents/{sunrise.id}/sarvam/check", headers=h).status_code == 200
    assert voice_agent._running == set()  # released after the check
