"""Споделени типове и миксини за ORM моделите."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# PRD-то иска JSONB за вариращите CV полета. Вариантът за SQLite пази отворена
# вратата за "бърз старт със SQLite → после Postgres" от README.
JSONDict = JSONB().with_variant(JSON(), "sqlite")


class TimestampMixin:
    """created_at / updated_at, попълвани от базата, не от приложението."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
