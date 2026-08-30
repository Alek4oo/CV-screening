"""Четене на конфигурацията: тежести от ruleset-а, изисквания от ролята.

Двата JSON документа идват от базата и никой не гарантира формата им, затова
разборът е тук, на едно място, и гърми високо с InvalidRulesError вместо да
произведе тихо безсмислен скор.

Разделението следва коментара в модела на ролята: ролята казва *какво* се иска
(умения, години, степен), ruleset-ът казва *колко тежи* всяко от тях.
"""

from dataclasses import dataclass
from typing import Any

from app.parsing import canonical_language, canonical_skill, degree_rank
from app.parsing.vocabulary import DEGREE_RANKS
from app.scoring.base import InvalidRulesError

# Фактори по подразбиране — важат само когато ruleset.definition няма "weights"
# изобщо. Задължителните умения носят половината скор: те са същината на матча.
DEFAULT_WEIGHTS: dict[str, float] = {
    "required_skills": 0.50,
    "preferred_skills": 0.15,
    "experience": 0.25,
    "education": 0.10,
    "languages": 0.00,
}

FACTOR_NAMES: tuple[str, ...] = tuple(DEFAULT_WEIGHTS)


@dataclass(frozen=True, slots=True)
class ScoringRules:
    """Версионирани тежести — това, което прави скоринга проследим."""

    weights: dict[str, float]
    version: str | None = None

    @classmethod
    def from_definition(
        cls, definition: dict[str, Any] | None, version: str | None = None
    ) -> "ScoringRules":
        definition = definition or {}
        if not isinstance(definition, dict):
            raise InvalidRulesError("The ruleset definition must be an object.")

        if "weights" not in definition:
            return cls(weights=dict(DEFAULT_WEIGHTS), version=version)

        raw = definition["weights"]
        if not isinstance(raw, dict):
            raise InvalidRulesError("'weights' must be an object of factor -> weight.")

        unknown = sorted(set(raw) - set(FACTOR_NAMES))
        if unknown:
            # Тихото игнориране би значело, че тежест, която някой е записал в
            # правилата, не влияе на нищо — най-скъпият вид мълчалива грешка.
            raise InvalidRulesError(
                f"Unknown factors in 'weights': {', '.join(unknown)}. "
                f"Known: {', '.join(FACTOR_NAMES)}."
            )

        # Изричните тежести са пълни: каквото не е написано, тежи нула. Иначе
        # „вдигам required_skills на 1" тихо би оставило и подразбиращия се опит.
        weights = {name: 0.0 for name in FACTOR_NAMES}
        for name, value in raw.items():
            weights[name] = _positive_number(value, f"weights.{name}")

        if sum(weights.values()) <= 0:
            raise InvalidRulesError("At least one factor must carry a weight > 0.")

        return cls(weights=weights, version=version)

    def weight_of(self, factor: str) -> float:
        return self.weights.get(factor, 0.0)


@dataclass(frozen=True, slots=True)
class WeightedSkill:
    """Умение с тежест в рамките на своята група."""

    name: str
    weight: float


@dataclass(frozen=True, slots=True)
class RoleRequirements:
    """Изискванията на ролята, приведени до сравними стойности."""

    required_skills: tuple[WeightedSkill, ...] = ()
    preferred_skills: tuple[WeightedSkill, ...] = ()
    min_years_experience: float = 0.0
    min_degree: str | None = None
    languages: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Роля без нито едно изискване не може да подреди когото и да било."""
        return not (
            self.required_skills
            or self.preferred_skills
            or self.min_years_experience
            or self.min_degree
            or self.languages
        )

    @classmethod
    def from_json(cls, requirements: dict[str, Any] | None) -> "RoleRequirements":
        requirements = requirements or {}
        if not isinstance(requirements, dict):
            raise InvalidRulesError("Role requirements must be an object.")

        return cls(
            required_skills=_skills(requirements.get("required_skills"), "required_skills"),
            preferred_skills=_skills(requirements.get("preferred_skills"), "preferred_skills"),
            min_years_experience=_positive_number(
                requirements.get("min_years_experience", 0), "min_years_experience"
            ),
            min_degree=_degree(requirements.get("min_degree")),
            languages=tuple(
                dict.fromkeys(
                    canonical_language(item)
                    for item in _string_list(requirements.get("languages"), "languages")
                )
            ),
        )


def _skills(raw: Any, field: str) -> tuple[WeightedSkill, ...]:
    """Приема ["python"] и [{"name": "python", "weight": 3}] — и двете се срещат."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise InvalidRulesError(f"'{field}' must be a list.")

    skills: dict[str, WeightedSkill] = {}
    for index, item in enumerate(raw):
        if isinstance(item, str):
            name, weight = item, 1.0
        elif isinstance(item, dict):
            name = item.get("name") or item.get("skill") or ""
            weight = _positive_number(item.get("weight", 1), f"{field}[{index}].weight")
        else:
            raise InvalidRulesError(f"'{field}[{index}]' must be a string or an object.")

        if not isinstance(name, str) or not name.strip():
            raise InvalidRulesError(f"'{field}[{index}]' has no skill name.")

        canonical = canonical_skill(name)
        # Повторено умение: печели по-високата тежест, вместо да го броим двойно.
        existing = skills.get(canonical)
        if existing is None or weight > existing.weight:
            skills[canonical] = WeightedSkill(name=canonical, weight=weight)

    if any(skill.weight <= 0 for skill in skills.values()):
        raise InvalidRulesError(f"Weights in '{field}' must be > 0.")

    return tuple(skills.values())


def _degree(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise InvalidRulesError("'min_degree' must be a string.")

    normalized = " ".join(raw.lower().split())
    if degree_rank(normalized) == 0:
        # Степен, която речникът не познава, не може да бъде сравнена с нищо —
        # по-добре отказ сега, отколкото фактор, който тихо дава нула на всички.
        raise InvalidRulesError(
            f"Unknown degree 'min_degree'={raw!r}. "
            f"Known: {', '.join(sorted(DEGREE_RANKS))}."
        )
    return normalized


def _string_list(raw: Any, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise InvalidRulesError(f"'{field}' must be a list.")
    for item in raw:
        if not isinstance(item, str):
            raise InvalidRulesError(f"'{field}' accepts strings only.")
    return tuple(item for item in raw if item.strip())


def _positive_number(value: Any, field: str) -> float:
    # bool е подтип на int в Python — тук е почти сигурно грешка в конфигурацията.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRulesError(f"'{field}' must be a number.")
    if value < 0:
        raise InvalidRulesError(f"'{field}' cannot be negative.")
    return float(value)
