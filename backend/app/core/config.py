from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Voice Care Platform"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Database / cache
    database_url: str = "sqlite+aiosqlite:///./voicecare.db"
    # Connections per app process. Keep small on hosts that run several copies against a pooled database
    # (e.g. Catalyst AppSail + Supabase): copies x (pool_size + max_overflow) must stay under the DB limit.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    redis_url: str | None = None
    # Single-server hosts without PostgreSQL (e.g. Windows/IIS shared hosting) may opt in to SQLite.
    # SQLite allows one writer at a time: run exactly one app process and back up the .db file.
    allow_sqlite_in_production: bool = False

    # Built dashboard (frontend/dist) to serve from this process, for hosts without a separate web server.
    frontend_dir: str | None = None

    # Security
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 720
    encryption_key: str | None = None  # Fernet key; required outside development
    rate_limit_per_minute: int = 120

    # Email alerts (new leads, escalations) to each business's admins. Off until SMTP_HOST and SMTP_FROM are set.
    # Works with any SMTP provider, e.g. Zoho Mail: smtp.zoho.in, port 587, starttls, an app password.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    # Public dashboard URL used for links in emails, e.g. https://kuralai.com
    public_base_url: str | None = None

    # Sarvam AI
    sarvam_api_key: str | None = None
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_llm_model: str = "sarvam-105b-conversations"
    sarvam_llm_reasoning_effort: str = "low"
    # Hosted Sarvam Voice Agents (Samvaad). Their own API key (dashboard > Settings > API key), sent as X-API-Key
    # when minting a call's signed WebSocket URL. The browser then talks to Sarvam directly, so this works on hosts
    # without WebSocket support (e.g. Catalyst AppSail).
    sarvam_agents_api_key: str | None = None
    sarvam_agents_base_url: str = "https://apps.sarvam.ai/api/app-runtime/"
    # Defaults for agents whose Sarvam link leaves a field blank (a link's own value always wins). Org and workspace
    # are usually the same for every business on one Sarvam account; the app (agent) id is normally per agent.
    sarvam_agents_org_id: str | None = None
    sarvam_agents_workspace_id: str | None = None
    sarvam_agents_app_id: str | None = None
    # Send the business's context (name, persona, phone, hours, services) as agent_variables when a call starts.
    # Enable only after declaring those variables in the Sarvam agent (see docs/deploy/SARVAM_VOICE.md).
    sarvam_agents_send_context: bool = False
    # Analytics API (same key): transcripts of finished calls, saved under Calls.
    sarvam_agents_analytics_url: str = "https://apps.sarvam.ai/api/analytics/v1"

    # Engine limits
    llm_timeout_seconds: float = 20.0
    tool_timeout_seconds: float = 8.0
    max_tool_rounds: int = 4
    history_max_messages: int = 20

    # Seed demo data (two demo businesses) on first start in development
    seed_demo_data: bool = True
    seed_admin_email: str = "admin@platform.local"
    seed_admin_password: str = "ChangeMe-Admin-123"
    seed_tenant_password: str = "ChangeMe-Tenant-123"

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, v: str) -> str:
        """Accept the plain postgres:// / postgresql://?sslmode=require strings hosts like Supabase give out."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v[len(prefix):]
        if v.startswith("postgresql+asyncpg://") and "sslmode=" in v:
            v = v.replace("sslmode=", "ssl=")  # asyncpg's name for the same option
        return v

    @property
    def is_production(self) -> bool:
        return self.environment != "development"

    def production_problems(self) -> tuple[list[str], list[str]]:
        """(errors, warnings) for a non-development deploy. Errors stop the server from starting."""
        errors, warnings = [], []
        if self.jwt_secret == "dev-only-change-me" or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET must be a random value of at least 32 characters")
        try:
            from cryptography.fernet import Fernet

            Fernet((self.encryption_key or "").encode())
        except Exception:
            errors.append("ENCRYPTION_KEY must be a valid Fernet key")
        if self.is_sqlite and not self.allow_sqlite_in_production:
            errors.append("DATABASE_URL must point to PostgreSQL, not SQLite")
        elif self.is_sqlite:
            warnings.append("Using SQLite in production: run a single app process and back up the database file")
        if any(o == "*" or "localhost" in o or "127.0.0.1" in o for o in self.cors_origins):
            warnings.append("CORS_ORIGINS includes '*' or localhost; set it to your dashboard's https origin")
        if any(o.startswith("http://") for o in self.cors_origins if "localhost" not in o):
            warnings.append("CORS_ORIGINS uses http://; browsers need https for the microphone")
        if not self.sarvam_configured:
            warnings.append("SARVAM_API_KEY is not set; voice and AI replies are disabled")
        if not self.redis_url:
            warnings.append("REDIS_URL is not set; live call state is in-process (single replica only)")
        return errors, warnings

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def sarvam_configured(self) -> bool:
        return bool(self.sarvam_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
