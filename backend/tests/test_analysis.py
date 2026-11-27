"""Post-call analyst agent: reason → validate → self-correct → verify → act, plus its API and tenant isolation."""

import json

from sqlalchemy import select

from app.analysis.agent import SUBMIT, analyse_conversation, submit_tool
from app.llm.base import LLMResponse, ToolCall
from app.llm.sarvam import set_llm
from app.models import ConversationAnalysis, EscalationRecord
from app.orchestration.lifecycle import end_conversation
from tests.conftest import agent_for, login, new_engine, say

GOOD = dict(
    summary="Caller asked about 2BHK prices in Saravanampatti and got the price range. No booking was made.",
    sentiment="positive", sentiment_score=0.6, sentiment_trend="improving", emotions=["curious", "pleased"],
    outcome="information_only", resolved=True, topics=["pricing"], key_quotes=["that sounds good"],
    needs_human=False, follow_ups=[], agent_issues=[],
)


def submit(**overrides) -> LLMResponse:
    args = {**GOOD, **overrides}
    return LLMResponse(content="", tool_calls=[ToolCall(id="c_submit", name=SUBMIT, arguments=json.dumps(args))])


async def _ended_chat(db, llm, slug="sunrise-realty", caller="What is the price of a 2BHK? Okay, that sounds good."):
    """A short text chat, ended. The analyst's LLM reply must be queued before calling this."""
    engine, state = await new_engine(db, slug, llm)
    llm.script.insert(0, say("A 2BHK at Sunrise Meadows is 52 to 61 lakh."))
    await engine.handle_turn(state, caller)
    await end_conversation(db, state)
    return state


async def _analysis(db, conv_id) -> ConversationAnalysis:
    db.expire_all()
    return (await db.execute(select(ConversationAnalysis).where(
        ConversationAnalysis.conversation_id == conv_id))).scalar_one()


async def test_ending_a_chat_runs_the_analyst(db, llm):
    llm.queue(submit())
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "done" and a.attempts == 1
    assert (a.sentiment, a.outcome, a.resolved, a.sentiment_trend) == ("positive", "information_only", True, "improving")
    assert a.key_quotes == ["that sounds good"] and a.checks == []
    # The analyst got the transcript and the submit tool, and its summary became the conversation's summary.
    brief = llm.calls[-1][1]["content"]
    assert "CALLER: What is the price of a 2BHK?" in brief and "AGENT: A 2BHK" in brief
    assert llm.tools[-1][0]["function"]["name"] == SUBMIT
    from app.models import Conversation
    conv = await db.get(Conversation, state.conversation_id)
    assert conv.summary == GOOD["summary"]


async def test_invalid_submission_is_sent_back_and_corrected(db, llm):
    llm.queue(submit(sentiment="angry", sentiment_score=3), submit())
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "done" and a.attempts == 2
    retry = llm.calls[-1]
    feedback = json.loads(retry[-1]["content"])
    assert retry[-1]["role"] == "tool" and feedback["ok"] is False
    assert "sentiment" in feedback["error"] and "sentiment_score" in feedback["error"]
    # Sarvam rule: tool messages present → tools are sent too.
    assert llm.tools[-1]


async def test_plain_text_reply_is_nudged_then_json_content_accepted(db, llm):
    llm.queue(say("The caller seemed happy."), say("```json\n" + json.dumps(GOOD) + "\n```"))
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "done" and a.attempts == 2
    assert llm.calls[-1][-1]["role"] == "user" and SUBMIT in llm.calls[-1][-1]["content"]


async def test_gives_up_after_three_bad_attempts_without_failing_the_call(db, llm):
    llm.queue(say("no"), say("still no"), say("nope"))
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "failed" and a.attempts == 3 and a.error and a.sentiment is None


async def test_llm_error_is_recorded_not_raised(db, llm):
    llm.queue(RuntimeError("model down"))
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "failed" and "model down" in a.error


async def test_facts_override_the_model(db, llm):
    llm.queue(submit(outcome="booked", resolved=True, key_quotes=["that sounds good", "I booked a visit for Sunday"]))
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    assert a.outcome == "unresolved" and a.resolved is False
    assert a.key_quotes == ["that sounds good"]  # the invented quote is dropped
    assert any("booking" in c for c in a.checks) and any("quote" in c for c in a.checks)


async def test_quote_matching_ignores_case_and_punctuation(db, llm):
    llm.queue(submit(key_quotes=["Okay, that sounds GOOD!"]))
    state = await _ended_chat(db, llm)
    assert (await _analysis(db, state.conversation_id)).key_quotes == ["Okay, that sounds GOOD!"]


