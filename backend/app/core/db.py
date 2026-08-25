"""Връзка към PostgreSQL през SQLAlchemy ORM.

На този етап има само engine, session factory и декларативна база — ORM моделите
идват в следващ комит. Целта тук е доказано работеща връзка.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Обща декларативна база за всички ORM модели."""


def get_session() -> Iterator[Session]:
    """FastAPI зависимост — сесия за заявка, затворена накрая."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> bool:
    """Връща True, ако базата отговаря на тривиална заявка."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
