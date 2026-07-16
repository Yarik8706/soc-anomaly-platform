from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "SOC Anomaly Platform API"
    app_version: str = "0.1.0"
    app_env: str = "local"
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    analysis_queue: str = "analysis"
    upload_directory: Path = PROJECT_ROOT / "data" / "uploads"
    normalized_directory: Path = PROJECT_ROOT / "data" / "normalized"
    analysis_directory: Path = PROJECT_ROOT / "data" / "runs"
    jwt_secret: str = "local-development-secret-change-me-now"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def validate_security_settings(self):
        if self.app_env != "local" and self.jwt_secret.startswith("local-development"):
            raise ValueError("JWT_SECRET must be configured outside local development")
        return self


settings = Settings()
