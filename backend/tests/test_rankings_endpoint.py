"""GET /roles/{id}/rankings и GET /rankings/{id} — класацията, както я чете UI-ът."""

from datetime import datetime, timezone

import pytest

from app.models import (
    Candidate,
    Decision,
    DecisionOutcome,
    Ranking,
    RankingMode,
    Role,
    RoleStatus,
    Ruleset,
    RulesetStatus,
)

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
def ranked(client, session, ruleset, role) -> list[Candidate]:
    """Три кандидата, класирани през същия ендпойнт, който ползва продукцията."""
    rows = [
        Candidate(
            full_name="Ivan Petrov",
            email="ivan@example.com",
            profile={
                "skills": ["python", "postgresql", "docker"],
                "experience": [{"start": "2018", "end": "2024"}],
            },
            protected_attributes={"gender": "male"},
        ),
        Candidate(
            full_name="Maria Ivanova",
            email="maria@example.com",
            profile={
                "skills": ["python", "postgresql"],
                "experience": [{"start": "2024", "end": "2026"}],
            },
            protected_attributes={},
        ),
        Candidate(
            full_name="Georgi Georgiev",
            email=None,
            profile={"skills": ["php"], "experience": []},
            protected_attributes={},
        ),
    ]
    session.add_all(rows)
    session.commit()

    assert client.post(f"/roles/{role.id}/rank").status_code == 200
    return rows


def rankings(client, role_id, **params):
    return client.get(f"/roles/{role_id}/rankings", params=params)


def ranking_id_of(client, role_id, name: str) -> str:
    rows = rankings(client, role_id).json()["rows"]
    return next(row["ranking_id"] for row in rows if row["full_name"] == name)


class TestList:
    def test_returns_the_stored_ranking_ordered_by_score(self, client, role, ranked):
        response = rankings(client, role.id)
        assert response.status_code == 200, response.text

        body = response.json()
        assert [row["full_name"] for row in body["rows"]] == [
            "Ivan Petrov",
            "Maria Ivanova",
            "Georgi Georgiev",
        ]
        assert [row["position"] for row in body["rows"]] == [1, 2, 3]
        assert body["total"] == 3
        assert body["total_unfiltered"] == 3

    def test_names_the_role_ruleset_and_mode(self, client, role, ruleset, ranked):
        body = rankings(client, role.id).json()
        assert body["role_title"] == "Backend Developer"
        assert body["role_status"] == "open"
        assert body["ruleset"]["version"] == "2026.08.1"
        assert body["ruleset"]["id"] == str(ruleset.id)
        assert body["mode"] == "masked"
        assert [item["version"] for item in body["available_rulesets"]] == ["2026.08.1"]

    def test_row_carries_the_summary_the_table_shows(self, client, role, ranked):
        top = rankings(client, role.id).json()["rows"][0]
        assert top["score"] == 100.0
        assert top["meets_minimum"] is True
        assert top["outcome"] == "pending"
        assert top["decided_by"] is None
        assert [factor["name"] for factor in top["top_factors"]] == [
            "required_skills",
            "experience",
        ]

    def test_missing_hard_requirements_are_listed_not_filtered(self, client, role, ranked):
        weak = rankings(client, role.id).json()["rows"][-1]
        assert weak["full_name"] == "Georgi Georgiev"
        assert weak["meets_minimum"] is False
        assert "python" in weak["missing"]
        # Непокритият минимум не изхвърля кандидата и не му слага статус.
        assert weak["outcome"] == "pending"

    def test_counts_are_by_decision_status(self, client, role, ranked):
        counts = rankings(client, role.id).json()["counts"]
        assert counts == {"pending": 3, "advanced": 0, "rejected": 0, "on_hold": 0}

    def test_role_without_rankings_returns_an_empty_table(self, client, role):
        body = rankings(client, role.id).json()
        assert body["rows"] == []
        assert body["ruleset"] is None
        assert body["total_unfiltered"] == 0

    def test_unknown_role_is_404(self, client):
        assert rankings(client, "00000000-0000-0000-0000-000000000000").status_code == 404


