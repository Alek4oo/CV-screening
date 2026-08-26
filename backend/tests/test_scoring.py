"""Правиловият скоринг: формула, обяснимост, конфигурация и граничните случаи.

Тестовете тук не пипат база и не минават през HTTP — двигателят е чиста функция
от (профил, изисквания, тежести) към резултат и се проверява като такава.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.scoring import (
    DEFAULT_WEIGHTS,
    InvalidRulesError,
    RoleRequirements,
    RuleBasedScorer,
    Scorer,
    ScoringEngineUnavailableError,
    ScoringRules,
    build_scorer,
)
from app.scoring.rule_based import CandidateFacts

TODAY_YEAR = 2026

FULL_REQUIREMENTS = {
    "required_skills": ["python", "postgresql"],
    "preferred_skills": ["docker"],
    "min_years_experience": 4,
    "min_degree": "bachelor",
}


def scorer(definition=None, version="2026.08.1") -> RuleBasedScorer:
    return RuleBasedScorer(
        ScoringRules.from_definition(definition, version=version), today_year=TODAY_YEAR
    )


def role(**requirements) -> SimpleNamespace:
    return SimpleNamespace(requirements=requirements)


def candidate(**profile) -> SimpleNamespace:
    return SimpleNamespace(profile=profile)


def factor(result, name):
    return next(item for item in result.factors if item.name == name)


class TestFormula:
    def test_full_match_scores_100(self):
        result = scorer().score(
            candidate(
                skills=["python", "postgresql", "docker"],
                experience=[{"start": "2018", "end": "2024"}],
                education=[{"degree": "master"}],
            ),
            role(**FULL_REQUIREMENTS),
        )
        assert result.score == Decimal("100.0000")
        assert result.meets_minimum is True

    def test_empty_profile_scores_0(self):
        result = scorer().score(candidate(), role(**FULL_REQUIREMENTS))
        assert result.score == Decimal("0.0000")
        assert result.meets_minimum is False

    def test_score_is_the_weighted_sum_of_factors(self):
        # Само задължителните умения са покрити: 0.5 / (0.5+0.15+0.25+0.1) = 50%.
        result = scorer().score(
            candidate(skills=["python", "postgresql"]), role(**FULL_REQUIREMENTS)
        )
        assert result.score == Decimal("50.0000")

    def test_contributions_add_up_to_the_score(self):
        result = scorer().score(
            candidate(
                skills=["python", "docker"],
                experience=[{"start": "2023", "end": "2025"}],
                education=[{"degree": "бакалавър"}],
            ),
            role(**FULL_REQUIREMENTS),
        )
        total = sum(item.contribution for item in result.factors)
        # Разминаване само от квантоването на отделните приноси.
        assert abs(total - result.score) <= Decimal("0.0005")

    def test_score_stays_within_bounds(self):
        result = scorer().score(
            candidate(
                skills=["python", "postgresql", "docker"],
                experience=[{"start": "1990", "end": "2025"}],
                education=[{"degree": "phd"}],
            ),
            role(**FULL_REQUIREMENTS),
        )
        assert Decimal(0) <= result.score <= Decimal(100)

    def test_score_is_quantised_to_the_column_precision(self):
        result = scorer().score(candidate(skills=["python"]), role(**FULL_REQUIREMENTS))
        assert result.score.as_tuple().exponent == -4


class TestActiveFactorsOnly:
    def test_factor_the_role_does_not_ask_for_is_absent(self):
        result = scorer().score(candidate(skills=["python"]), role(required_skills=["python"]))
        assert [item.name for item in result.factors] == ["required_skills"]

    def test_missing_experience_does_not_penalise_when_not_required(self):
        """Роля без искан опит не бива да наказва кандидат без опит."""
        result = scorer().score(candidate(skills=["python"]), role(required_skills=["python"]))
        assert result.score == Decimal("100.0000")

    def test_role_without_requirements_scores_zero_but_meets_minimum(self):
        result = scorer().score(candidate(skills=["python"]), role())
        assert result.score == Decimal("0.0000")
        assert result.factors == ()
        # Няма изискване, което да не е покрито — флагът не бива да лъже.
        assert result.meets_minimum is True

    def test_role_asking_only_for_zero_weight_factors_scores_zero(self):
        """Правилата не тежат нищо на езиците, а ролята иска само тях."""
        result = scorer({"weights": {"required_skills": 1}}).score(
            candidate(languages=["English"]), role(languages=["english"])
        )
        assert result.score == Decimal("0.0000")
        # Факторът се показва въпреки нулевия принос — иначе рекрутерът не вижда
        # защо покритото изискване не е дало точки.
        assert factor(result, "languages").subscore == 1.0
        assert factor(result, "languages").contribution == Decimal("0.0000")


class TestSkills:
    def test_skill_aliases_are_matched_canonically(self):
        result = scorer().score(
            candidate(skills=["postgres"]), role(required_skills=["PostgreSQL"])
        )
        assert factor(result, "required_skills").matched == ("postgresql",)

    def test_skill_weights_shift_the_subscore(self):
        heavy = scorer().score(
            candidate(skills=["python"]),
            role(required_skills=[{"name": "python", "weight": 3}, {"name": "go", "weight": 1}]),
        )
        assert factor(heavy, "required_skills").subscore == pytest.approx(0.75)

    def test_missing_skills_are_listed_for_the_recruiter(self):
        result = scorer().score(
            candidate(skills=["python"]), role(required_skills=["python", "go", "kafka"])
        )
        assert factor(result, "required_skills").missing == ("go", "kafka")

    def test_duplicate_requirement_is_counted_once_with_the_higher_weight(self):
        requirements = RoleRequirements.from_json(
            {"required_skills": ["python", {"name": "Python", "weight": 5}]}
        )
        assert len(requirements.required_skills) == 1
        assert requirements.required_skills[0].weight == 5.0


class TestExperience:
    def test_years_are_summed_across_positions(self):
        result = scorer().score(
            candidate(
                experience=[
                    {"start": "2016", "end": "2019"},
                    {"start": "2019", "end": "2021"},
                ]
            ),
            role(min_years_experience=5),
        )
        assert factor(result, "experience").subscore == pytest.approx(1.0)

    def test_current_position_counts_up_to_today(self):
        result = scorer().score(
            candidate(experience=[{"start": "2024", "end": None, "current": True}]),
            role(min_years_experience=2),
        )
        assert factor(result, "experience").subscore == pytest.approx(1.0)

    def test_more_experience_than_asked_is_capped_at_one(self):
        result = scorer().score(
            candidate(experience=[{"start": "2000", "end": "2025"}]),
            role(min_years_experience=3),
        )
        assert factor(result, "experience").subscore == 1.0

    def test_partial_experience_scores_proportionally(self):
        result = scorer().score(
            candidate(experience=[{"start": "2023", "end": "2025"}]),
            role(min_years_experience=4),
        )
        assert factor(result, "experience").subscore == pytest.approx(0.5)

    def test_month_prefixed_dates_are_understood(self):
        result = scorer().score(
            candidate(experience=[{"start": "03.2019", "end": "05.2023"}]),
            role(min_years_experience=4),
        )
        assert factor(result, "experience").subscore == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "entry",
        [
            {"start": None, "end": "2023"},
            {"start": "2019"},
            {"start": "не е година", "end": "2023"},
            {"start": "2023", "end": "2019"},  # обърнат период не дава отрицателни години
            "не е обект",
        ],
    )
    def test_unusable_entries_are_ignored(self, entry):
        result = scorer().score(
            candidate(experience=[entry]), role(min_years_experience=3)
        )
        assert factor(result, "experience").subscore == 0.0


class TestEducation:
    @pytest.mark.parametrize(
        ("degree", "expected"),
        [("бакалавър", 1.0), ("master", 1.0), ("магистър", 1.0), ("phd", 1.0)],
    )
    def test_equal_or_higher_degree_satisfies_the_requirement(self, degree, expected):
        result = scorer().score(
            candidate(education=[{"degree": degree}]), role(min_degree="bachelor")
        )
        assert factor(result, "education").subscore == expected

    def test_lower_degree_scores_proportionally(self):
        result = scorer().score(
            candidate(education=[{"degree": "high school"}]), role(min_degree="master")
        )
        # ранг 1 от искан ранг 4
        assert factor(result, "education").subscore == pytest.approx(0.25)

    def test_highest_degree_wins_over_the_last_one(self):
        result = scorer().score(
            candidate(education=[{"degree": "phd"}, {"degree": "high school"}]),
            role(min_degree="master"),
        )
        assert factor(result, "education").subscore == 1.0

    def test_unrecognised_degree_scores_zero(self):
        result = scorer().score(
            candidate(education=[{"degree": "университет"}]), role(min_degree="bachelor")
        )
        assert factor(result, "education").subscore == 0.0


class TestLanguages:
    def test_language_aliases_are_matched(self):
        result = scorer({"weights": {"languages": 1}}).score(
            candidate(languages=["Английски", "Български"]),
            role(languages=["english", "bulgarian"]),
        )
        assert result.score == Decimal("100.0000")

    def test_partial_language_coverage(self):
        result = scorer({"weights": {"languages": 1}}).score(
            candidate(languages=["Български"]), role(languages=["english", "bulgarian"])
        )
        assert factor(result, "languages").subscore == pytest.approx(0.5)
        assert factor(result, "languages").missing == ("english",)


class TestMinimumFlagIsNotRejection:
    def test_missing_required_skill_lowers_the_flag_but_keeps_points(self):
        result = scorer().score(
            candidate(
                skills=["python", "docker"],
                experience=[{"start": "2018", "end": "2024"}],
                education=[{"degree": "master"}],
            ),
            role(**FULL_REQUIREMENTS),
        )
        assert result.meets_minimum is False
        # Никакво авто-отхвърляне: кандидатът си остава в класацията.
        assert result.score > Decimal(0)

    def test_short_experience_lowers_the_flag(self):
        result = scorer().score(
            candidate(
                skills=["python", "postgresql"],
                experience=[{"start": "2024", "end": "2025"}],
            ),
            role(**FULL_REQUIREMENTS),
        )
        assert result.meets_minimum is False

    def test_missing_language_lowers_the_flag(self):
        result = scorer().score(
            candidate(languages=["Български"]), role(languages=["english"])
        )
        assert result.meets_minimum is False


class TestConfigurableWeights:
    def test_weights_change_the_outcome_for_the_same_candidate(self):
        applicant = candidate(
            skills=["docker"],
            experience=[{"start": "2018", "end": "2026"}],
        )
        requirements = role(
            required_skills=["python"], preferred_skills=["docker"], min_years_experience=4
        )

        skills_first = scorer({"weights": {"required_skills": 1, "preferred_skills": 1}})
        experience_first = scorer({"weights": {"experience": 1}})

        assert skills_first.score(applicant, requirements).score == Decimal("50.0000")
        assert experience_first.score(applicant, requirements).score == Decimal("100.0000")

    def test_explicit_weights_zero_out_the_unlisted_factors(self):
        rules = ScoringRules.from_definition({"weights": {"required_skills": 1}})
        assert rules.weights["experience"] == 0.0

    def test_defaults_apply_only_when_weights_are_absent(self):
        rules = ScoringRules.from_definition({})
        assert rules.weights == DEFAULT_WEIGHTS

    def test_rules_carry_the_version_into_the_result(self):
        result = scorer(version="2026.08.2").score(
            candidate(skills=["python"]), role(required_skills=["python"])
        )
        assert result.ruleset_version == "2026.08.2"


class TestInvalidConfiguration:
    @pytest.mark.parametrize(
        "definition",
        [
            {"weights": {"charisma": 1}},
            {"weights": {"required_skills": -1}},
            {"weights": {"required_skills": "много"}},
            {"weights": {"required_skills": 0, "experience": 0}},
            {"weights": []},
            {"weights": {"required_skills": True}},
        ],
    )
    def test_unusable_rules_are_rejected(self, definition):
        with pytest.raises(InvalidRulesError):
            ScoringRules.from_definition(definition)

    @pytest.mark.parametrize(
        "requirements",
        [
            {"required_skills": "python"},
            {"required_skills": [123]},
            {"required_skills": [{"name": ""}]},
            {"required_skills": [{"name": "python", "weight": -2}]},
            {"min_years_experience": -1},
            {"min_years_experience": "три"},
            {"min_degree": "бакалавърче"},
            {"languages": [42]},
        ],
    )
    def test_unusable_requirements_are_rejected(self, requirements):
        with pytest.raises(InvalidRulesError):
            RoleRequirements.from_json(requirements)

    def test_unknown_backend_is_reported_as_unavailable(self, monkeypatch):
        from app.core import config

        monkeypatch.setattr(config.settings, "scoring_backend", "astrology")
        with pytest.raises(ScoringEngineUnavailableError):
            build_scorer(SimpleNamespace(version="2026.08.1", definition={}))


class TestExplainability:
    def test_every_factor_carries_weight_subscore_and_points(self):
        result = scorer().score(
            candidate(skills=["python"], education=[{"degree": "master"}]),
            role(**FULL_REQUIREMENTS),
        )
        for item in result.factors:
            assert item.detail
            assert 0.0 <= item.subscore <= 1.0
            assert item.contribution >= Decimal(0)

    def test_explanation_is_json_serialisable(self):
        """Отива в JSONB колона — Decimal там би гръмнал при запис."""
        result = scorer().score(
            candidate(skills=["python"]), role(**FULL_REQUIREMENTS)
        )
        encoded = json.dumps(result.to_explanation(), ensure_ascii=False)
        assert "rule_based" in encoded
        assert "2026.08.1" in encoded

    def test_explanation_lists_matched_and_missing(self):
        explanation = (
            scorer()
            .score(candidate(skills=["python"]), role(required_skills=["python", "go"]))
            .to_explanation()
        )
        required = next(f for f in explanation["factors"] if f["name"] == "required_skills")
        assert required["matched"] == ["python"]
        assert required["missing"] == ["go"]


class TestProtectedAttributesAreOutOfReach:
    def test_protected_attributes_do_not_change_the_score(self):
        profile = {"skills": ["python"], "experience": [{"start": "2020", "end": "2026"}]}
        requirements = role(required_skills=["python"], min_years_experience=3)

        plain = SimpleNamespace(profile=profile)
        with_protected = SimpleNamespace(
            profile=profile, protected_attributes={"gender": "female", "age": 41}
        )

        assert scorer().score(plain, requirements).score == (
            scorer().score(with_protected, requirements).score
        )

    def test_facts_are_built_from_the_profile_alone(self):
        facts = CandidateFacts.from_profile(
            {"skills": ["Python"], "languages": ["Английски"]}, today_year=TODAY_YEAR
        )
        assert facts.skills == frozenset({"python"})
        assert facts.languages == frozenset({"english"})
        assert not hasattr(facts, "protected_attributes")


class TestSwappability:
    def test_rule_based_scorer_satisfies_the_protocol(self):
        assert isinstance(scorer(), Scorer)

    def test_custom_scorer_satisfies_the_protocol(self):
        class ConstantScorer:
            name = "constant"

            def score(self, candidate, role):
                raise NotImplementedError

        assert isinstance(ConstantScorer(), Scorer)

    def test_build_scorer_uses_the_configured_backend(self):
        built = build_scorer(SimpleNamespace(version="2026.08.1", definition={}))
        assert built.name == "rule_based"
        assert built.rules.version == "2026.08.1"


class TestDefensiveInputs:
    @pytest.mark.parametrize("profile", [None, {}, {"skills": None}, {"skills": "python"}])
    def test_broken_profiles_score_zero_instead_of_crashing(self, profile):
        result = scorer().score(SimpleNamespace(profile=profile), role(**FULL_REQUIREMENTS))
        assert result.score == Decimal("0.0000")

    def test_non_string_skills_are_ignored(self):
        result = scorer().score(
            candidate(skills=["python", 42, None]), role(required_skills=["python"])
        )
        assert factor(result, "required_skills").matched == ("python",)

    def test_missing_requirements_key_is_treated_as_no_requirements(self):
        result = scorer().score(candidate(skills=["python"]), SimpleNamespace(requirements=None))
        assert result.score == Decimal("0.0000")
        assert result.meets_minimum is True
