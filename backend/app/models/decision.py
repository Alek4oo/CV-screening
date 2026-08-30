"""Решение на рекрутер по конкретно класиране.

Human-in-the-loop е състояние тук, не бутон в UI-а: редът се ражда FOR_REVIEW
и CHECK ограничението не позволява да напусне FOR_REVIEW без човек и час. Нищо
не става „отхвърлено" от само себе си.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import TimestampMixin, UUIDType, uuid_pk

if TYPE_CHECKING:
    from app.models.ranking import Ranking
    from app.models.ruleset import Ruleset


class DecisionOutcome(str, enum.Enum):
    FOR_REVIEW = "for_review"
    ADVANCED = "advanced"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


class Decision(TimestampMixin, Base):
    __tablename__ = "decision"
    __table_args__ = (
        CheckConstraint(
            "outcome = 'for_review' "
            "OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_decision_requires_human",
        ),
    )

    id: Mapped[UUID] = uuid_pk()

    # unique → едно решение на класиране.
    ranking_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("ranking.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Дублира ranking.ruleset_id нарочно: одитният запис за версията, с която е
    # взето решението, не бива да зависи от втора таблица.
    ruleset_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("ruleset.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    outcome: Mapped[DecisionOutcome] = mapped_column(
        Enum(
            DecisionOutcome,
            name="decision_outcome",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DecisionOutcome.FOR_REVIEW,
    )

    # Кой потвърди. NULL само докато решението е FOR_REVIEW.
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rationale: Mapped[str | None] = mapped_column(Text)

    ranking: Mapped["Ranking"] = relationship(back_populates="decision")
    ruleset: Mapped["Ruleset"] = relationship()

    def __repr__(self) -> str:
        return f"<Decision id={self.id} outcome={self.outcome.value} by={self.decided_by!r}>"
