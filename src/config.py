from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration read from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore Firebase/GCP env vars not declared in this model
    )

    # Auth — V1 legacy (kept for dev-token fallback only)
    admin_token: str = "dev-token-change-me"
    admin_username: str = "admin"
    admin_password: str = "admin"

    # Auth — V2: session-based auth settings
    bcrypt_rounds: int = 12
    session_ttl_hours: int = 24
    allow_dev_token: bool = False  # NEVER True in production
    rate_limit_login_per_minute: int = 5
    max_jobs_per_user_per_day: int = 20

    # JWT hop tokens — V3: broker issues short-lived, scoped JWTs per task hop
    jwt_hop_secret: str = ""  # 256-bit minimum (32+ chars), loaded from JWT_HOP_SECRET env var
    jwt_hop_issuer: str = "terafac-api"
    jwt_hop_audience: str = "terafac-worker"
    jwt_hop_ttl_seconds: int = 300  # 5 minutes

    # V4: Research agent settings
    research_agent_url: str = "http://localhost:8001/run"  # Cloud Run URL in prod
    gemini_api_key: str = ""  # loaded from GEMINI_API_KEY env var (Secret Manager in prod)
    research_timeout_seconds: int = 60  # max time to wait for research agent response

    # CORS
    cors_origins: str = "http://localhost:3100,http://localhost:3000"

    # Firestore
    firestore_project_id: str = "terafac-dev"

    # Server
    port: int = 8000

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list, stripped of whitespace."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — instantiated once per process."""
    return Settings()
