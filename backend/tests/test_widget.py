"""Website widget: public session + text chat. Scope comes from the widget token, never the request."""

from sqlalchemy import select

from app.models import Agent, Conversation
from tests.conftest import agent_for, login, say


def _session(client, agent_id):
    return client.post(f"/api/v1/public/agents/{agent_id}/session")


def _chat(client, token, text, conversation_id=None):
    return client.post("/api/v1/public/chat", headers={"Authorization": f"Bearer {token}"},
                       json={"text": text, "conversation_id": conversation_id})


async def test_widget_session_and_chat(client, db, llm):
    agent = await agent_for(db, "sunrise-realty")
    s = _session(client, agent.id)
    assert s.status_code == 200
    body = s.json()
    assert body["token"] and body["agent"]["greeting"] and body["agent"]["business"]
    llm.queue(say("We are open 9 to 7."), say("You're welcome."))
    r1 = _chat(client, body["token"], "When are you open?")
    assert r1.status_code == 200 and r1.json()["reply"] == "We are open 9 to 7."
    conv_id = r1.json()["conversation_id"]
    r2 = _chat(client, body["token"], "Thanks", conv_id)
    assert r2.json()["conversation_id"] == conv_id
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one()
    assert conv.channel == "widget" and conv.tenant_id == agent.tenant_id
    end = client.post(f"/api/v1/public/chat/{conv_id}/end", headers={"Authorization": f"Bearer {body['token']}"})
    assert end.status_code == 200


async def test_widget_respects_the_agent_switch(client, db):
    agent = await agent_for(db, "sunrise-realty")
    token = _session(client, agent.id).json()["token"]
    a = await db.get(Agent, agent.id)
    a.public_widget_enabled = False
    await db.commit()
    assert _session(client, agent.id).status_code == 404
    assert _chat(client, token, "hello").status_code == 404  # an already-issued token stops working too


async def test_widget_cannot_reach_another_agents_conversation(client, db, llm):
    realty = await agent_for(db, "sunrise-realty")
    hospital = await agent_for(db, "carewell-hospital")
    t_realty = _session(client, realty.id).json()["token"]
    t_hospital = _session(client, hospital.id).json()["token"]
    llm.queue(say("Hi from realty."))
    conv_id = _chat(client, t_realty, "hello").json()["conversation_id"]
    # The hospital widget token can't continue (or end) the realty chat.
    assert _chat(client, t_hospital, "what did they say?", conv_id).status_code == 404
    r = client.post(f"/api/v1/public/chat/{conv_id}/end", headers={"Authorization": f"Bearer {t_hospital}"})
    assert r.json().get("already_ended") is True
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one()
    assert conv.status == "active"  # untouched


async def test_widget_endpoints_reject_other_credentials(client, db):
    agent = await agent_for(db, "sunrise-realty")
    assert client.post("/api/v1/public/chat", json={"text": "hi"}).status_code == 401
    admin_jwt = login(client, "admin@sunrise.local")["Authorization"].removeprefix("Bearer ")
    assert _chat(client, admin_jwt, "hi").status_code == 401  # a login token is not a widget session
    tool_token = client.post(f"/api/v1/agents/{agent.id}/sarvam/token",
                             headers=login(client, "admin@sunrise.local")).json()["token"]
    assert _chat(client, tool_token, "hi").status_code == 401  # a Sarvam tool token is not a widget session
    # And a widget token can't use the admin API.
    token = _session(client, agent.id).json()["token"]
    assert client.get("/api/v1/agents", headers={"Authorization": f"Bearer {token}"}).status_code == 401


async def test_public_cors_is_open_but_admin_cors_is_not(client, db):
    agent = await agent_for(db, "sunrise-realty")
    pre = client.options("/api/v1/public/chat", headers={"Origin": "https://customer-site.example",
                                                         "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == "*"
    s = client.post(f"/api/v1/public/agents/{agent.id}/session", headers={"Origin": "https://customer-site.example"})
    assert s.headers["access-control-allow-origin"] == "*"
    admin = client.options("/api/v1/agents", headers={"Origin": "https://customer-site.example",
                                                      "Access-Control-Request-Method": "GET"})
    assert admin.headers.get("access-control-allow-origin") != "*"


async def test_widget_works_with_simple_requests_no_preflight(client, db, llm):
    """text/plain bodies with the token inside: what the widget sends so no CORS preflight is needed."""
    import json as _json

    agent = await agent_for(db, "sunrise-realty")
    hospital = await agent_for(db, "carewell-hospital")
    token = _session(client, agent.id).json()["token"]
    plain = {"Content-Type": "text/plain;charset=UTF-8"}
    llm.queue(say("Hello from Sunrise."))
    r = client.post("/api/v1/public/chat", headers=plain, content=_json.dumps({"token": token, "text": "hi"}))
    assert r.status_code == 200 and r.json()["reply"] == "Hello from Sunrise."
    conv_id = r.json()["conversation_id"]
    conv = (await db.execute(select(Conversation).where(Conversation.id == conv_id))).scalar_one()
    assert conv.tenant_id == agent.tenant_id and conv.agent_id == agent.id
    # A body token for another business's agent can't reach this one's chat, and junk tokens are refused.
    t_hospital = _session(client, hospital.id).json()["token"]
    r = client.post(f"/api/v1/public/chat/{conv_id}/end", headers=plain, content=_json.dumps({"token": t_hospital}))
    assert r.json().get("already_ended") is True
    assert client.post("/api/v1/public/chat", headers=plain, content='{"token": "junk", "text": "hi"}').status_code == 401
    assert client.post("/api/v1/public/chat", headers=plain, content="not json").status_code == 422
    r = client.post(f"/api/v1/public/chat/{conv_id}/end", headers=plain, content=_json.dumps({"token": token}))
    assert r.json() == {"ok": True}
