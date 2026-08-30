"""Роля — изискванията, спрямо които се класират кандидатите."""

import enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import JSONDict, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.bias_audit import BiasAudit
    from app.models.ranking import Ranking


class RoleStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class Role(TimestampMixin, Base):
    __tablename__ = "role"

    id: Mapped[UUID] = uuid_pk()

    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Задължителни и предпочитани умения с тегла. Тежестите тук описват ролята;
    # начинът, по който се смятат, живее в ruleset.definition.
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    status: Mapped[RoleStatus] = mapped_column(
        Enum(
            RoleStatus,
            name="role_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RoleStatus.DRAFT,
    )

    rankings: Mapped[list["Ranking"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    bias_audits: Mapped[list["BiasAudit"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} title={self.title!r}>"
