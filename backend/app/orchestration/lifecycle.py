"""Text conversation lifecycle (dashboard test chat, website widget): start, close, then analyse.

Voice calls run on hosted Sarvam Voice Agents; their records are created in app/api/sarvam_agents.py.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.agent import analyse_conversation
from app.context.manager import AgentBundle
from app.context.state import ConversationState, get_state_store
from app.models import AnalyticsEvent, Conversation


async def start_conversation(db: AsyncSession, bundle: AgentBundle, channel: str) -> ConversationState:
    agent = bundle.agent
    conv = Conversation(tenant_id=agent.tenant_id, agent_id=agent.id, channel=channel, language=agent.default_language)
    db.add(conv)
    await db.flush()
    db.add(AnalyticsEvent(tenant_id=agent.tenant_id, agent_id=agent.id, conversation_id=conv.id,
                          name="conversation_started", properties={"channel": channel}))
    await db.commit()
    state = ConversationState(conversation_id=conv.id, tenant_id=agent.tenant_id, agent_id=agent.id, channel=channel,
                              language=agent.default_language, languages_used=[agent.default_language])
    await get_state_store().put(state)
    return state


async def end_conversation(db: AsyncSession, state: ConversationState, reason: str = "ended_by_user") -> None:
    if state.ended:
        return
    state.ended = True
    conv = (await db.execute(select(Conversation).where(
        Conversation.tenant_id == state.tenant_id, Conversation.id == state.conversation_id))).scalar_one()
    now = datetime.now(UTC)
    conv.ended_at = now
    conv.language = state.language
    conv.languages_used = state.languages_used
    conv.intents = state.intents
    conv.customer_id = state.customer_id
    user_turns = sum(1 for m in state.history if m.get("role") == "user")
    if state.escalated:
        conv.status, conv.resolved = "escalated", False
    elif user_turns == 0:
        conv.status = "abandoned"
    else:
        conv.status = "completed"
        conv.resolved = state.consecutive_failures == 0
    db.add(AnalyticsEvent(tenant_id=state.tenant_id, agent_id=state.agent_id, conversation_id=state.conversation_id,
                          name="conversation_ended", properties={"status": conv.status, "reason": reason,
                                                                 "language": state.language}))
    await db.commit()
    await get_state_store().delete(state.conversation_id)
    # Post-call analyst: summary, sentiment, outcome, follow-ups. Best-effort; its row records any failure.
    await analyse_conversation(db, state.tenant_id, state.conversation_id)
