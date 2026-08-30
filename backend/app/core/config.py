"""Конфигурация на приложението, четена от средата (12-factor)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI CV Screening API"
    app_version: str = "0.1.0"

    # Пълен SQLAlchemy URL. По подразбиране сочи към db услугата от
    # docker-compose. Същата променлива чете и alembic/env.py — един източник
    # на истина за това коя е базата.
    database_url: str = "postgresql+psycopg2://cvscreening:cvscreening@db:5432/cvscreening"

    # --- Frontend ---
    # Произходите, от които React изгледът има право да вика API-то. Дев
    # сървърът на Vite и статичният билд от docker-compose.
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    # --- Качване на документи ---
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_upload_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
    )

    # --- Скоринг ---
    # Ключ от регистъра в app.scoring. Тежестите идват от ruleset-а, не оттук.
    scoring_backend: str = "rule_based"

    # --- OCR ---
    # Ключ от регистъра в app.ocr. Смяната на реализация е смяна на тази стойност.
    ocr_backend: str = "tesseract"
    ocr_languages: str = "bul+eng"
    # Път до бинарника, ако не е на PATH.
    tesseract_cmd: str | None = None
    # DPI при растеризиране на сканиран PDF преди OCR.
    ocr_dpi: int = 300


settings = Settings()
