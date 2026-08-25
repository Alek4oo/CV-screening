"""Версионирани правила за скоринг.

Редовете тук са неизменими по замисъл: промяна в правилата означава нов ред с
нова версия, не UPDATE на стар. Иначе одитната следа сочи към правила, които
вече не са тези, с които е взето решението.
"""

import enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.common import JSONDict, TimestampMixin
from datetime import datetime


class RulesetStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class Ruleset(TimestampMixin, Base):
    __tablename__ = "ruleset"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)

    # Човешки четима версия, напр. "2026.08.1". Уникална — един ред, една версия.
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Тегла, прагове, формула на скоринга — каквото скоринг адаптерът чете.
    definition: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    status: Mapped[RulesetStatus] = mapped_column(
        Enum(
            RulesetStatus,
            name="ruleset_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RulesetStatus.DRAFT,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Ruleset version={self.version!r} status={self.status.value}>"
