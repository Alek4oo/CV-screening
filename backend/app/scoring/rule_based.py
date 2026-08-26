"""Правилов скоринг: сравнява профила с изискванията по конфигурируеми тежести.

Формулата е нарочно проста, защото рекрутерът трябва да може да я провери с очи:

    скор = 100 × Σ(тежест_фактор × изпълнение_фактор) / Σ(тежест_фактор)

`изпълнение` е число в [0, 1] за всеки фактор поотделно, а нормализацията по
сумата на тежестите значи, че скорът е в 0..100 независимо какви тежести са
конфигурирани. Участват само факторите, за които ролята има изискване — роля
без искани езици не наказва никого за липсата им.

Умишлено няма автоматично отхвърляне. Непокритото задължително умение сваля
скора и вдига флага `meets_minimum=False`; решението остава на човек.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.parsing import canonical_language, canonical_skill, degree_rank
from app.scoring.base import (
    SCORE_SCALE,
    FactorScore,
    ScorableCandidate,
    ScorableRole,
    ScoreResult,
    quantize,
)
from app.scoring.rules import RoleRequirements, ScoringRules, WeightedSkill


@dataclass(frozen=True, slots=True)
class CandidateFacts:
    """Профилът, сведен до сравнимите факти. Нищо защитено не влиза тук."""

    skills: frozenset[str]
    years_experience: float
    degree: str | None
    degree_rank: int
    languages: frozenset[str]

    @classmethod
    def from_profile(cls, profile: dict[str, Any] | None, today_year: int) -> "CandidateFacts":
        profile = profile or {}
        education = [item for item in _as_list(profile.get("education")) if isinstance(item, dict)]
        # Най-високата степен, не последната по време — иначе доктор с курс
        # отгоре би изглеждал по-слаб от самия себе си.
        best = max(education, key=lambda item: degree_rank(_text(item.get("degree"))), default=None)
        best_degree = _text(best.get("degree")) if best else None

        return cls(
            skills=frozenset(
                canonical_skill(skill)
                for skill in _as_list(profile.get("skills"))
                if isinstance(skill, str) and skill.strip()
            ),
            years_experience=_years_of_experience(_as_list(profile.get("experience")), today_year),
            degree=best_degree,
            degree_rank=degree_rank(best_degree),
            languages=frozenset(
                canonical_language(language)
                for language in _as_list(profile.get("languages"))
                if isinstance(language, str) and language.strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class _RawFactor:
    """Фактор преди претегляне — самото изпълнение, без тежест и точки."""

    name: str
    subscore: float
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    detail: str


class RuleBasedScorer:
    """Скорер, чиито тежести идват от версия правила (ruleset)."""

    name = "rule_based"

    def __init__(self, rules: ScoringRules, today_year: int | None = None) -> None:
        self.rules = rules
        # Инжектира се в тестовете, за да не зависи резултатът от календара.
        self.today_year = today_year or date.today().year

    def score(self, candidate: ScorableCandidate, role: ScorableRole) -> ScoreResult:
        requirements = RoleRequirements.from_json(getattr(role, "requirements", None))
        facts = CandidateFacts.from_profile(getattr(candidate, "profile", None), self.today_year)

        raw_factors = [
            factor
            for factor in (
                _required_skills(facts, requirements.required_skills),
                _preferred_skills(facts, requirements.preferred_skills),
                _experience(facts, requirements.min_years_experience),
                _education(facts, requirements.min_degree),
                _languages(facts, requirements.languages),
            )
            if factor is not None
        ]

        factors, total = self._weigh(raw_factors)
        return ScoreResult(
            score=quantize(total),
            factors=factors,
            meets_minimum=_meets_minimum(facts, requirements),
            engine=self.name,
            ruleset_version=self.rules.version,
        )

    def _weigh(self, raw_factors: list[_RawFactor]) -> tuple[tuple[FactorScore, ...], Decimal]:
        """Претегля, нормализира и връща (фактори, суров общ скор)."""
        weights = {factor.name: self.rules.weight_of(factor.name) for factor in raw_factors}
        total_weight = Decimal(str(sum(weights.values())))

        factors: list[FactorScore] = []
        total = Decimal(0)
        for factor in raw_factors:
            weight = weights[factor.name]
            if total_weight > 0:
                share = Decimal(str(weight)) / total_weight
                contribution = SCORE_SCALE * share * Decimal(str(factor.subscore))
            else:
                # Ролята иска само фактори с нулева тежест — никой не печели точки.
                contribution = Decimal(0)

            total += contribution
            factors.append(
                FactorScore(
                    name=factor.name,
                    weight=weight,
                    subscore=factor.subscore,
                    contribution=quantize(contribution),
                    matched=factor.matched,
                    missing=factor.missing,
                    detail=factor.detail,
                )
            )

        return tuple(factors), total


# --- отделните фактори ---


def _required_skills(facts: CandidateFacts, required: tuple[WeightedSkill, ...]) -> _RawFactor | None:
    if not required:
        return None
    return _skill_factor("required_skills", facts, required, "задължителни")


def _preferred_skills(
    facts: CandidateFacts, preferred: tuple[WeightedSkill, ...]
) -> _RawFactor | None:
    if not preferred:
        return None
    return _skill_factor("preferred_skills", facts, preferred, "предпочитани")


def _skill_factor(
    name: str, facts: CandidateFacts, wanted: tuple[WeightedSkill, ...], label: str
) -> _RawFactor:
    matched = tuple(skill.name for skill in wanted if skill.name in facts.skills)
    missing = tuple(skill.name for skill in wanted if skill.name not in facts.skills)

    total_weight = sum(skill.weight for skill in wanted)
    covered = sum(skill.weight for skill in wanted if skill.name in facts.skills)
    subscore = covered / total_weight if total_weight else 0.0

    return _RawFactor(
        name=name,
        subscore=subscore,
        matched=matched,
        missing=missing,
        detail=(
            f"Покрити {len(matched)} от {len(wanted)} {label} умения "
            f"({subscore:.0%} по тежест)."
        ),
    )


def _experience(facts: CandidateFacts, min_years: float) -> _RawFactor | None:
    if min_years <= 0:
        return None

    years = facts.years_experience
    subscore = min(1.0, years / min_years)
    return _RawFactor(
        name="experience",
        subscore=subscore,
        matched=(f"{years:g} г.",) if years else (),
        missing=() if years >= min_years else (f"липсват {min_years - years:g} г.",),
        detail=f"{years:g} години опит при искани {min_years:g}.",
    )


def _education(facts: CandidateFacts, min_degree: str | None) -> _RawFactor | None:
    if not min_degree:
        return None

    required_rank = degree_rank(min_degree)
    # По-висока степен не носи бонус — изискването е праг, не състезание.
    subscore = min(1.0, facts.degree_rank / required_rank) if required_rank else 0.0
    return _RawFactor(
        name="education",
        subscore=subscore,
        matched=(facts.degree,) if facts.degree else (),
        missing=() if facts.degree_rank >= required_rank else (min_degree,),
        detail=(
            f"Степен {facts.degree or 'няма разпозната'} (ранг {facts.degree_rank}) "
            f"при искана {min_degree} (ранг {required_rank})."
        ),
    )


def _languages(facts: CandidateFacts, wanted: tuple[str, ...]) -> _RawFactor | None:
    if not wanted:
        return None

    matched = tuple(language for language in wanted if language in facts.languages)
    missing = tuple(language for language in wanted if language not in facts.languages)
    return _RawFactor(
        name="languages",
        subscore=len(matched) / len(wanted),
        matched=matched,
        missing=missing,
        detail=f"Покрити {len(matched)} от {len(wanted)} езика.",
    )


def _meets_minimum(facts: CandidateFacts, requirements: RoleRequirements) -> bool:
    """Покрити ли са всички твърди изисквания. Предпочитаните не се броят."""
    if any(skill.name not in facts.skills for skill in requirements.required_skills):
        return False
    if facts.years_experience < requirements.min_years_experience:
        return False
    if requirements.min_degree and facts.degree_rank < degree_rank(requirements.min_degree):
        return False
    return all(language in facts.languages for language in requirements.languages)


# --- помощни ---


def _years_of_experience(entries: list[Any], today_year: int) -> float:
    """Сума от периодите в години.

    Застъпващи се позиции се броят два пъти — грубо, но предвидимо, а суровият
    текст остава в CV-то, ако рекрутерът иска да провери.
    """
    total = 0.0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        start = _year(entry.get("start"))
        if start is None:
            continue
        end = today_year if entry.get("current") else _year(entry.get("end"))
        if end is None:
            continue
        total += max(0.0, float(end - start))
    return total


def _year(value: Any) -> int | None:
    """Изважда годината от "2019" и "03.2019"; None при всичко останало."""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 4:
        return None
    return int(digits[-4:])


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
