"""Application configuration settings using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for the Bulk Certificate Generator application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./certificates.db"

    # File Storage
    certificates_storage_dir: str = "./storage/certificates"

    # Batch limits
    max_recipients_per_job: int = 5000

    # Processing mode: when True, background tasks execute synchronously (ideal for testing)
    run_background_tasks_synchronously: bool = False

    # Logging & Server
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def storage_path(self) -> Path:
        """Return the resolved Path object for certificate storage, ensuring it exists."""
        path = Path(self.certificates_storage_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
