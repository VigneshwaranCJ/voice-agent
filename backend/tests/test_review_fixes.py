"""Regression tests for the codebase review findings (see docs/REVIEW_FIXES.md)."""

import asyncio

from sqlalchemy import select

from app.context.state import ConversationState
from app.core.config import get_settings
from app.core.ratelimit import RateLimitMiddleware
from app.industries.healthcare.module import emergency_guard
from app.knowledge.ingest import index_document
from app.knowledge.retrieval import _CACHE, search
from app.models import ConversationMessage, KnowledgeDocument, Lead, Tenant
from app.orchestration.engine import AgentEngine
from app.context.manager import load_agent_bundle
from app.tools.registry import _REGISTRY, ToolSpec, caller_affirmed
from tests.conftest import agent_for, call, login, new_engine, say, tool_results


# 1 — emergency patterns are word-bounded
def test_emergency_regex_word_boundaries():
    for benign in ("What are the insurance benefits?", "Does the plan cover outfits?", "profits and accidental-free",
                   "Is the hospital strokes-unit open"):
        assert not emergency_guard(benign), benign
    for urgent in ("my son is having fits", "he had a stroke", "she is suicidal", "Chest pain since morning",
                   "accident on the highway", "appa mayakkam aayitaru", "அம்மாவுக்கு நெஞ்சு வலி"):
        assert emergency_guard(urgent), urgent


def _state_with(reply: str) -> ConversationState:
    s = ConversationState(conversation_id="c", tenant_id="t", agent_id="a")
    s.history = [{"role": "assistant", "content": "Shall I book Dr Ramesh at 10 AM?"}, {"role": "user", "content": reply}]
    return s


# 7 — a question containing "confirm"/"right" is not a yes
def test_question_is_not_affirmation():
    for q in ("Can you confirm the time?", "is that right?", "what time is it, ok", "சரியா? எப்போ?", "kya time hai"):
        assert not caller_affirmed(_state_with(q)), q
    for yes in ("yes please", "ok confirm", "சரி பண்ணுங்க", "haan theek hai"):
        assert caller_affirmed(_state_with(yes)), yes


# 3 — a failing tool's rollback must not drop the caller's message
async def test_tool_failure_keeps_user_message(db, llm):
    spec = _REGISTRY["search_properties"]

    async def broken(ctx, args):
        raise ConnectionError("db down")

    _REGISTRY["search_properties"] = ToolSpec(spec.name, spec.description, spec.params, broken, spec.industry)
    try:
        engine, state = await new_engine(db, "sunrise-realty", llm)
        llm.queue(call("search_properties", city="Coimbatore"), say("Sorry"))
        await engine.handle_turn(state, "2BHK in Coimbatore please", "en-IN")
        msgs = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == state.conversation_id))).scalars().all()
        assert "2BHK in Coimbatore please" in [m.content for m in msgs if m.role == "user"]
    finally:
        _REGISTRY["search_properties"] = spec


# 4 — a timed-out tool's partial writes are rolled back, and the session keeps working
async def test_tool_timeout_rolls_back_partial_writes(db, llm, monkeypatch):
    spec = _REGISTRY["search_properties"]
    monkeypatch.setattr(get_settings(), "tool_timeout_seconds", 0.2)

    async def slow(ctx, args):
        ctx.db.add(Lead(tenant_id=ctx.tenant_id, name="ghost", phone="9000000000", interest="x"))
        await ctx.db.flush()
        await asyncio.sleep(5)

    _REGISTRY["search_properties"] = ToolSpec(spec.name, spec.description, spec.params, slow, spec.industry)
    try:
        engine, state = await new_engine(db, "sunrise-realty", llm)
        llm.queue(call("search_properties", city="Coimbatore"), say("Sorry, slow system"))
        res = await engine.handle_turn(state, "2BHK", "en-IN")
        assert tool_results(llm.calls[-1])[0]["retryable"] and res.reply == "Sorry, slow system"
        assert not (await db.execute(select(Lead).where(Lead.name == "ghost"))).scalars().all()
    finally:
        _REGISTRY["search_properties"] = spec


# 9 — changing industry resets tools; the engine never exposes another industry's tools
async def test_industry_change_resets_tools(client, db, llm):
    re_agent = await agent_for(db, "sunrise-realty")
    h = login(client, "admin@sunrise.local")
    r = client.put(f"/api/v1/agents/{re_agent.id}", headers=h, json={"name": re_agent.name, "industry": "healthcare"})
    assert r.status_code == 200, r.text
    tools = r.json()["config"]["enabled_tools"]
    assert "book_appointment" in tools and "search_properties" not in tools

    agent_id = re_agent.id
    db.expire_all()  # the API wrote through another session
    bundle = await load_agent_bundle(db, agent_id)
    bundle.config.enabled_tools = ["search_properties", "search_doctors"]  # simulate a stale config
    engine = AgentEngine(db, bundle, llm)
    assert engine.enabled_tools == ["search_doctors"]


# 10 — retrieval index is cached but picks up new/changed documents
async def test_retrieval_cache_invalidates_on_new_document(db):
    t = (await db.execute(select(Tenant).where(Tenant.slug == "sunrise-realty"))).scalar_one()
    assert not await search(db, tenant_id=t.id, agent_id=None, query="helipad rooftop")
    assert (t.id, None) in _CACHE
    doc = KnowledgeDocument(tenant_id=t.id, title="Amenities", source_type="text",
                            raw_text="Every tower has a rooftop helipad for residents.")
    db.add(doc)
    await db.flush()
    await index_document(db, doc)
    await db.commit()
    hits = await search(db, tenant_id=t.id, agent_id=None, query="helipad rooftop")
    assert hits and "helipad" in hits[0].content


# 6 — the rate limiter keeps only the current window (bounded memory)
async def test_rate_limiter_memory_is_bounded():
    rl = RateLimitMiddleware(app=None, per_minute=5)
    rl.window, rl.counts = 1, {f"10.0.0.{i}": 1 for i in range(1000)}

    class Req:
        class url:
            path = "/api/v1/x"
        scope = {"type": "http"}
        client = type("C", (), {"host": "1.2.3.4"})()

    async def nxt(_):
        return "ok"

    assert await rl.dispatch(Req(), nxt) == "ok"
    assert rl.counts == {"1.2.3.4": 1}