class TestFilters:
    def test_filters_by_minimum_flag(self, client, role, ranked):
        # Мария покрива уменията, но не и исканите 4 години опит.
        body = rankings(client, role.id, meets_minimum=False).json()
        assert [row["full_name"] for row in body["rows"]] == ["Maria Ivanova", "Georgi Georgiev"]
        assert body["total"] == 2
        assert body["total_unfiltered"] == 3

        covered = rankings(client, role.id, meets_minimum=True).json()
        assert [row["full_name"] for row in covered["rows"]] == ["Ivan Petrov"]

    def test_filters_by_score_range(self, client, role, ranked):
        body = rankings(client, role.id, min_score=50).json()
        assert [row["full_name"] for row in body["rows"]] == ["Ivan Petrov", "Maria Ivanova"]

    def test_searches_name_and_email(self, client, role, ranked):
        assert [row["full_name"] for row in rankings(client, role.id, q="maria").json()["rows"]] == [
            "Maria Ivanova"
        ]
        assert [
            row["full_name"] for row in rankings(client, role.id, q="ivan@example").json()["rows"]
        ] == ["Ivan Petrov"]

    def test_filters_by_decision_outcome(self, client, role, ranked):
        target = ranking_id_of(client, role.id, "Maria Ivanova")
        client.put(
            f"/rankings/{target}/decision",
            json={"outcome": "advanced", "decided_by": "recruiter", "rationale": "покрива"},
        )

        body = rankings(client, role.id, outcome="advanced").json()
        assert [row["full_name"] for row in body["rows"]] == ["Maria Ivanova"]
        assert body["counts"]["advanced"] == 1
        assert body["counts"]["pending"] == 2

    def test_position_survives_filtering(self, client, role, ranked):
        # Филтърът скрива редове, но не преномерира класацията — №3 си остава №3.
        body = rankings(client, role.id, meets_minimum=False).json()
        assert [row["position"] for row in body["rows"]] == [2, 3]

    def test_sort_by_name(self, client, role, ranked):
        names = [row["full_name"] for row in rankings(client, role.id, sort="name_asc").json()["rows"]]
        assert names == ["Georgi Georgiev", "Ivan Petrov", "Maria Ivanova"]

        names = [
            row["full_name"] for row in rankings(client, role.id, sort="name_desc").json()["rows"]
        ]
        assert names == ["Maria Ivanova", "Ivan Petrov", "Georgi Georgiev"]

    def test_unknown_sort_is_422(self, client, role, ranked):
        assert rankings(client, role.id, sort="score").status_code == 422

    def test_paginates(self, client, role, ranked):
        body = rankings(client, role.id, limit=1, offset=1).json()
        assert [row["full_name"] for row in body["rows"]] == ["Maria Ivanova"]
        assert body["total"] == 3

    def test_unknown_ruleset_version_is_409(self, client, role, ranked):
        response = rankings(client, role.id, ruleset_version="1999.1.1")
        assert response.status_code == 409
        assert "2026.08.1" in response.json()["detail"]


class TestDetail:
    def test_returns_the_full_explanation(self, client, role, ruleset, ranked):
        target = ranking_id_of(client, role.id, "Ivan Petrov")
        response = client.get(f"/rankings/{target}")
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["position"] == 1
        assert body["score"] == 100.0
        assert body["meets_minimum"] is True
        assert body["mode"] == "masked"
        assert body["engine"] == "rule_based"
        assert body["weights"] == WEIGHTS
        assert {factor["name"] for factor in body["factors"]} == {
            "required_skills",
            "experience",
        }
        assert body["ruleset"]["version"] == "2026.08.1"
        assert body["role"]["requirements"]["required_skills"] == ["python", "postgresql"]
        assert body["decision"] is None

    def test_candidate_block_never_carries_protected_attributes(self, client, role, ranked):
        target = ranking_id_of(client, role.id, "Ivan Petrov")
        body = client.get(f"/rankings/{target}").json()

        assert body["candidate"]["full_name"] == "Ivan Petrov"
        assert body["candidate"]["profile"]["skills"]
        # Кандидатът има записан пол — изгледът за рекрутер не го получава.
        assert "protected_attributes" not in body["candidate"]

    def test_unknown_ranking_is_404(self, client):
        assert client.get("/rankings/00000000-0000-0000-0000-000000000000").status_code == 404


