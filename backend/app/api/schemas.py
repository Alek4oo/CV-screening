"""Pydantic схеми на API слоя.

Изискванията на ролята и тежестите на правилата се валидират тук, при входа, а
не при класирането. Така грешната конфигурация се отказва с 422 от този, който
я подава, вместо да гръмне седмица по-късно срещу някой, който само класира.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AuditAction, DecisionOutcome, RoleStatus, RulesetStatus
from app.scoring import InvalidRulesError, RoleRequirements, ScoringRules


class ExtractionInfo(BaseModel):
    """Как е добит текстът — част от проследимостта, не козметика."""

    engine: str = Field(description="Name of the OCR adapter that did the work")
    characters: int = Field(description="Length of the extracted text")
    confidence: float = Field(description="Share of sections found while parsing, 0..1")


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
        description="What is asked for: weighted skills, years, degree, languages.",
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

    version: str = Field(min_length=1, max_length=32, description="e.g. 2026.08.1")
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    definition: dict[str, Any] = Field(
        default_factory=dict,
        description="Factor weights. Empty means the defaults.",
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
        description="Ruleset version. Defaults to the one currently active.",
    )
    candidate_ids: list[UUID] | None = Field(
        default=None,
        description="A subset of candidates. Defaults to all of them.",
    )


class FactorOut(BaseModel):
    """Приносът на един фактор — обяснението, което рекрутерът чете."""

    name: str = Field(description="Factor name, e.g. required_skills")
    weight: float = Field(description="Weight from the ruleset")
    subscore: float = Field(description="Fulfilment of the factor, 0..1")
    contribution: float = Field(description="Points the factor contributes to the score")
    matched: list[str] = Field(default_factory=list, description="What is covered")
    missing: list[str] = Field(default_factory=list, description="What is missing")
    detail: str = Field(default="", description="A one-line explanation")


class RankedCandidate(BaseModel):
    position: int = Field(description="Place in the ranking, from 1")
    ranking_id: UUID
    candidate_id: UUID
    full_name: str
    score: float = Field(description="Points from 0 to 100")
    meets_minimum: bool = Field(
        description="Whether every hard requirement is met. A flag, not a verdict."
    )
    factors: list[FactorOut]


class RankResponse(BaseModel):
    role_id: UUID
    role_title: str
    ruleset_id: UUID
    ruleset_version: str
    engine: str = Field(description="Name of the scoring adapter that did the work")
    mode: str = Field(description="masked — scoring with no access to protected attributes")
    ranked: list[RankedCandidate]


# --- Кандидати за преглед ---


class CandidateDetailRead(CandidateRead):
    """Кандидатът, както го вижда рекрутерът.

    `protected_attributes` няма поле тук и това не е пропуск: те са вход
    единствено на bias-одита. Изглед, който ги показва, би позволил решение,
    взето по тях — точно каквото PRD-то забранява.
    """

    external_ref: str | None = None
    raw_text: str | None = Field(default=None, description="The raw text from OCR")
    updated_at: datetime


# --- Решение на рекрутер ---


class DecisionWrite(BaseModel):
    """Заявка за решение по класиране.

    И двете полета извън изхода са задължителни при всеки статус, включително
    връщането „за преглед": решение без име и без обосновка не е преглед от
    човек, а само смяна на стойност в базата.
    """

    outcome: DecisionOutcome = Field(description="for_review | advanced | rejected | on_hold")
    decided_by: str = Field(min_length=1, max_length=255, description="Which recruiter is deciding")
    rationale: str = Field(min_length=1, description="Why — recorded in the audit log")

    @field_validator("decided_by", "rationale")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("The field cannot be only whitespace.")
        return stripped


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ranking_id: UUID
    ruleset_id: UUID
    outcome: DecisionOutcome
    decided_by: str | None = None
    decided_at: datetime | None = None
    rationale: str | None = None
    created_at: datetime
    updated_at: datetime


# --- Класация за преглед ---


class RulesetRef(BaseModel):
    """Версията правила, с която е сметнато класирането."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    name: str
    status: RulesetStatus


class RankingRow(BaseModel):
    """Един ред от таблицата с класирани кандидати."""

    ranking_id: UUID
    position: int = Field(description="Place in the full ranking, before filters")
    candidate_id: UUID
    full_name: str
    email: str | None = None
    score: float
    meets_minimum: bool = Field(
        description="Whether the minimum is met. A flag for the recruiter, not a rejection."
    )
    top_factors: list[FactorOut] = Field(
        default_factory=list, description="The heaviest factors — a summary for the table"
    )
    missing: list[str] = Field(
        default_factory=list, description="Hard requirements not met"
    )
    outcome: DecisionOutcome = Field(
        description="Decision status. With no Decision row this is for_review."
    )
    decided_by: str | None = None
    decided_at: datetime | None = None
    ranked_at: datetime


class RankingListResponse(BaseModel):
    role_id: UUID
    role_title: str
    role_status: RoleStatus
    ruleset: RulesetRef | None = Field(
        default=None, description="The version the shown ranking belongs to"
    )
    available_rulesets: list[RulesetRef] = Field(
        default_factory=list, description="Versions the role has already been ranked under"
    )
    mode: str = Field(
        default="masked", description="Scoring with no access to protected attributes"
    )
    total: int = Field(description="Rows after the filters")
    total_unfiltered: int = Field(description="Rows in the full ranking")
    counts: dict[str, int] = Field(
        default_factory=dict, description="Counts by decision status"
    )
    rows: list[RankingRow]


class RoleRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    requirements: dict[str, Any]
    status: RoleStatus


class RankingDetail(BaseModel):
    """Класирането на един кандидат с цялото обяснение зад него."""

    ranking_id: UUID
    position: int
    score: float
    meets_minimum: bool
    mode: str
    engine: str = Field(default="", description="The scoring adapter behind the result")
    factors: list[FactorOut]
    weights: dict[str, float] = Field(
        default_factory=dict, description="Weights from the ruleset"
    )
    candidate: CandidateDetailRead
    role: RoleRef
    ruleset: RulesetRef
    decision: DecisionRead | None = None
    ranked_at: datetime


class AuditEntryRead(BaseModel):
    """Ред от одитната следа — кой, кога, какво."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor: str
    action: AuditAction
    entity_type: str
    entity_id: UUID | None = None
    ruleset_id: UUID | None = None
    payload_in: dict[str, Any]
    payload_out: dict[str, Any]
