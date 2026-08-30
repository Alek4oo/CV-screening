"""Общи фикстури: изолирана база и клиент с подменени зависимости.

За схемата има два пътя и разликата е нарочна:

  * TEST_DATABASE_URL сочи към Postgres → схемата идва от `alembic upgrade
    head`, тоест от същите миграции като продукцията. Това е пътят, който
    доказва, че миграциите работят.
  * Няма TEST_DATABASE_URL → SQLite в паметта, вдигната от `Base.metadata`.
    Бърза и без зависимости, но проверява модели, не миграции: Postgres
    типовете (JSONB, ENUM, native UUID) минават през вариантите в
    `app.models.common`.

Това е единственото място в проекта, където схема се създава без Alembic — и
то е тестова база за един процес, не нещо, което приложението пипа.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_session
from app.main import app
from app.ocr import get_text_extractor

DATA_DIR = Path(__file__).parent / "data"
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return (DATA_DIR / "sample_cv.pdf").read_bytes()


@pytest.fixture
def engine():
    """Празна база за теста — през миграциите, ако има Postgres подръка."""
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        test_engine = create_engine(url, poolclass=StaticPool)
        _migrate(url)
        yield test_engine
        test_engine.dispose()
        return

    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


def _migrate(url: str) -> None:
    """Сваля схемата до нула и я вдига наново от миграциите."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # Зададен така, sqlalchemy.url бие DATABASE_URL от средата — миграциите
    # не могат да се озоват в дев базата на разработчика.
    config.set_main_option("sqlalchemy.url", url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def client(engine):
    """TestClient срещу тестовата база, с истинския OCR адаптер по подразбиране."""

    def override_session():
        db_session = Session(engine)
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_ruleset(session):
    """Активна версия правила — минимумът, без който класирането отказва."""
    from datetime import datetime, timezone

    from app.models import Ruleset, RulesetStatus

    ruleset = Ruleset(
        version="2026.08.1",
        name="Базови правила",
        definition={"weights": {"required_skills": 1}},
        status=RulesetStatus.ACTIVE,
        activated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    session.add(ruleset)
    session.commit()
    return ruleset


@pytest.fixture
def use_extractor(client):
    """Подменя OCR адаптера — доказателството, че е сменяем."""

    def _use(extractor):
        app.dependency_overrides[get_text_extractor] = lambda: extractor
        return client

    return _use
