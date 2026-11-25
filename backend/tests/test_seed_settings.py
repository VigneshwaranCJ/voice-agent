"""The demo seed takes its logins from Settings, so SEED_* values in .env apply (not only real env vars)."""

from app.core.config import Settings


def test_seed_credentials_are_read_from_dotenv(tmp_path, monkeypatch):
    for var in ("SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD", "SEED_TENANT_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "SEED_ADMIN_EMAIL=Owner@Example.local\nSEED_ADMIN_PASSWORD=Admin-From-Dotenv-1\n"
        "SEED_TENANT_PASSWORD=Tenant-From-Dotenv-1\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env))
    assert s.seed_admin_email == "Owner@Example.local"
    assert s.seed_admin_password == "Admin-From-Dotenv-1"
    assert s.seed_tenant_password == "Tenant-From-Dotenv-1"


def test_seed_credentials_default_when_unset(tmp_path, monkeypatch):
    for var in ("SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD", "SEED_TENANT_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=str(tmp_path / "missing.env"))
    assert s.seed_admin_email == "admin@platform.local"
    assert s.seed_admin_password == "ChangeMe-Admin-123"
    assert s.seed_tenant_password == "ChangeMe-Tenant-123"
