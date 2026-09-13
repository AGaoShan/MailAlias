from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mailcom_db_path: str = "./data/mailcom.db"
    mailcom_secret_key: str = "dev-secret-key-please-change-32bytes-minimum"
    jwt_secret: str = "dev-jwt-secret-please-change-32bytes-minimum"
    jwt_expire_minutes: int = 1440

    pickup_api_base: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    mailcom_timeout: int = 30

    max_aliases_per_account: int = 10

    pickup_concurrency_per_account: int = 2
    pickup_global_concurrency: int = 8
    rate_limit_per_account_qps: float = 1.0
    rate_limit_global_qps: float = 5.0
    write_min_interval: float = 2.0
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    circuit_fail_threshold: int = 5
    circuit_cooldown: float = 60.0
    pickup_cache_ttl: int = 30

    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    frontend_dist: str = "../frontend/dist"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def db_path(self) -> Path:
        return Path(self.mailcom_db_path).expanduser().resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def frontend_dist_path(self) -> Path:
        return Path(self.frontend_dist).expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
