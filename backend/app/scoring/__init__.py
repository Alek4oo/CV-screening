"""Регистър на скоринг адаптерите.

Смяната на реализация е смяна на SCORING_BACKEND в средата — нищо в API слоя не
се пипа. Нова реализация се добавя с един ред в _BACKENDS.

Тежестите идват от версия правила, не от кода: фабриката приема ruleset и оттам
всяко класиране може да посочи с коя версия е сметнато.
"""

from collections.abc import Callable
from typing import Any, Protocol

from app.core.config import settings
from app.scoring.base import (
    FactorScore,
    InvalidRulesError,
    ScorableCandidate,
    ScorableRole,
    Scorer,
    ScoreResult,
    ScoringEngineUnavailableError,
    ScoringError,
)
from app.scoring.rule_based import CandidateFacts, RuleBasedScorer
from app.scoring.rules import DEFAULT_WEIGHTS, FACTOR_NAMES, RoleRequirements, ScoringRules

__all__ = [
    "DEFAULT_WEIGHTS",
    "FACTOR_NAMES",
    "CandidateFacts",
    "FactorScore",
    "InvalidRulesError",
    "RoleRequirements",
    "RuleBasedScorer",
    "ScorableCandidate",
    "ScorableRole",
    "ScoreResult",
    "Scorer",
    "ScorerFactory",
    "ScoringEngineUnavailableError",
    "ScoringError",
    "ScoringRules",
    "build_scorer",
    "get_scorer_factory",
]


class VersionedRules(Protocol):
    """Толкова от ruleset-а, колкото фабриката ползва."""

    version: str
    definition: dict[str, Any]


class ScorerFactory(Protocol):
    def __call__(self, ruleset: VersionedRules) -> Scorer: ...


_BACKENDS: dict[str, Callable[[ScoringRules], Scorer]] = {
    "rule_based": RuleBasedScorer,
}


def build_scorer(ruleset: VersionedRules) -> Scorer:
    """Скорер, конфигуриран с подадената версия правила.

    Хвърля InvalidRulesError при неизползваема дефиниция и
    ScoringEngineUnavailableError при непознат бекенд.
    """
    rules = ScoringRules.from_definition(
        getattr(ruleset, "definition", None), version=getattr(ruleset, "version", None)
    )

    try:
        factory = _BACKENDS[settings.scoring_backend]
    except KeyError:
        known = ", ".join(sorted(_BACKENDS))
        raise ScoringEngineUnavailableError(
            f"Непознат SCORING_BACKEND {settings.scoring_backend!r}. Налични: {known}"
        ) from None

    return factory(rules)


def get_scorer_factory() -> ScorerFactory:
    """FastAPI зависимост — тестовете я подменят през app.dependency_overrides."""
    return build_scorer
