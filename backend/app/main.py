from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.industries.registry  # noqa: F401  registers industry tools/models
import app.tools.common  # noqa: F401  registers common tools
from app.api import (
    agents, auth, business_data, chat, conversations, integrations, knowledge, notifications, sarvam_agents, tenants,
    users,
)
from app.core.config import get_settings
from app.core.database import SessionLocal, create_all
from app.core.logging import configure_logging, log
from app.core.public_cors import PublicCORSMiddleware
from app.core.ratelimit import RateLimitMiddleware

settings = get_settings()
configure_logging(settings.log_level, json=settings.environment != "development")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.is_production:
        errors, warnings = settings.production_problems()
        for w in warnings:
            log.warning("production_config", issue=w)
        if errors:
            raise RuntimeError("Unsafe production config: " + "; ".join(errors))
    if settings.is_sqlite or settings.environment == "development":
        await create_all()  # production: `alembic upgrade head` runs before the app starts
    if settings.seed_demo_data and settings.environment == "development":
        from app.seed import seed

        async with SessionLocal() as db:
            if await seed(db):
                log.info("demo_data_seeded")
    if not settings.sarvam_configured:
        log.warning("sarvam_not_configured", hint="Set SARVAM_API_KEY in .env to enable voice and AI replies")
    yield
    from app.sarvam.client import get_sarvam

    await get_sarvam().aclose()


# Interactive API docs only in development (they advertise every endpoint and schema).
_docs = {} if not settings.is_production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, **_docs)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(PublicCORSMiddleware)  # added last = outermost: widget endpoints accept any site

api = APIRouter(prefix="/api/v1")
for r in (auth, tenants, users, notifications, agents, knowledge, integrations, conversations, business_data, chat,
          sarvam_agents):
    api.include_router(r.router)
app.include_router(api)


@app.get("/health")
async def health():
    return {"status": "ok", "sarvam_configured": settings.sarvam_configured,
            "database": "sqlite" if settings.is_sqlite else "postgresql",
            "state_store": "redis" if settings.redis_url else "memory"}


if settings.frontend_dir:  # last, so the dashboard's catch-all route never shadows the API
    from app.core.frontend import mount_frontend

    mount_frontend(app, settings.frontend_dir)
