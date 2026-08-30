"""Класиране на кандидат спрямо роля с конкретна версия правила.

`mode` е това, което прави bias-одита възможен: PRD-то иска сравнение на
класирането със и без чувствителни признаци. MASKED е продукционният път —
скоринг върху маскиран профил. UNMASKED се произвежда само офлайн от одита и
никога не стига до рекрутера.
"""

import enum
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import JSONDict, TimestampMixin, UUIDType, uuid_pk

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.decision import Decision
    from app.models.role import Role
    from app.models.ruleset import Ruleset


class RankingMode(str, enum.Enum):
    MASKED = "masked"
    UNMASKED = "unmasked"


class Ranking(TimestampMixin, Base):
    __tablename__ = "ranking"
    __table_args__ = (
        # Едно класиране на комбинация кандидат/роля/правила/режим. Преизчисление
        # с нови правила ражда нов ред, а старият остава за одита.
        UniqueConstraint(
            "candidate_id",
            "role_id",
            "ruleset_id",
            "mode",
            name="uq_ranking_candidate_role_ruleset_mode",
        ),
        CheckConstraint("score >= 0", name="ck_ranking_score_non_negative"),
        # Класацията за една роля се чете точно така: филтър по роля, подредба
        # по низходящ резултат. DESC-ът в индекса значи, че Postgres взима
        # първите N реда от него, без сортиране.
        Index("ix_ranking_role_score", "role_id", desc("score")),
    )

    id: Mapped[UUID] = uuid_pk()

    candidate_id: Mapped[UUID] = mapped_column(
        UUIDType,
        ForeignKey("candidate.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("role.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT: версия правила, с която има класирания, не се трие.
    ruleset_id: Mapped[UUID] = mapped_column(
        UUIDType,
        ForeignKey("ruleset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    mode: Mapped[RankingMode] = mapped_column(
        Enum(
            RankingMode,
            name="ranking_mode",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RankingMode.MASKED,
    )

    score: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)

    # Кои фактори колко тежат и защо — изходът на explainability модула.
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    candidate: Mapped["Candidate"] = relationship(back_populates="rankings")
    role: Mapped["Role"] = relationship(back_populates="rankings")
    ruleset: Mapped["Ruleset"] = relationship()

    decision: Mapped["Decision | None"] = relationship(
        back_populates="ranking", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Ranking id={self.id} score={self.score} mode={self.mode.value}>"
