"""Append-only одитна следа.

PRD-то иска вход, изход, версия на правилата и кой е потвърдил — това са
колоните по-долу. Няма updated_at и няма релации с cascade: ред веднъж записан
не се променя и не се трие.

Забележка: ORM-ът не може да наложи append-only сам по себе си. Истинската
гаранция е на ниво база — REVOKE UPDATE/DELETE за ролята на приложението или
BEFORE UPDATE/DELETE тригер. Идва с миграциите.

Второ предупреждение за същия момент: добавена стойност в AuditAction стига до
празна база през create_all, но не и до вече създаден Postgres ENUM тип. Там
трябва ALTER TYPE audit_action ADD VALUE — първата работа на Alembic.
"""

import enum
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import JSONDict


class AuditAction(str, enum.Enum):
    CV_INGESTED = "cv_ingested"
    PROFILE_PARSED = "profile_parsed"
    CANDIDATE_SCORED = "candidate_scored"
    DECISION_RECORDED = "decision_recorded"
    RULESET_CREATED = "ruleset_created"
    RULESET_ACTIVATED = "ruleset_activated"
    RULESET_RETIRED = "ruleset_retired"
    ROLE_CREATED = "role_created"
    ROLE_UPDATED = "role_updated"
    BIAS_AUDIT_RUN = "bias_audit_run"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_occurred_at", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

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
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))

    # Версията правила, в сила при действието.
    ruleset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ruleset.id", ondelete="RESTRICT"), index=True
    )

    payload_in: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)
    payload_out: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action.value} actor={self.actor!r} at={self.occurred_at}>"
