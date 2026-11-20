from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, Principal, audit, get_principal, require_role, tenant_admin_scope, tenant_scope
from app.industries.registry import INDUSTRIES, PLANNED
from app.models import BusinessProfile, Tenant, User
from app.schemas.api import BusinessProfileIn, BusinessProfileOut, TenantIn, TenantOut
from app.security.crypto import hash_password

router = APIRouter(tags=["tenants"])


@router.get("/industries")
async def industries():
    return {"available": [{"key": m.key, "label": m.label, "default_tools": m.default_tools} for m in INDUSTRIES.values()],
            "planned": [{"key": k, "label": v} for k, v in PLANNED.items()]}


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(p: Principal = Depends(get_principal), db: AsyncSession = DB):
    q = select(Tenant).order_by(Tenant.created_at)
    if not p.is_platform_admin:
        q = q.where(Tenant.id == p.home_tenant_id)
    return (await db.execute(q)).scalars().all()


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(body: TenantIn, request: Request, p: Principal = Depends(require_role("platform_admin")),
                        db: AsyncSession = DB):
    if (await db.execute(select(Tenant).where(Tenant.slug == body.slug))).scalar_one_or_none():
        raise HTTPException(409, "Slug already in use")
    t = Tenant(name=body.name, slug=body.slug, industry=body.industry)
    db.add(t)
    await db.flush()
    db.add(BusinessProfile(tenant_id=t.id, display_name=body.name))
    if body.admin_email and body.admin_password:
        if (await db.execute(select(User).where(User.email == body.admin_email.lower()))).scalar_one_or_none():
            raise HTTPException(409, "Admin email already registered")
        db.add(User(tenant_id=t.id, email=body.admin_email.lower(), full_name=f"{body.name} Admin",
                    password_hash=hash_password(body.admin_password), role="tenant_admin"))
    await audit(db, request, p, "create", "tenant", t.id, name=t.name)
    await db.commit()
    return t


@router.get("/business-profile", response_model=BusinessProfileOut)
async def get_profile(p: Principal = Depends(tenant_scope), db: AsyncSession = DB):
    bp = (await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == p.tenant_id))).scalar_one_or_none()
    if not bp:
        raise HTTPException(404, "No business profile")
    return bp


@router.put("/business-profile", response_model=BusinessProfileOut)
async def update_profile(body: BusinessProfileIn, request: Request, p: Principal = Depends(tenant_admin_scope),
                         db: AsyncSession = DB):
    bp = (await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == p.tenant_id))).scalar_one_or_none()
    if not bp:
        bp = BusinessProfile(tenant_id=p.tenant_id, display_name=body.display_name)
        db.add(bp)
    for k, v in body.model_dump().items():
        setattr(bp, k, v)
    await audit(db, request, p, "update", "business_profile", bp.id)
    await db.commit()
    return bp
