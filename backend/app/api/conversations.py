from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, Principal, audit, tenant_scope
from app.core.timeutil import as_utc
from app.models import (
    Appointment, BusinessProfile, CallSession, Conversation, ConversationMessage, EscalationRecord, Lead, ToolExecution,
)
from app.schemas.api import ConversationOut, EscalationUpdateIn, LeadUpdateIn, MessageOut

router = APIRouter(tags=["calls"])


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(agent_id: str | None = None, status: str | None = None, channel: str | None = None,
                             language: str | None = None, q: str | None = Query(None, max_length=200),
                             date_from: datetime | None = None, date_to: datetime | None = None,
                             limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                             p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    """Calls for the caller's business, newest first. `q` searches summaries and transcripts."""
    stmt = select(Conversation).where(Conversation.tenant_id == p.tenant_id)
    if agent_id:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if language:
        stmt = stmt.where(Conversation.language == language)
    if date_from:
        stmt = stmt.where(Conversation.created_at >= _utc(date_from))
    if date_to:
        stmt = stmt.where(Conversation.created_at < _utc(date_to))
    if q and q.strip():
        like = f"%{q.strip()}%"
        in_transcript = select(ConversationMessage.id).where(
            ConversationMessage.tenant_id == p.tenant_id, ConversationMessage.conversation_id == Conversation.id,
            ConversationMessage.content.ilike(like)).exists()
        stmt = stmt.where(Conversation.summary.ilike(like) | in_transcript)
    return (await db.execute(stmt.order_by(Conversation.created_at.desc()).limit(limit).offset(offset))).scalars().all()


def _utc(dt: datetime) -> datetime:
    """Aware UTC bound: correct for PostgreSQL timestamptz; SQLite's DateTime storage ignores the zone."""
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.get("/conversations/{conv_id}")
async def conversation_detail(conv_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    conv = (await db.execute(select(Conversation).where(Conversation.tenant_id == p.tenant_id,
                                                        Conversation.id == conv_id))).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    msgs = (await db.execute(select(ConversationMessage).where(
        ConversationMessage.tenant_id == p.tenant_id, ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.created_at))).scalars().all()
    tools = (await db.execute(select(ToolExecution).where(
        ToolExecution.tenant_id == p.tenant_id, ToolExecution.conversation_id == conv_id)
        .order_by(ToolExecution.created_at))).scalars().all()
    escalations = (await db.execute(select(EscalationRecord).where(
        EscalationRecord.tenant_id == p.tenant_id, EscalationRecord.conversation_id == conv_id))).scalars().all()
    call = (await db.execute(select(CallSession).where(
        CallSession.tenant_id == p.tenant_id, CallSession.conversation_id == conv_id))).scalars().first()
    return {
        "conversation": ConversationOut.model_validate(conv),
        "messages": [MessageOut.model_validate(m) for m in msgs],
        "tool_executions": [{"tool": t.tool_name, "status": t.status, "arguments": t.arguments, "result": t.result,
                             "error": t.error, "duration_ms": t.duration_ms, "at": t.created_at} for t in tools],
        "escalations": [{"id": e.id, "reason": e.reason, "priority": e.priority, "summary": e.summary,
                         "status": e.status, "at": e.created_at} for e in escalations],
        "call": {"duration_seconds": call.duration_seconds, "status": call.status, "end_reason": call.end_reason,
                 "recording_consent": call.recording_consent} if call else None,
    }


@router.get("/escalations")
async def list_escalations(status: str | None = None, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    q = select(EscalationRecord).where(EscalationRecord.tenant_id == p.tenant_id)
    if status:
        q = q.where(EscalationRecord.status == status)
    rows = (await db.execute(q.order_by(EscalationRecord.created_at.desc()).limit(200))).scalars().all()
    return [_escalation_out(e) for e in rows]


def _escalation_out(e: EscalationRecord) -> dict:
    return {"id": e.id, "conversation_id": e.conversation_id, "reason": e.reason, "priority": e.priority,
            "summary": e.summary, "status": e.status, "assigned_to": e.assigned_to,
            "notes": (e.context or {}).get("notes", ""), "context": e.context, "at": e.created_at}


@router.patch("/escalations/{escalation_id}")
async def update_escalation(escalation_id: str, body: EscalationUpdateIn, request: Request,
                            p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    e = (await db.execute(select(EscalationRecord).where(
        EscalationRecord.tenant_id == p.tenant_id, EscalationRecord.id == escalation_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Escalation not found")
    sent = body.model_fields_set
    if "assigned_to" in sent:
        e.assigned_to = (body.assigned_to or "").strip() or None
        if e.assigned_to and e.status == "open" and "status" not in sent:
            e.status = "assigned"  # assigning someone moves it out of the unowned queue
    if body.status is not None:
        e.status = body.status
    if body.notes is not None:
        e.context = {**(e.context or {}), "notes": body.notes}  # new dict so the JSON change is saved
    await audit(db, request, p, "update", "escalation", e.id, status=e.status, assigned_to=e.assigned_to)
    await db.commit()
    return _escalation_out(e)


@router.get("/leads")
async def list_leads(p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    rows = (await db.execute(select(Lead).where(Lead.tenant_id == p.tenant_id)
                             .order_by(Lead.created_at.desc()).limit(200))).scalars().all()
    return [_lead_out(r) for r in rows]


def _lead_out(r: Lead) -> dict:
    return {"id": r.id, "name": r.name, "phone": r.phone, "interest": r.interest, "budget": r.budget,
            "location_preference": r.location_preference, "status": r.status, "assigned_to": r.assigned_to,
            "notes": (r.details or {}).get("notes", ""), "conversation_id": r.conversation_id, "at": r.created_at}


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdateIn, request: Request, p: Principal = Depends(tenant_scope),
                      db: AsyncSession = DB):
    r = (await db.execute(select(Lead).where(Lead.tenant_id == p.tenant_id, Lead.id == lead_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Lead not found")
    if body.status is not None:
        r.status = body.status
    if "assigned_to" in body.model_fields_set:
        r.assigned_to = (body.assigned_to or "").strip() or None
    if body.notes is not None:
        r.details = {**(r.details or {}), "notes": body.notes}  # new dict so the JSON change is saved
    await audit(db, request, p, "update", "lead", r.id, status=r.status, assigned_to=r.assigned_to)
    await db.commit()
    return _lead_out(r)


@router.get("/appointments")
async def list_appointments(p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    rows = (await db.execute(select(Appointment).where(Appointment.tenant_id == p.tenant_id)
                             .order_by(Appointment.starts_at.desc()).limit(200))).scalars().all()
    return [{"id": r.id, "kind": r.kind, "resource_type": r.resource_type, "resource_id": r.resource_id,
             "starts_at": r.starts_at, "status": r.status, "contact_name": r.contact_name,
             "contact_phone": r.contact_phone, "notes": r.notes} for r in rows]


@router.get("/analytics/overview")
async def analytics_overview(days: int = Query(30, le=365), p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    since = datetime.now(UTC) - timedelta(days=days)
    t = p.tenant_id
    conv_base = select(Conversation).where(Conversation.tenant_id == t, Conversation.created_at >= since).subquery()

    async def scalar(q):
        return (await db.execute(q)).scalar() or 0

    total = await scalar(select(func.count()).select_from(conv_base))
    by_status = dict((await db.execute(select(conv_base.c.status, func.count()).group_by(conv_base.c.status))).all())
    by_lang = dict((await db.execute(select(conv_base.c.language, func.count()).group_by(conv_base.c.language))).all())
    by_channel = dict((await db.execute(select(conv_base.c.channel, func.count()).group_by(conv_base.c.channel))).all())
    resolved = await scalar(select(func.count()).select_from(conv_base).where(conv_base.c.resolved.is_(True)))
    calls = select(CallSession).where(CallSession.tenant_id == t, CallSession.started_at >= since).subquery()
    call_total = await scalar(select(func.count()).select_from(calls))
    missed = await scalar(select(func.count()).select_from(calls).where(calls.c.status == "missed"))
    avg_dur = await scalar(select(func.avg(calls.c.duration_seconds)))
    csat = await scalar(select(func.avg(conv_base.c.satisfaction)))
    tools = (await db.execute(select(ToolExecution.tool_name, func.count()).where(
        ToolExecution.tenant_id == t, ToolExecution.created_at >= since).group_by(ToolExecution.tool_name)
        .order_by(func.count().desc()).limit(10))).all()
    # Days and hours in the business's own timezone (timestamps are stored in UTC).
    tz_name = (await db.execute(select(BusinessProfile.timezone).where(BusinessProfile.tenant_id == t))).scalar() or "Asia/Kolkata"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz, tz_name = ZoneInfo("UTC"), "UTC"
    local = [as_utc(c).astimezone(tz) for (c,) in (await db.execute(select(conv_base.c.created_at))).all()]
    per_day = Counter(d.date().isoformat() for d in local)
    per_hour = Counter(d.hour for d in local)
    leads = dict((await db.execute(select(Lead.status, func.count()).where(
        Lead.tenant_id == t, Lead.created_at >= since).group_by(Lead.status))).all())
    escalations = dict((await db.execute(select(EscalationRecord.status, func.count()).where(
        EscalationRecord.tenant_id == t, EscalationRecord.created_at >= since).group_by(EscalationRecord.status))).all())
    ended = sum(v for k, v in by_status.items() if k != "active")
    return {
        "days": days, "total_conversations": total, "total_calls": call_total,
        "answered_calls": call_total - missed, "missed_calls": missed,
        "avg_call_duration_seconds": round(float(avg_dur), 1) if avg_dur else 0,
        "resolved": resolved, "resolution_rate": round(resolved / ended, 3) if ended else None,
        "escalated": by_status.get("escalated", 0), "by_status": by_status,
        "languages": {k or "unknown": v for k, v in by_lang.items()}, "channels": by_channel,
        "customer_satisfaction": round(float(csat), 2) if csat else None,
        "top_tools": [{"tool": n, "count": c} for n, c in tools],
        "daily": [{"date": d, "count": c} for d, c in sorted(per_day.items())],
        "hours": [per_hour.get(h, 0) for h in range(24)], "timezone": tz_name,
        "leads": {"total": sum(leads.values()), "by_status": leads},
        "escalations": {"total": sum(escalations.values()), "by_status": escalations},
    }
