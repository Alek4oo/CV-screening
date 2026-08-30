"""Резултат от bias-одит за двойка роля/версия правила.

Одитът е това, което PRD-то иска доказано: класирането се смята веднъж върху
маскиран профил и веднъж върху немаскиран, а разликата между двете подредби е
мярката за пристрастност. Тази таблица пази изхода — не суровите признаци.

Редът е неизменим по замисъл, като одитната следа: нов одит значи нов ред, а
не UPDATE на стар. Затова има само `created_at`, без `updated_at`.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, desc, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import JSONDict, UUIDType, uuid_pk

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.ruleset import Ruleset


class BiasAudit(Base):
    __tablename__ = "bias_audit"
    __table_args__ = (
        # Историята на одитите за една роля, най-новият отгоре.
        Index("ix_bias_audit_role_created_at", "role_id", desc("created_at")),
    )

    id: Mapped[UUID] = uuid_pk()

    # CASCADE: изтрита роля няма одит. RESTRICT за правилата — версия, за която
    # има одитен резултат, не се трие.
    role_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("role.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ruleset_id: Mapped[UUID] = mapped_column(
        UUIDType,
        ForeignKey("ruleset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Метрики по групи (selection rate, средно класиране, impact ratio) и
    # разликата masked/unmasked. Формата зависи от това какви признаци има в
    # набора — затова JSONB, а не колони.
    report: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    role: Mapped["Role"] = relationship(back_populates="bias_audits")
    ruleset: Mapped["Ruleset"] = relationship()

    def __repr__(self) -> str:
        return f"<BiasAudit id={self.id} role_id={self.role_id} at={self.created_at}>"
