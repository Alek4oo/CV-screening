"""Pydantic схеми на API слоя.

Изискванията на ролята и тежестите на правилата се валидират тук, при входа, а
не при класирането. Така грешната конфигурация се отказва с 422 от този, който
я подава, вместо да гръмне седмица по-късно срещу някой, който само класира.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import RoleStatus, RulesetStatus
from app.scoring import InvalidRulesError, RoleRequirements, ScoringRules


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


def _validated_requirements(value: dict[str, Any]) -> dict[str, Any]:
    try:
        RoleRequirements.from_json(value)
    except InvalidRulesError as exc:
        raise ValueError(str(exc)) from exc
    return value


def _validated_definition(value: dict[str, Any]) -> dict[str, Any]:
    try:
        ScoringRules.from_definition(value)
    except InvalidRulesError as exc:
        raise ValueError(str(exc)) from exc
    return value


class RoleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    requirements: dict[str, Any] = Field(
        default_factory=dict,
        description="Какво се иска: умения с тегла, години опит, степен, езици.",
    )
    status: RoleStatus = RoleStatus.DRAFT
    external_ref: str | None = Field(default=None, max_length=64)

    _check_requirements = field_validator("requirements")(_validated_requirements)


class RoleUpdate(BaseModel):
    """Частично обновяване — подава се само това, което се променя."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    requirements: dict[str, Any] | None = None
    status: RoleStatus | None = None

    _check_requirements = field_validator("requirements")(_validated_requirements)


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_ref: str | None = None
    title: str
    description: str | None = None
    requirements: dict[str, Any]
    status: RoleStatus
    created_at: datetime
    updated_at: datetime


class RulesetCreate(BaseModel):
    """Нова версия правила. Ражда се като чернова — активира се отделно."""

    version: str = Field(min_length=1, max_length=32, description="Напр. 2026.08.1")
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    definition: dict[str, Any] = Field(
        default_factory=dict,
        description="Тежести на факторите. Празно значи подразбиращите се.",
    )

    _check_definition = field_validator("definition")(_validated_definition)


class RulesetUpdate(BaseModel):
    """Промяна на чернова. Активирана версия не се пипа — прави се нова."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
    definition: dict[str, Any] | None = None

    _check_definition = field_validator("definition")(_validated_definition)


class RulesetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    name: str
    notes: str | None = None
    definition: dict[str, Any]
    status: RulesetStatus
    activated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


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
