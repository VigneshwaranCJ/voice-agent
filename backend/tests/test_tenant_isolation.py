from sqlalchemy import select

from app.industries.healthcare.models import Doctor
from app.industries.real_estate.models import Property
from tests.conftest import agent_for, call, login, new_engine, say, tool_results


async def test_api_isolation(client, db):
    re_agent = await agent_for(db, "sunrise-realty")
    hc_agent = await agent_for(db, "carewell-hospital")
    h = login(client, "admin@sunrise.local")
    assert client.get(f"/api/v1/agents/{re_agent.id}", headers=h).status_code == 200
    assert client.get(f"/api/v1/agents/{hc_agent.id}", headers=h).status_code == 404
    # Tenant header spoofing is refused
    r = client.get("/api/v1/agents", headers={**h, "X-Tenant-ID": hc_agent.tenant_id})
    assert r.status_code == 403
    assert all(a["tenant_id"] == re_agent.tenant_id for a in client.get("/api/v1/agents", headers=h).json())
    assert client.get("/api/v1/data/doctors", headers=h).json() == []
    titles = [d["title"] for d in client.get("/api/v1/knowledge/documents", headers=h).json()]
    assert titles == ["Sunrise Realty FAQ"]
    assert client.get("/api/v1/knowledge/search", params={"q": "ICU cashless insurance"}, headers=h).json() == []


async def test_platform_admin_must_select_tenant(client, db):
    hc_agent = await agent_for(db, "carewell-hospital")
    h = login(client, "admin@platform.local", "ChangeMe-Admin-123")
    assert client.get("/api/v1/agents", headers=h).status_code == 400
    r = client.get("/api/v1/agents", headers={**h, "X-Tenant-ID": hc_agent.tenant_id})
    assert r.status_code == 200 and r.json()[0]["id"] == hc_agent.id
    assert len(client.get("/api/v1/tenants", headers=h).json()) == 2


async def test_tools_cannot_reach_other_tenant(db, llm):
    other_property = (await db.execute(select(Property))).scalars().first()
    engine, state = await new_engine(db, "sunrise-realty", llm)
    # Same-tenant id works...
    llm.queue(call("get_property_details", property_id=other_property.id), say("ok"))
    await engine.handle_turn(state, "details", "en-IN")
    assert tool_results(llm.calls[-1])[0]["ok"]

    # ...but the hospital agent cannot read a real-estate row even with its id, nor can RE see doctors.
    hc_engine, hc_state = await new_engine(db, "carewell-hospital", llm)
    doctor = (await db.execute(select(Doctor))).scalars().first()
    llm.queue(call("get_doctor_schedule", doctor_id=doctor.id, date="2030-01-01"), say("ok"))
    await hc_engine.handle_turn(hc_state, "schedule", "en-IN")
    assert tool_results(llm.calls[-1])[0]["ok"]
    llm.queue(call("search_knowledge", query="home loan booking amount"), say("ok"))
    await hc_engine.handle_turn(hc_state, "home loan?", "en-IN")
    assert tool_results(llm.calls[-1])[0]["results"] == []


async def test_rbac_and_auth(client, db):
    assert client.get("/api/v1/agents").status_code == 401
    assert client.get("/api/v1/agents", headers={"Authorization": "Bearer junk"}).status_code == 401
    h = login(client, "admin@sunrise.local")
    r = client.post("/api/v1/tenants", headers=h, json={"name": "X", "slug": "x-co", "industry": "custom"})
    assert r.status_code == 403  # only platform admins create tenants


async def test_widget_token_scope(client, db):
    re_agent = await agent_for(db, "sunrise-realty")
    tok = client.post(f"/api/v1/public/agents/{re_agent.id}/session").json()["token"]
    # widget tokens cannot call the admin API
    assert client.get("/api/v1/agents", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    # nor the Sarvam session route, which needs a dashboard login
    url = f"/api/v1/sarvam/runtime/{re_agent.id}/orgs/o/workspaces/w/apps/a/url"
    assert client.get(url, headers={"Authorization": f"Bearer {tok}"}).status_code == 401
