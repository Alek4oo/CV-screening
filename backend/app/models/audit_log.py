"""Append-only одитна следа.

PRD-то иска вход, изход, версия на правилата и кой е потвърдил — това са
колоните по-долу. Няма updated_at и няма релации с cascade: ред веднъж записан
не се променя и не се трие.

Append-only-то е наложено на ниво база: базовата миграция слага BEFORE
UPDATE OR DELETE тригер, който вдига изключение. ORM-ът сам по себе си не може
да го гарантира.

Добавена стойност в AuditAction не стига до вече създаден Postgres ENUM тип —
за нея трябва отделна миграция с ALTER TYPE audit_action ADD VALUE.
"""

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import JSONDict, UUIDType, uuid_pk


class AuditAction(str, enum.Enum):
    CV_INGESTED = "cv_ingested"
    PROFILE_PARSED = "profile_parsed"
    CANDIDATE_SCORED = "candidate_scored"
    DECISION_RECORDED = "decision_recorded"
    RULESET_CREATED = "ruleset_created"
    RULESET_ACTIVATED = "ruleset_activated"
    RULESET_ARCHIVED = "ruleset_archived"
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    BIAS_AUDIT_RUN = "bias_audit_run"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        # Одитът се чете като „какво е ставало с това нещо, подредено по време".
        Index("ix_audit_log_entity", "entity_type", "entity_id", "occurred_at"),
    )

    id: Mapped[UUID] = uuid_pk()

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Потребител при човешко действие, "system" при автоматична стъпка.
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    # Свободна препратка, не FK: логът преживява триенето на това, което описва.
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(UUIDType)

    # Версията правила, в сила при действието — по същата причина също без FK.
    # Създаването на ruleset пише одитен ред, който сочи към него; твърд
    # RESTRICT тук значи, че черновата вече не може да бъде изтрита от
    # собствения си одитен запис. Логът не бива да заключва това, което описва.
    ruleset_id: Mapped[UUID | None] = mapped_column(UUIDType, index=True)

    payload_in: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
    payload_out: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action.value} actor={self.actor!r} at={self.occurred_at}>"
