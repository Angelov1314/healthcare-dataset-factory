"""Runtime configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://healthcare:change_me@localhost:5432/healthcare_factory"
    synthetic_seed: int = Field(default=20260810)
    synthetic_patients: int = Field(default=2000, ge=1, le=5000)
    log_level: str = "INFO"
    pseudonymization_secret: str = ""
    pseudonymization_key_id: str = "local-dev-v1"
    import_allowed_postgres_hosts: str = "localhost,127.0.0.1,db"
    import_allowed_postgres_ports: str = "5432"
    import_max_rows: int = Field(default=1000, ge=1, le=10000)
    import_max_upload_bytes: int = Field(default=10_000_000, ge=1, le=100_000_000)
    mapping_mode: str = "HYBRID"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = Field(default=15, ge=1, le=60)
    factory_benchmark_bundle_path: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
