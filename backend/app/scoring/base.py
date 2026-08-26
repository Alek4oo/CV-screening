"""Договорът на скоринг слоя.

Всичко над този модул знае само `score(candidate, role) -> ScoreResult`. Как се
смята резултатът е детайл на реализацията — точно затова адаптерът е сменяем,
както и OCR адаптерът.

Две неща тук не са козметика, а изискване на EU AI Act:

  * Входът е протокол с едно поле — `profile`. Скорерът няма достъп до
    `protected_attributes` не по споразумение, а защото типът не ги съдържа.
  * Резултатът носи приноса на всеки фактор, не само число. Класиране без
    обяснение не може да бъде прегледано от човек, а човекът решава.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol, runtime_checkable

# Скорът е в точки от 0 до 100 — по-четимо за рекрутер от дроб в [0, 1].
SCORE_SCALE = Decimal(100)
# Numeric(7, 4) в ranking.score — квантоваме до същата точност.
SCORE_QUANTUM = Decimal("0.0001")


class ScoringError(Exception):
    """Базова грешка на скоринг слоя."""


class InvalidRulesError(ScoringError):
    """Правилата или изискванията са неизползваеми (лоши тегла, непознат фактор).

    Грешка на конфигурацията — нито кандидатът, нито ролята са виновни.
    """


class ScoringEngineUnavailableError(ScoringError):
    """Заявеният скоринг адаптер липсва в регистъра."""


@runtime_checkable
class ScorableCandidate(Protocol):
    """Толкова от кандидата, колкото скорингът има право да види."""

    profile: dict[str, Any]


@runtime_checkable
class ScorableRole(Protocol):
    """Толкова от ролята, колкото скорингът има нужда да види."""

    requirements: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FactorScore:
    """Приносът на един фактор — редът, който рекрутерът чете."""

    name: str
    # Тежестта от ruleset-а, както е конфигурирана.
    weight: float
    # Изпълнение на фактора, 0..1 — независимо от тежестта му.
    subscore: float
    # Точки, които факторът дава на крайния скор (вече претеглени).
    contribution: Decimal
    matched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        # Decimal не е JSON-сериализуем — explanation-ът отива в JSONB колона.
        return {
            "name": self.name,
            "weight": self.weight,
            "subscore": round(self.subscore, 4),
            "contribution": float(self.contribution),
            "matched": list(self.matched),
            "missing": list(self.missing),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Скор + защо е такъв."""

    score: Decimal
    factors: tuple[FactorScore, ...]
    # Покрити ли са всички задължителни изисквания. Флаг за рекрутера, не
    # присъда: PRD-то забранява автоматично отхвърляне.
    meets_minimum: bool
    engine: str
    ruleset_version: str | None = None

    def to_explanation(self) -> dict[str, Any]:
        """Съдържанието на ranking.explanation."""
        return {
            "engine": self.engine,
            "ruleset_version": self.ruleset_version,
            "score": float(self.score),
            "meets_minimum": self.meets_minimum,
            "factors": [factor.to_dict() for factor in self.factors],
        }


@runtime_checkable
class Scorer(Protocol):
    """Интерфейсът, който всяка скоринг реализация трябва да покрие."""

    name: str

    def score(self, candidate: ScorableCandidate, role: ScorableRole) -> ScoreResult:
        """Класира кандидат спрямо роля.

        Хвърля InvalidRulesError при неизползваеми правила или изисквания.
        """
        ...


def quantize(points: Decimal) -> Decimal:
    """Свежда точките до точността на колоната, без плаващи изненади."""
    return points.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