class TestCandidateEndpoints:
    def test_lists_and_searches_candidates(self, client, ranked):
        assert len(client.get("/candidates").json()) == 3
        found = client.get("/candidates", params={"q": "georgi"}).json()
        assert [row["full_name"] for row in found] == ["Georgi Georgiev"]

    def test_candidate_detail_hides_protected_attributes(self, client, session, ranked):
        ivan = next(row for row in ranked if row.full_name == "Ivan Petrov")
        body = client.get(f"/candidates/{ivan.id}").json()

        assert body["full_name"] == "Ivan Petrov"
        assert "protected_attributes" not in body
        assert session.get(Candidate, ivan.id).protected_attributes == {"gender": "male"}

    def test_unknown_candidate_is_404(self, client):
        assert client.get("/candidates/00000000-0000-0000-0000-000000000000").status_code == 404


class TestNoAutomaticRejection:
    def test_ranking_creates_no_decision_rows(self, client, session, role, ranked):
        from sqlalchemy import select

        # Класирането само подрежда. Статус се ражда единствено от човек.
        assert session.scalars(select(Decision)).all() == []

    def test_every_row_starts_pending_even_below_the_minimum(self, client, role, ranked):
        body = rankings(client, role.id).json()
        assert {row["outcome"] for row in body["rows"]} == {"pending"}

    def test_reranking_does_not_touch_an_existing_decision(
        self, client, session, role, ruleset, ranked
    ):
        target = ranking_id_of(client, role.id, "Georgi Georgiev")
        client.put(
            f"/rankings/{target}/decision",
            json={"outcome": "on_hold", "decided_by": "recruiter", "rationale": "чака интервю"},
        )

        assert client.post(f"/roles/{role.id}/rank").status_code == 200

        row = next(
            item
            for item in rankings(client, role.id).json()["rows"]
            if item["full_name"] == "Georgi Georgiev"
        )
        assert row["outcome"] == "on_hold"
        assert row["decided_by"] == "recruiter"


class TestRulesetVersions:
    def test_new_version_gives_a_separate_leaderboard(self, client, session, role, ranked):
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
        assert client.post(f"/roles/{role.id}/rank").status_code == 200

        body = rankings(client, role.id).json()
        # По подразбиране се показва по-скоро активираната версия.
        assert body["ruleset"]["version"] == "2026.09.1"
        assert [item["version"] for item in body["available_rulesets"]] == [
            "2026.09.1",
            "2026.08.1",
        ]

        old = rankings(client, role.id, ruleset_version="2026.08.1").json()
        assert old["ruleset"]["version"] == "2026.08.1"
        assert old["total_unfiltered"] == 3

    def test_unmasked_rows_never_reach_the_recruiter(self, client, session, role, ruleset, ranked):
        """Bias-одитът пише UNMASKED редове; изгледът за рекрутер не ги вижда."""
        ivan = next(row for row in ranked if row.full_name == "Ivan Petrov")
        session.add(
            Ranking(
                candidate_id=ivan.id,
                role_id=role.id,
                ruleset_id=ruleset.id,
                mode=RankingMode.UNMASKED,
                score=99,
                explanation={"engine": "rule_based", "factors": []},
            )
        )
        session.commit()

        body = rankings(client, role.id).json()
        assert body["total_unfiltered"] == 3
        assert all(row["score"] != 99.0 for row in body["rows"])
