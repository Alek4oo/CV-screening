"""Споделени типове и миксини за ORM моделите.

Целевата база е PostgreSQL — типовете тук са нейните native типове. Вариантът
за SQLite съществува само заради тестовете в паметта; продукционната схема
минава единствено през Alembic (виж backend/alembic/).
"""

from datetime import datetime
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.functions import FunctionElement

# Вариращите JSON полета (профил, изисквания, обяснение, одитни payload-и)
# живеят в JSONB, не в текст: индексируеми са и заявките по ключ не парсват
# низ. Вариантът за SQLite държи тестовете в паметта работещи.
JSONDict = JSONB().with_variant(JSON(), "sqlite")

# Postgres native UUID. `as_uuid=True` значи, че кодът подава и получава
# `uuid.UUID`, а не низ — типът в базата и типът в Python са едно и също нещо.
UUIDType = UUID(as_uuid=True).with_variant(Uuid(as_uuid=True), "sqlite")


class gen_uuid(FunctionElement):
    """server_default за UUID ключ: `gen_random_uuid()` на Postgres.

    Извън Postgres се свежда до NULL — стойността тогава идва от Python
    страната (`default=uuid4`), която работи и на двата диалекта.
    """

    type = UUIDType
    name = "gen_uuid"
    inherit_cache = True


@compiles(gen_uuid, "postgresql")
def _gen_uuid_postgresql(element: gen_uuid, compiler, **kw: object) -> str:
    # pgcrypto не е нужен: gen_random_uuid() е в ядрото от PostgreSQL 13.
    return "gen_random_uuid()"


@compiles(gen_uuid)
def _gen_uuid_default(element: gen_uuid, compiler, **kw: object) -> str:
    return "NULL"


def uuid_pk() -> Mapped[PyUUID]:
    """UUID първичен ключ — генериран и от базата, и от приложението.

    `default=uuid4` е това, което реално попълва колоната при ORM insert, за да
    е налично `id` преди flush. `server_default` покрива вмъкванията извън
    ORM-а — миграции, seed през SQL, ръчни поправки.
    """
    return mapped_column(
        UUIDType, primary_key=True, default=uuid4, server_default=gen_uuid()
    )


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
