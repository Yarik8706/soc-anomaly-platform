from pathlib import Path

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

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
