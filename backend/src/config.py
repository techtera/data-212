"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # GCS
    GCS_BUCKET_NAME: str = "terafac-datasets"
    GCS_SA_KEY_PATH: str = "gcs-service-account.json"
    GCS_SIGNED_URL_TTL: int = 900  # seconds

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3100"

    # Training VM
    VM_HOST: str = ""
    VM_USER: str = "ubuntu"
    VM_SSH_KEY_PATH: str = ""
    TRAINING_MODE: str = "stub"  # "stub" or "ssh"

    # Auth
    BCRYPT_ROUNDS: int = 12
    SESSION_TTL_HOURS: int = 24

    # Gemini
    GEMINI_API_KEY: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
