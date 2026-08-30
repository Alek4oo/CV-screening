"""PUT /rankings/{id}/decision — човекът решава, и то с обосновка.

Тестовете тук пазят три обещания от PRD-то: решение без човек и без обосновка не
се записва, статусът се сменя само през този ендпойнт, и всяка смяна оставя ред
в одита с версията правила, с която е сметнат скорът.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import (
    AuditAction,
    AuditLog,
    Candidate,
    Decision,
    DecisionOutcome,
    Role,
    RoleStatus,
    Ruleset,
    RulesetStatus,
)


@pytest.fixture
def ruleset(session) -> Ruleset:
    row = Ruleset(
        version="2026.08.1",
        name="Базови правила",
        definition={"weights": {"required_skills": 1}},
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
        requirements={"required_skills": ["python"]},
        status=RoleStatus.OPEN,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def ranking_id(client, session, ruleset, role) -> str:
    session.add(
        Candidate(
            full_name="Maria Ivanova",
            email="maria@example.com",
            profile={"skills": ["python"]},
            protected_attributes={},
        )
    )
    session.commit()

    ranked = client.post(f"/roles/{role.id}/rank").json()["ranked"]
    return ranked[0]["ranking_id"]


def decide(client, ranking_id, **body):
    return client.put(f"/rankings/{ranking_id}/decision", json=body)


class TestRecording:
    def test_records_outcome_author_and_rationale(self, client, ranking_id):
        response = decide(
            client,
            ranking_id,
            outcome="advanced",
            decided_by="recruiter@sirma.bg",
            rationale="Покрива всички задължителни умения, каним на интервю.",
        )
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["outcome"] == "advanced"
        assert body["decided_by"] == "recruiter@sirma.bg"
        assert body["rationale"].startswith("Покрива")
        assert body["decided_at"] is not None
        assert body["ranking_id"] == ranking_id

    def test_persists_one_decision_per_ranking(self, client, session, ranking_id):
        decide(client, ranking_id, outcome="advanced", decided_by="r", rationale="да")
        decide(client, ranking_id, outcome="rejected", decided_by="r2", rationale="премислих")

        rows = session.scalars(select(Decision)).all()
        assert len(rows) == 1
        assert rows[0].outcome is DecisionOutcome.REJECTED
        assert rows[0].decided_by == "r2"
        assert rows[0].rationale == "премислих"

    def test_decision_points_at_the_ruleset_that_produced_the_score(
        self, client, session, ruleset, ranking_id
    ):
        decide(client, ranking_id, outcome="rejected", decided_by="r", rationale="няма опит")

        decision = session.scalars(select(Decision)).one()
        assert decision.ruleset_id == ruleset.id

    def test_shows_up_in_the_ranking_detail(self, client, ranking_id):
        decide(client, ranking_id, outcome="on_hold", decided_by="r", rationale="чака отговор")

        body = client.get(f"/rankings/{ranking_id}").json()
        assert body["decision"]["outcome"] == "on_hold"
        assert body["decision"]["rationale"] == "чака отговор"

    def test_can_be_returned_to_pending(self, client, ranking_id):
        decide(client, ranking_id, outcome="rejected", decided_by="r", rationale="слаб профил")
        response = decide(
            client, ranking_id, outcome="pending", decided_by="r", rationale="връщам за преглед"
        )

        assert response.status_code == 200
        assert response.json()["outcome"] == "pending"
        # Връщането също е човешко действие — авторът остава записан.
        assert response.json()["decided_by"] == "r"

    def test_unknown_ranking_is_404(self, client):
        response = decide(
            client,
            "00000000-0000-0000-0000-000000000000",
            outcome="advanced",
            decided_by="r",
            rationale="да",
        )
        assert response.status_code == 404


class TestRationaleIsMandatory:
    def test_missing_rationale_is_rejected(self, client, session, ranking_id):
        assert decide(client, ranking_id, outcome="rejected", decided_by="r").status_code == 422
        assert session.scalars(select(Decision)).all() == []

    def test_blank_rationale_is_rejected(self, client, session, ranking_id):
        response = decide(client, ranking_id, outcome="rejected", decided_by="r", rationale="   ")
        assert response.status_code == 422
        assert session.scalars(select(Decision)).all() == []

    def test_missing_author_is_rejected(self, client, session, ranking_id):
        assert decide(client, ranking_id, outcome="rejected", rationale="не пасва").status_code == 422
        assert session.scalars(select(Decision)).all() == []

    def test_unknown_outcome_is_rejected(self, client, ranking_id):
        response = decide(
            client, ranking_id, outcome="auto_rejected", decided_by="bot", rationale="скор"
        )
        assert response.status_code == 422

    def test_whitespace_is_trimmed_not_stored(self, client, session, ranking_id):
        decide(client, ranking_id, outcome="advanced", decided_by="  r  ", rationale="  добър  ")

        decision = session.scalars(select(Decision)).one()
        assert decision.decided_by == "r"
        assert decision.rationale == "добър"


class TestAuditTrail:
    def test_each_decision_writes_an_audit_row(self, client, session, ruleset, ranking_id):
        decide(client, ranking_id, outcome="advanced", decided_by="recruiter", rationale="силен")

        entry = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.DECISION_RECORDED)
        ).one()
        assert entry.actor == "recruiter"
        assert entry.entity_type == "decision"
        assert entry.ruleset_id == ruleset.id
        assert entry.payload_in["outcome"] == "advanced"
        assert entry.payload_in["rationale"] == "силен"
        assert entry.payload_in["ranking_id"] == ranking_id

    def test_a_changed_decision_keeps_the_previous_one_in_the_log(
        self, client, session, ranking_id
    ):
        decide(client, ranking_id, outcome="advanced", decided_by="r", rationale="силен")
        decide(client, ranking_id, outcome="rejected", decided_by="r2", rationale="отпадна")

        entries = session.scalars(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.DECISION_RECORDED)
            .order_by(AuditLog.occurred_at)
        ).all()
        assert len(entries) == 2
        assert entries[0].payload_out["previous_outcome"] == "pending"
        assert entries[1].payload_out["previous_outcome"] == "advanced"

    def test_audit_endpoint_returns_scoring_and_decision_history(self, client, ranking_id):
        decide(client, ranking_id, outcome="advanced", decided_by="r", rationale="силен")

        entries = client.get(f"/rankings/{ranking_id}/audit").json()
        actions = [entry["action"] for entry in entries]
        assert "decision_recorded" in actions
        assert "candidate_scored" in actions

    def test_audit_records_the_score_at_decision_time(self, client, session, ranking_id):
        decide(client, ranking_id, outcome="advanced", decided_by="r", rationale="силен")

        entry = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.DECISION_RECORDED)
        ).one()
        assert entry.payload_out["score"] == 100.0
        assert entry.payload_out["meets_minimum"] is True