async def test_needs_human_opens_one_follow_up(db, llm, client):
    llm.queue(submit(sentiment="negative", sentiment_score=-0.7, outcome="unresolved", resolved=False, needs_human=True,
                     follow_ups=[{"action": "Call back with the exact possession date", "priority": "high"}]))
    state = await _ended_chat(db, llm)
    a = await _analysis(db, state.conversation_id)
    esc = (await db.execute(select(EscalationRecord).where(
        EscalationRecord.conversation_id == state.conversation_id))).scalars().all()
    assert len(esc) == 1 and a.escalation_id == esc[0].id
    assert (esc[0].reason, esc[0].priority, esc[0].tenant_id) == ("follow_up", "high", state.tenant_id)
    assert "possession date" in esc[0].summary and esc[0].context["source"] == "post_call_analysis"
    # A re-run doesn't open a second follow-up.
    llm.queue(submit(needs_human=True, sentiment="negative", sentiment_score=-0.5, outcome="unresolved", resolved=False))
    h = login(client, "admin@sunrise.local")
    assert client.post(f"/api/v1/conversations/{state.conversation_id}/analysis", headers=h).status_code == 200
    db.expire_all()
    assert len((await db.execute(select(EscalationRecord).where(
        EscalationRecord.conversation_id == state.conversation_id))).scalars().all()) == 1


async def test_follow_up_can_be_turned_off(db, llm, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "analysis_auto_follow_up", False)
    llm.queue(submit(needs_human=True))
    state = await _ended_chat(db, llm)
    assert (await _analysis(db, state.conversation_id)).escalation_id is None
    assert not (await db.execute(select(EscalationRecord).where(
        EscalationRecord.conversation_id == state.conversation_id))).scalars().all()


async def test_silent_conversation_is_skipped_without_an_llm_call(db, llm):
    engine, state = await new_engine(db, "sunrise-realty", llm)
    await end_conversation(db, state)
    a = await _analysis(db, state.conversation_id)
    assert (a.status, a.outcome) == ("skipped", "abandoned") and llm.calls == []


async def test_not_configured_without_a_sarvam_key(db, llm):
    llm.queue(say("Hello."))
    engine, state = await new_engine(db, "sunrise-realty", llm)
    await engine.handle_turn(state, "hello")
    set_llm(None)  # back to the real Sarvam provider, which has no key in tests
    await end_conversation(db, state)
    a = await _analysis(db, state.conversation_id)
    assert a.status == "not_configured" and "SARVAM_API_KEY" in a.error


async def test_submit_schema_is_self_contained():
    params = submit_tool()["function"]["parameters"]
    assert "$defs" not in json.dumps(params) and "$ref" not in json.dumps(params)
    assert params["properties"]["follow_ups"]["items"]["properties"]["priority"]["enum"] == ["low", "normal", "high"]


async def test_api_shows_analysis_and_filters_by_sentiment(db, llm, client):
    llm.queue(submit(sentiment="negative", sentiment_score=-0.4, needs_human=False))
    state = await _ended_chat(db, llm)
    h = login(client, "admin@sunrise.local")
    detail = client.get(f"/api/v1/conversations/{state.conversation_id}", headers=h).json()
    assert detail["analysis"]["status"] == "done" and detail["analysis"]["sentiment"] == "negative"
    rows = client.get("/api/v1/conversations", params={"sentiment": "negative"}, headers=h).json()
    assert [r["id"] for r in rows] == [state.conversation_id] and rows[0]["sentiment"] == "negative"
    assert client.get("/api/v1/conversations", params={"sentiment": "positive"}, headers=h).json() == []
    assert client.get("/api/v1/conversations", params={"sentiment": "furious"}, headers=h).status_code == 422
    overview = client.get("/api/v1/analytics/overview", headers=h).json()["sentiment"]
    assert overview["analysed"] == 1 and overview["by_label"] == {"negative": 1} and overview["average_score"] == -0.4


async def test_rerun_refuses_an_active_conversation(db, llm, client):
    engine, state = await new_engine(db, "sunrise-realty", llm)
    h = login(client, "admin@sunrise.local")
    assert client.post(f"/api/v1/conversations/{state.conversation_id}/analysis", headers=h).status_code == 409


async def test_analysis_tenant_isolation(db, llm, client):
    llm.queue(submit())
    state = await _ended_chat(db, llm)  # a Sunrise Realty conversation
    other = await agent_for(db, "carewell-hospital")
    h = login(client, "admin@carewell.local")
    assert client.post(f"/api/v1/conversations/{state.conversation_id}/analysis", headers=h).status_code == 404
    assert client.get(f"/api/v1/conversations/{state.conversation_id}", headers=h).status_code == 404
    assert client.get("/api/v1/conversations", params={"sentiment": "positive"}, headers=h).json() == []
    assert client.get("/api/v1/analytics/overview", headers=h).json()["sentiment"]["analysed"] == 0
    # The analyst itself only reads a conversation through its own tenant.
    assert await analyse_conversation(db, other.tenant_id, state.conversation_id, llm=llm) is None
