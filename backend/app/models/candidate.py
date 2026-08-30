"""Кандидат — структуриран профил след OCR/парсване.

Защитените атрибути стоят в отделна колона от профила нарочно. Маскирането по
PRD не е стъпка, която някой може да забрави да извика — скоринг слоят получава
`profile` и просто няма достъп до `protected_attributes`.
"""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.common import JSONDict, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.ranking import Ranking


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidate"

    id: Mapped[UUID] = uuid_pk()

    # Идентификатор от seed набора — държи синтетичните данни идемпотентни.
    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), index=True)

    source_filename: Mapped[str | None] = mapped_column(String(512))
    # Суровият изход на OCR адаптера, преди парсване. Пази се за проследимост.
    raw_text: Mapped[str | None] = mapped_column(Text)

    # Структуриран профил: умения, опит, образование. Формата варира по CV.
    profile: Mapped[dict[str, Any]] = mapped_column(JSONDict, nullable=False, default=dict)

    # Пол, възраст, произход и подобни. Вход единствено за bias-одита —
    # никога за скоринга.
    protected_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONDict, nullable=False, default=dict
    )

    rankings: Mapped[list["Ranking"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} name={self.full_name!r}>"
