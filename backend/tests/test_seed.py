"""Seed наборът: идемпотентност, годност за скоринг и одитна следа."""

from sqlalchemy import select

from app.models import AuditAction, AuditLog, Candidate, Role, Ruleset, RulesetStatus
from app.scoring import RoleRequirements, ScoringRules
from app.seed import SYNTHETIC_CANDIDATES, SYNTHETIC_ROLES, seed


class TestFirstRun:
    def test_creates_the_whole_set(self, session):
        report = seed(session)

        assert len(session.scalars(select(Candidate)).all()) == len(SYNTHETIC_CANDIDATES)
        assert len(session.scalars(select(Role)).all()) == len(SYNTHETIC_ROLES)
        assert report.created["ruleset"] == 1

    def test_the_seeded_ruleset_is_active(self, session):
        seed(session)

        ruleset = session.scalars(select(Ruleset)).one()
        assert ruleset.status is RulesetStatus.ACTIVE
        assert ruleset.activated_at is not None

    def test_profiles_come_from_the_real_parser(self, session):
        seed(session)

        maria = session.scalars(
            select(Candidate).where(Candidate.external_ref == "cand-001")
        ).one()
        assert maria.full_name == "Мария Иванова"
        assert maria.email == "maria.ivanova@example.com"
        assert "fastapi" in maria.profile["skills"]
        assert maria.profile["experience"][0]["organization"] == "Telerik Academy"
        assert maria.profile["education"][0]["degree"] == "магистър"

    def test_protected_attributes_are_set_only_here(self, session):
        seed(session)

        candidates = session.scalars(select(Candidate)).all()
        assert all(candidate.protected_attributes for candidate in candidates)
        # Нищо защитено не се е промъкнало в профила, който скорингът вижда.
        assert all("gender" not in candidate.profile for candidate in candidates)

    def test_writes_an_audit_trail(self, session):
        seed(session)

        actions = [entry.action for entry in session.scalars(select(AuditLog)).all()]
        assert actions.count(AuditAction.CV_INGESTED) == len(SYNTHETIC_CANDIDATES)
        assert actions.count(AuditAction.RULESET_ACTIVATED) == 1
        assert {entry.actor for entry in session.scalars(select(AuditLog)).all()} == {"seed"}


class TestIdempotence:
    def test_second_run_does_not_duplicate(self, session):
        seed(session)
        report = seed(session)

        assert len(session.scalars(select(Candidate)).all()) == len(SYNTHETIC_CANDIDATES)
        assert len(session.scalars(select(Role)).all()) == len(SYNTHETIC_ROLES)
        assert len(session.scalars(select(Ruleset)).all()) == 1
        assert report.created == {}
        assert report.skipped["candidate"] == len(SYNTHETIC_CANDIDATES)

    def test_second_run_adds_no_audit_noise(self, session):
        seed(session)
        before = len(session.scalars(select(AuditLog)).all())
        seed(session)

        assert len(session.scalars(select(AuditLog)).all()) == before

    def test_edited_role_is_restored(self, session):
        seed(session)
        role = session.scalars(select(Role).where(Role.external_ref == "role-backend-01")).one()
        role.requirements = {"required_skills": ["cobol"]}
        session.commit()

        report = seed(session)

        assert report.updated["role"] == 1
        assert "cobol" not in str(role.requirements)

    def test_existing_ruleset_version_is_never_rewritten(self, session):
        seed(session)
        ruleset = session.scalars(select(Ruleset)).one()
        ruleset.notes = "пипнато на ръка"
        session.commit()

        report = seed(session)

        assert report.skipped["ruleset"] == 1
        assert ruleset.notes == "пипнато на ръка"


class TestSeededDataIsUsable:
    def test_every_role_has_requirements_the_scorer_accepts(self, session):
        seed(session)

        for role in session.scalars(select(Role)):
            requirements = RoleRequirements.from_json(role.requirements)
            assert not requirements.is_empty

    def test_the_ruleset_definition_parses(self, session):
        seed(session)

        ruleset = session.scalars(select(Ruleset)).one()
        rules = ScoringRules.from_definition(ruleset.definition, version=ruleset.version)
        assert rules.weights["required_skills"] == 0.50

    def test_ranking_the_seeded_role_produces_a_spread(self, client, session):
        """Seed наборът трябва да разграничава кандидати, не да ги изравнява."""
        seed(session)
        role = session.scalars(select(Role).where(Role.external_ref == "role-backend-01")).one()

        response = client.post(f"/roles/{role.id}/rank")
        assert response.status_code == 200, response.text

        ranked = response.json()["ranked"]
        assert len(ranked) == len(SYNTHETIC_CANDIDATES)
        assert ranked[0]["score"] > ranked[-1]["score"]
        assert ranked[0]["meets_minimum"] is True
        assert ranked[-1]["meets_minimum"] is False

    def test_devops_role_ranks_a_different_candidate_first(self, client, session):
        """Различната роля вдига различен кандидат — иначе скорингът е декор."""
        seed(session)
        backend = session.scalars(
            select(Role).where(Role.external_ref == "role-backend-01")
        ).one()
        devops = session.scalars(select(Role).where(Role.external_ref == "role-devops-01")).one()

        top_backend = client.post(f"/roles/{backend.id}/rank").json()["ranked"][0]
        top_devops = client.post(f"/roles/{devops.id}/rank").json()["ranked"][0]

        assert top_backend["full_name"] != top_devops["full_name"]
