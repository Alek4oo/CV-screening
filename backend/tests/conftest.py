"""Общи фикстури: изолирана база в паметта и клиент с подменени зависимости."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.db import Base, get_session
from app.main import app
from app.ocr import get_text_extractor

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return (DATA_DIR / "sample_cv.pdf").read_bytes()


@pytest.fixture
def engine():
    """SQLite в паметта, споделен между връзките на теста."""
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def client(engine, monkeypatch):
    """TestClient срещу тестовата база, с истинския OCR адаптер по подразбиране."""
    # Иначе lifespan-ът ще посегне към Postgres от конфигурацията.
    monkeypatch.setattr(settings, "auto_create_tables", False)

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
