"""Entry point for Windows IIS hosting through HttpPlatformHandler (see web.config next to this file).

IIS starts `python -m serve` and passes the port to listen on in HTTP_PLATFORM_PORT (HttpPlatformHandler,
web.config) or ASPNETCORE_PORT (ASP.NET Core Module, web.ancm.config). The backend and the built dashboard
run in this one process: settings come from the .env file in this folder.

On start, platform admins are created from .env pairs (idempotent; existing users are left untouched):

    BOOTSTRAP_ADMIN_EMAIL=...      BOOTSTRAP_ADMIN_PASSWORD=...
    BOOTSTRAP_ADMIN_EMAIL_2=...    BOOTSTRAP_ADMIN_PASSWORD_2=...   (up to _10)

Remove the passwords from .env once each admin has signed in.
"""

import asyncio
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)  # relative paths in .env (database file, FRONTEND_DIR) resolve against this folder
(HERE / "App_Data" / "logs").mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE / ".env")


async def _bootstrap_admins() -> None:
    from app.bootstrap import admin_pairs_from_env, bootstrap_admins_from_env

    if not admin_pairs_from_env():
        return
    from app.core.database import create_all, engine

    try:
        await create_all()  # SQLite: tables are created here (no migrations on this host)
        await bootstrap_admins_from_env()
    finally:
        await engine.dispose()  # the server starts its own event loop; don't carry pooled connections over


def main() -> None:
    asyncio.run(_bootstrap_admins())

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",  # IIS forwards to this port; it is not reachable from outside
        # HttpPlatformHandler passes HTTP_PLATFORM_PORT; the ASP.NET Core Module (web.ancm.config) passes ASPNETCORE_PORT.
        port=int(os.getenv("HTTP_PLATFORM_PORT") or os.getenv("ASPNETCORE_PORT") or "8000"),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        ws="none",  # no WebSocket routes: voice runs on hosted Sarvam Voice Agents
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
