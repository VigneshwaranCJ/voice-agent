"""Auth / tenancy dependencies."""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import AuditLog, User
from app.security.crypto import decode_token

bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {"tenant_agent": 1, "tenant_admin": 2, "platform_admin": 3}


@dataclass
class Principal:
    user_id: str
    role: str
    home_tenant_id: str | None
    tenant_id: str | None  # effective tenant for this request

    @property
    def is_platform_admin(self) -> bool:
        return self.role == "platform_admin"


async def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_tenant_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    if claims.get("kind") in ("widget", "ws"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Widget sessions cannot access the admin API")
    # Tokens are stateless, so check the account on every request: a deactivated (or deleted) user is locked
    # out at once instead of when the token expires. Role and tenant also come from the database, not the token.
    user = await db.get(User, claims.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid. Please sign in again.")
    role, home = user.role, user.tenant_id
    if role == "platform_admin":
        effective = x_tenant_id  # may be None for cross-tenant platform endpoints
    else:
        if x_tenant_id and x_tenant_id != home:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-tenant access denied")
        effective = home
    return Principal(user_id=claims["sub"], role=role, home_tenant_id=home, tenant_id=effective)


def require_role(min_role: str):
    async def dep(p: Principal = Depends(get_principal)) -> Principal:
        if ROLE_RANK.get(p.role, 0) < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return p
    return dep


async def tenant_scope(p: Principal = Depends(get_principal)) -> Principal:
    """Endpoints operating on tenant data. Platform admins must pick a tenant via X-Tenant-ID."""
    if not p.tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select a tenant (X-Tenant-ID header)")
    return p


async def tenant_admin_scope(p: Principal = Depends(tenant_scope)) -> Principal:
    if ROLE_RANK.get(p.role, 0) < ROLE_RANK["tenant_admin"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
    return p


async def audit(db: AsyncSession, request: Request | None, p: Principal | None, action: str, resource_type: str,
                resource_id: str | None = None, **details) -> None:
    db.add(AuditLog(tenant_id=p.tenant_id if p else None, actor=p.user_id if p else "system", action=action,
                    resource_type=resource_type, resource_id=resource_id, details=details,
                    ip=request.client.host if request and request.client else None))


DB = Depends(get_db)
