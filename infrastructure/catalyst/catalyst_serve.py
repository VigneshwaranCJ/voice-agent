"""Entry point for Zoho Catalyst AppSail (Catalyst-managed Python 3.12 runtime).

Startup command in AppSail:  python3 -u catalyst_serve.py

- Dependencies are vendored into ./vendor (Linux wheels, built by build-catalyst.ps1); AppSail doesn't install them.
- Settings come from AppSail environment variables (console > AppSail > Configuration), not a .env file.
- On every start: open the port Catalyst assigns (X_ZOHO_CATALYST_LISTEN_PORT) at once, since AppSail requires
  listening within 10 seconds; then apply database migrations, create any BOOTSTRAP_ADMIN_* users, and serve the
  API, WebSockets and the built dashboard on that socket. RUN_MIGRATIONS=false skips migrations.
"""

import asyncio
import os
import socket
import sys
import time
from pathlib import Path

# Listen immediately: AppSail only waits 10 s for the port, and importing the app plus migrations can take longer
# on a cold instance. Requests that arrive meanwhile wait in the socket's queue until the server is ready.
PORT = int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT", "9000"))
SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
SOCK.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
SOCK.bind(("0.0.0.0", PORT))  # Catalyst routes traffic to this port on all interfaces
SOCK.listen(2048)

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "vendor"), str(HERE)]
os.chdir(HERE)
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("FRONTEND_DIR", str(HERE / "static"))

T0 = time.monotonic()


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(HERE / "alembic.ini")), "head")


async def _bootstrap() -> None:
    from app.bootstrap import admin_pairs_from_env, bootstrap_admins_from_env
    from app.core.database import engine

    try:
        if admin_pairs_from_env():
            await bootstrap_admins_from_env()
    finally:
        await engine.dispose()  # uvicorn starts its own event loop; don't carry pooled connections over


def main() -> None:
    from app.core.config import get_settings
    from app.core.logging import log

    if os.getenv("RUN_MIGRATIONS", "true").lower() != "false":
        if get_settings().is_sqlite:
            log.warning("catalyst_sqlite", hint="AppSail disks are not persistent; set DATABASE_URL to PostgreSQL")
        _migrate()
    asyncio.run(_bootstrap())

    import uvicorn

    log.info("catalyst_starting", port=PORT, prep_seconds=round(time.monotonic() - T0, 2))
    config = uvicorn.Config(
        "app.main:app",
        proxy_headers=True,
        forwarded_allow_ips="*",  # only Catalyst's front end can reach the instance
        ws="none",  # no WebSocket routes: voice runs on hosted Sarvam Voice Agents
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
    uvicorn.Server(config).run(sockets=[SOCK])  # serve on the socket opened at startup


if __name__ == "__main__":
    main()
