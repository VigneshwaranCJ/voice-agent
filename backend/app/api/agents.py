from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, Principal, audit, tenant_admin_scope, tenant_scope
from app.industries.registry import get_industry
from app.models import Agent, AgentConfiguration
from app.schemas.api import AgentConfigIn, AgentConfigOut, AgentDetailOut, AgentIn, AgentOut
from app.tools.registry import all_tools

router = APIRouter(prefix="/agents", tags=["agents"])


async def _get_agent(db: AsyncSession, p: Principal, agent_id: str) -> Agent:
    a = (await db.execute(select(Agent).where(Agent.tenant_id == p.tenant_id, Agent.id == agent_id))).unique().scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Agent not found")
    return a


async def _active_config(db: AsyncSession, a: Agent) -> AgentConfiguration | None:
    return (await db.execute(select(AgentConfiguration).where(
        AgentConfiguration.tenant_id == a.tenant_id, AgentConfiguration.agent_id == a.id,
        AgentConfiguration.is_active.is_(True)).order_by(AgentConfiguration.version.desc()))).scalars().first()


def _validate_tools(tools: list[str], industry: str) -> None:
    allowed = set(get_industry(industry).default_tools)
    bad = [t for t in tools if t not in allowed]
    if bad:
        raise HTTPException(422, f"Tools not available for industry '{industry}': {bad}")


async def _detail(db: AsyncSession, a: Agent) -> AgentDetailOut:
    cfg = await _active_config(db, a)
    return AgentDetailOut(**AgentOut.model_validate(a).model_dump(),
                          config=AgentConfigOut.model_validate(cfg) if cfg else None)


@router.get("/tools/catalog")
async def tool_catalog():
    return [{"name": t.name, "description": t.description, "industry": t.industry,
             "requires_confirmation": t.requires_confirmation, "is_write": t.is_write,
             "parameters": t.openai_schema()["function"]["parameters"]} for t in all_tools()]


@router.get("", response_model=list[AgentOut])
async def list_agents(p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    return (await db.execute(select(Agent).where(Agent.tenant_id == p.tenant_id).order_by(Agent.created_at))).unique().scalars().all()


@router.post("", response_model=AgentDetailOut, status_code=201)
async def create_agent(body: AgentIn, request: Request, p: Principal = Depends(tenant_admin_scope), db: AsyncSession = DB):
    cfg_in = body.config or AgentConfigIn()
    if not cfg_in.enabled_tools:
        cfg_in.enabled_tools = get_industry(body.industry).default_tools
    _validate_tools(cfg_in.enabled_tools, body.industry)
    a = Agent(tenant_id=p.tenant_id, **body.model_dump(exclude={"config"}))
    db.add(a)
    await db.flush()
    db.add(AgentConfiguration(tenant_id=p.tenant_id, agent_id=a.id, version=1, **cfg_in.model_dump()))
    await audit(db, request, p, "create", "agent", a.id, name=a.name)
    await db.commit()
    await db.refresh(a)
    return await _detail(db, a)


@router.get("/{agent_id}", response_model=AgentDetailOut)
async def get_agent(agent_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    return await _detail(db, await _get_agent(db, p, agent_id))


@router.put("/{agent_id}", response_model=AgentDetailOut)
async def update_agent(agent_id: str, body: AgentIn, request: Request, p: Principal = Depends(tenant_admin_scope),
                       db: AsyncSession = DB):
    a = await _get_agent(db, p, agent_id)
    industry_changed = body.industry != a.industry
    for k, v in body.model_dump(exclude={"config"}).items():
        setattr(a, k, v)
    if body.config:
        await _new_config_version(db, p, a, body.config)
    elif industry_changed:
        # Old config's tools belong to the previous industry: start a new version with this industry's defaults.
        current = await _active_config(db, a)
        cfg_in = AgentConfigIn.model_validate(
            {**AgentConfigOut.model_validate(current).model_dump(), "enabled_tools": []} if current else {})
        await _new_config_version(db, p, a, cfg_in)
    await audit(db, request, p, "update", "agent", a.id)
    await db.commit()
    await db.refresh(a)
    return await _detail(db, a)


async def _new_config_version(db: AsyncSession, p: Principal, a: Agent, cfg_in: AgentConfigIn) -> AgentConfiguration:
    if not cfg_in.enabled_tools:
        cfg_in.enabled_tools = get_industry(a.industry).default_tools
    _validate_tools(cfg_in.enabled_tools, a.industry)
    current = await _active_config(db, a)
    cfg = AgentConfiguration(tenant_id=p.tenant_id, agent_id=a.id, version=(current.version + 1) if current else 1,
                             **cfg_in.model_dump())
    db.add(cfg)
    return cfg


@router.put("/{agent_id}/config", response_model=AgentConfigOut)
async def update_config(agent_id: str, body: AgentConfigIn, request: Request,
                        p: Principal = Depends(tenant_admin_scope), db: AsyncSession = DB):
    a = await _get_agent(db, p, agent_id)
    cfg = await _new_config_version(db, p, a, body)
    await audit(db, request, p, "update_config", "agent", a.id, version=cfg.version)
    await db.commit()
    return cfg


@router.get("/{agent_id}/config/history", response_model=list[AgentConfigOut])
async def config_history(agent_id: str, p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    a = await _get_agent(db, p, agent_id)
    return (await db.execute(select(AgentConfiguration).where(
        AgentConfiguration.tenant_id == p.tenant_id, AgentConfiguration.agent_id == a.id)
        .order_by(AgentConfiguration.version.desc()))).scalars().all()
