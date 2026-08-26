"""Pydantic схеми на API слоя."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtractionInfo(BaseModel):
    """Как е добит текстът — част от проследимостта, не козметика."""

    engine: str = Field(description="Име на OCR адаптера, свършил работата")
    characters: int = Field(description="Дължина на извлечения текст")
    confidence: float = Field(description="Дял намерени секции при парсването, 0..1")


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str | None = None
    source_filename: str | None = None
    profile: dict[str, Any]
    created_at: datetime


class CandidateUploadResponse(BaseModel):
    candidate: CandidateRead
    extraction: ExtractionInfo


class RankRequest(BaseModel):
    """Тялото на POST /roles/{id}/rank — и двете полета са по избор."""

    ruleset_version: str | None = Field(
        default=None,
        description="Версия правила. По подразбиране — активната в момента.",
    )
    candidate_ids: list[UUID] | None = Field(
        default=None,
        description="Подмножество кандидати. По подразбиране — всички.",
    )


class FactorOut(BaseModel):
    """Приносът на един фактор — обяснението, което рекрутерът чете."""

    name: str = Field(description="Име на фактора, напр. required_skills")
    weight: float = Field(description="Тежест от версията правила")
    subscore: float = Field(description="Изпълнение на фактора, 0..1")
    contribution: float = Field(description="Точки, които факторът дава на скора")
    matched: list[str] = Field(default_factory=list, description="Какво е покрито")
    missing: list[str] = Field(default_factory=list, description="Какво липсва")
    detail: str = Field(default="", description="Обяснение на един ред")


class RankedCandidate(BaseModel):
    position: int = Field(description="Място в класацията, от 1")
    ranking_id: UUID
    candidate_id: UUID
    full_name: str
    score: float = Field(description="Точки от 0 до 100")
    meets_minimum: bool = Field(
        description="Покрити ли са всички твърди изисквания. Флаг, не присъда."
    )
    factors: list[FactorOut]


class RankResponse(BaseModel):
    role_id: UUID
    role_title: str
    ruleset_id: UUID
    ruleset_version: str
    engine: str = Field(description="Име на скоринг адаптера, свършил работата")
    mode: str = Field(description="masked — скоринг без достъп до защитени атрибути")
    ranked: list[RankedCandidate]
