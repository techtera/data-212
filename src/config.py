from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration read from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Auth
    admin_token: str = "dev-token-change-me"
    admin_username: str = "admin"
    admin_password: str = "admin"

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
