"""Single-process hosting (IIS bundle): SQLite opt-in and serving the built dashboard from FastAPI."""

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.frontend import mount_frontend


def _prod(**kw) -> Settings:
    base = dict(environment="production", jwt_secret="x" * 48, encryption_key=Fernet.generate_key().decode(),
                database_url="sqlite+aiosqlite:///./App_Data/kural.db", cors_origins=["https://kuralai.com"],
                sarvam_api_key="k", redis_url="redis://r:6379/0")
    return Settings(_env_file=None, **{**base, **kw})


def test_sqlite_in_production_needs_explicit_opt_in():
    errors, _ = _prod().production_problems()
    assert any("SQLite" in e for e in errors)
    errors, warnings = _prod(allow_sqlite_in_production=True).production_problems()
    assert errors == []
    assert any("SQLite" in w for w in warnings)


@pytest.fixture
def site(tmp_path):
    dist = tmp_path / "static"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>INDEX")
    (dist / "assets" / "app-123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (dist / "web.config").write_text("<configuration/>")
    (tmp_path / ".env").write_text("SARVAM_API_KEY=secret")
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping():
        return {"ok": True}

    mount_frontend(app, dist)
    return TestClient(app)


def test_serves_files_and_spa_routes(site):
    r = site.get("/assets/app-123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert site.get("/favicon.svg").text == "<svg/>"
    for route in ("/", "/agents", "/calls/42"):
        r = site.get(route)
        assert r.status_code == 200 and "INDEX" in r.text and r.headers["cache-control"] == "no-cache"


def test_api_routes_win_and_unknown_api_paths_404(site):
    assert site.get("/api/v1/ping").json() == {"ok": True}
    assert site.get("/api/v1/nope").status_code == 404
    assert site.get("/health").status_code == 404  # backend-owned, never the dashboard


def test_no_files_outside_the_dashboard_folder(site):
    for path in ("/../.env", "/%2e%2e/.env", "/..%2f.env", "/web.config"):
        r = site.get(path)
        assert "secret" not in r.text
        assert "<configuration/>" not in r.text


def test_missing_index_fails_fast(tmp_path):
    with pytest.raises(RuntimeError):
        mount_frontend(FastAPI(), tmp_path)
