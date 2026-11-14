"""Pricing service configuration."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PRICING_",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_db: str = Field(min_length=1)
    postgres_user: str = Field(min_length=1)
    postgres_port: int = Field(gt=0, le=65535)
    postgres_password: SecretStr
    postgres_host: str

    db_pool_size: int = Field(gt=0, le=10)
    db_max_overflow: int = Field(ge=0, le=10)
    db_pool_timeout: int = Field(gt=0, le=60)

    @property
    def postgres_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
