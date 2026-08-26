"""POST /roles/{id}/rank — класиране, проследимост и отказите по пътя."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.main import app
from app.models import (
    AuditAction,
    AuditLog,
    Candidate,
    Ranking,
    RankingMode,
    Role,
    RoleStatus,
    Ruleset,
    RulesetStatus,
)
from app.scoring import ScoreResult, get_scorer_factory

WEIGHTS = {"required_skills": 0.6, "experience": 0.4}


@pytest.fixture
def ruleset(session) -> Ruleset:
    row = Ruleset(
        version="2026.08.1",
        name="Базови правила",
        definition={"weights": WEIGHTS},
        status=RulesetStatus.ACTIVE,
        activated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def role(session) -> Role:
    row = Role(
        title="Backend Developer",
        requirements={
            "required_skills": ["python", "postgresql"],
            "min_years_experience": 4,
        },
        status=RoleStatus.OPEN,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def candidates(session) -> list[Candidate]:
    rows = [
        Candidate(
            full_name="Ivan Petrov",  # покрива всичко
            profile={
                "skills": ["python", "postgresql", "docker"],
                "experience": [{"start": "2018", "end": "2024"}],
            },
            protected_attributes={"gender": "male"},
        ),
        Candidate(
            full_name="Maria Ivanova",  # умения да, опит малко
            profile={
                "skills": ["python", "postgresql"],
                "experience": [{"start": "2024", "end": "2026"}],
            },
            protected_attributes={},
        ),
        Candidate(
            full_name="Georgi Georgiev",  # почти нищо
            profile={"skills": ["php"], "experience": []},
            protected_attributes={},
        ),
    ]
    session.add_all(rows)
    session.commit()
    return rows


def rank(client, role_id, **body):
    return client.post(f"/roles/{role_id}/rank", json=body or None)


class TestHappyPath:
    def test_returns_candidates_ordered_by_score(self, client, ruleset, role, candidates):
        response = rank(client, role.id)
        assert response.status_code == 200, response.text

        body = response.json()
        assert [row["full_name"] for row in body["ranked"]] == [
            "Ivan Petrov",
            "Maria Ivanova",
            "Georgi Georgiev",
        ]
        assert [row["position"] for row in body["ranked"]] == [1, 2, 3]
        assert body["ranked"][0]["score"] == 100.0
        assert body["ranked"][-1]["score"] == 0.0

    def test_response_names_the_ruleset_engine_and_mode(self, client, ruleset, role, candidates):
        body = rank(client, role.id).json()
        assert body["ruleset_version"] == "2026.08.1"
        assert body["ruleset_id"] == str(ruleset.id)
        assert body["engine"] == "rule_based"
        assert body["mode"] == "masked"
        assert body["role_title"] == "Backend Developer"

    def test_each_candidate_carries_the_factor_breakdown(self, client, ruleset, role, candidates):
        top = rank(client, role.id).json()["ranked"][0]
        factors = {item["name"]: item for item in top["factors"]}

        assert set(factors) == {"required_skills", "experience"}
        assert factors["required_skills"]["contribution"] == 60.0
        assert factors["experience"]["contribution"] == 40.0
        assert factors["required_skills"]["matched"] == ["python", "postgresql"]
        assert factors["required_skills"]["detail"]

    def test_partial_match_is_ranked_not_rejected(self, client, ruleset, role, candidates):
        weak = rank(client, role.id).json()["ranked"][-1]
        assert weak["meets_minimum"] is False
        # Липсващият минимум не изхвърля кандидата от класацията.
        assert weak["candidate_id"]

    def test_empty_candidate_pool_gives_an_empty_ranking(self, client, ruleset, role):
        body = rank(client, role.id).json()
        assert body["ranked"] == []


class TestPersistence:
    def test_writes_one_ranking_per_candidate(self, client, session, ruleset, role, candidates):
        rank(client, role.id)

        rankings = session.scalars(select(Ranking)).all()
        assert len(rankings) == len(candidates)
        assert {row.ruleset_id for row in rankings} == {ruleset.id}
        assert {row.mode for row in rankings} == {RankingMode.MASKED}

    def test_ranking_stores_score_and_explanation(self, client, session, ruleset, role, candidates):
        rank(client, role.id)

        top = session.scalars(
            select(Ranking).order_by(Ranking.score.desc())
        ).first()
        assert Decimal(str(top.score)) == Decimal("100.0000")
        assert top.explanation["engine"] == "rule_based"
        assert top.explanation["ruleset_version"] == "2026.08.1"
        assert [factor["name"] for factor in top.explanation["factors"]] == [
            "required_skills",
            "experience",
        ]

    def test_rerunning_updates_instead_of_duplicating(
        self, client, session, ruleset, role, candidates
    ):
        rank(client, role.id)
        rank(client, role.id)

        assert len(session.scalars(select(Ranking)).all()) == len(candidates)

    def test_rerunning_picks_up_a_changed_profile(
        self, client, session, ruleset, role, candidates
    ):
        rank(client, role.id)

        weak = session.scalars(
            select(Candidate).where(Candidate.full_name == "Georgi Georgiev")
        ).one()
        weak.profile = {
            "skills": ["python", "postgresql"],
            "experience": [{"start": "2010", "end": "2026"}],
        }
        session.commit()

        body = rank(client, role.id).json()
        assert body["ranked"][0]["score"] == 100.0
        updated = session.scalars(
            select(Ranking).where(Ranking.candidate_id == weak.id)
        ).one()
        assert Decimal(str(updated.score)) == Decimal("100.0000")

    def test_a_new_ruleset_creates_new_rows_and_keeps_the_old(
        self, client, session, ruleset, role, candidates
    ):
        rank(client, role.id)

        session.add(
            Ruleset(
                version="2026.09.1",
                name="Само умения",
                definition={"weights": {"required_skills": 1}},
                status=RulesetStatus.ACTIVE,
                activated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

        body = rank(client, role.id).json()
        assert body["ruleset_version"] == "2026.09.1"
        # Старите класирания остават — решение, взето с тях, трябва да сочи нанякъде.
        assert len(session.scalars(select(Ranking)).all()) == 2 * len(candidates)

    def test_writes_an_audit_entry_per_candidate(
        self, client, session, ruleset, role, candidates
    ):
        rank(client, role.id)

        entries = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.CANDIDATE_SCORED)
        ).all()
        assert len(entries) == len(candidates)

        entry = entries[0]
        assert entry.entity_type == "ranking"
        assert entry.ruleset_id == ruleset.id
        assert entry.payload_in["role_id"] == str(role.id)
        assert entry.payload_in["mode"] == "masked"
        assert entry.payload_out["engine"] == "rule_based"
        assert entry.payload_out["factors"]


class TestSelection:
    def test_candidate_ids_narrow_the_pool(self, client, ruleset, role, candidates):
        chosen = candidates[1]
        body = rank(client, role.id, candidate_ids=[str(chosen.id)]).json()
        assert [row["full_name"] for row in body["ranked"]] == [chosen.full_name]

    def test_unknown_candidate_id_is_a_404(self, client, ruleset, role, candidates):
        unknown = "00000000-0000-0000-0000-000000000000"
        response = rank(client, role.id, candidate_ids=[unknown])
        assert response.status_code == 404
        assert unknown in response.json()["detail"]

    def test_explicit_ruleset_version_is_used(self, client, session, ruleset, role, candidates):
        session.add(
            Ruleset(
                version="2026.07.1",
                name="Стари правила",
                definition={"weights": {"required_skills": 1}},
                status=RulesetStatus.RETIRED,
            )
        )
        session.commit()

        body = rank(client, role.id, ruleset_version="2026.07.1").json()
        assert body["ruleset_version"] == "2026.07.1"
        # Само уменията тежат — слабият кандидат остава на нула, силните са равни.
        assert body["ranked"][0]["score"] == 100.0

    def test_unknown_ruleset_version_is_a_404(self, client, ruleset, role, candidates):
        response = rank(client, role.id, ruleset_version="няма такава")
        assert response.status_code == 404


class TestRefusals:
    def test_unknown_role_is_a_404(self, client, ruleset):
        response = rank(client, "00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_no_active_ruleset_is_a_409(self, client, session, role, candidates):
        response = rank(client, role.id)
        assert response.status_code == 409
        assert "активна версия правила" in response.json()["detail"]

    def test_unusable_ruleset_definition_is_a_409(self, client, session, role, candidates):
        session.add(
            Ruleset(
                version="2026.08.9",
                name="Счупени правила",
                definition={"weights": {"charisma": 1}},
                status=RulesetStatus.ACTIVE,
                activated_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
            )
        )
        session.commit()

        response = rank(client, role.id)
        assert response.status_code == 409
        assert "charisma" in response.json()["detail"]

    def test_unusable_role_requirements_are_a_409(self, client, session, ruleset, candidates):
        broken = Role(title="Счупена роля", requirements={"min_years_experience": "три"})
        session.add(broken)
        session.commit()

        response = rank(client, broken.id)
        assert response.status_code == 409
        assert "неизползваеми" in response.json()["detail"]

    def test_nothing_is_persisted_when_the_rules_are_unusable(
        self, client, session, ruleset, candidates
    ):
        broken = Role(title="Счупена роля", requirements={"required_skills": [{"name": ""}]})
        session.add(broken)
        session.commit()

        rank(client, broken.id)
        assert session.scalars(select(Ranking)).all() == []
        assert session.scalars(select(AuditLog)).all() == []


class TestSwappableAdapterEndToEnd:
    def test_endpoint_uses_the_injected_scorer(self, client, ruleset, role, candidates):
        """Смяната на скоринг адаптер не изисква промяна в API слоя."""

        class ConstantScorer:
            name = "constant"

            def score(self, candidate, role) -> ScoreResult:
                return ScoreResult(
                    score=Decimal("42.0000"),
                    factors=(),
                    meets_minimum=True,
                    engine=self.name,
                    ruleset_version="stub",
                )

        app.dependency_overrides[get_scorer_factory] = lambda: (lambda ruleset: ConstantScorer())
        try:
            body = rank(client, role.id).json()
        finally:
            app.dependency_overrides.pop(get_scorer_factory)

        assert body["engine"] == "constant"
        assert {row["score"] for row in body["ranked"]} == {42.0}
        # Равните скорове излизат подредени по име, за да не „трепти" класацията.
        assert [row["full_name"] for row in body["ranked"]] == [
            "Georgi Georgiev",
            "Ivan Petrov",
            "Maria Ivanova",
        ]
