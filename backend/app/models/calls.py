from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin, utcnow


class Conversation(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="web_voice")  # web_voice | web_text | phone
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | completed | escalated | abandoned
    language: Mapped[str | None] = mapped_column(String(10))
    languages_used: Mapped[list] = mapped_column(JSON, default=list)
    intents: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool | None] = mapped_column(Boolean)
    satisfaction: Mapped[int | None] = mapped_column(Integer)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessage(IdMixin, TenantMixin, Base):
    __tablename__ = "conversation_messages"
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool | system
    content: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(10))
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CallSession(IdMixin, TenantMixin, Base):
    __tablename__ = "call_sessions"
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="web_voice")
    caller_number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress | completed | failed | missed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    recording_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_url: Mapped[str | None] = mapped_column(String(500))
    end_reason: Mapped[str | None] = mapped_column(String(60))
    # The provider's id for this call, e.g. a Sarvam Voice Agents interaction id ("20261120/abc..."), used to fetch
    # its transcript later.
    external_ref: Mapped[str | None] = mapped_column(String(200), index=True)


class ToolExecution(IdMixin, TenantMixin, Base):
    __tablename__ = "tool_executions"
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(80), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # success | error | timeout | denied
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EscalationRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "escalation_records"
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(40))  # customer_request | emergency | distress | unresolved | policy | verification
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # normal | high | critical
    summary: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | assigned | resolved
    assigned_to: Mapped[str | None] = mapped_column(String(200))


class AnalyticsEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "analytics_events"
    agent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(200))  # user id, "agent:<id>", "system"
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
