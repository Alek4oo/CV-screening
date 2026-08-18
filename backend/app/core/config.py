"""Конфигурация на приложението, четена от средата (12-factor)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI CV Screening API"
    app_version: str = "0.1.0"

    # Пълен SQLAlchemy URL. По подразбиране сочи към db услугата от docker-compose.
    database_url: str = "postgresql+psycopg2://cvscreening:cvscreening@db:5432/cvscreening"


settings = Settings()
