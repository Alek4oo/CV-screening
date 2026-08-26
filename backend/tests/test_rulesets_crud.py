"""CRUD за версии правила — и границите, които неизменимостта поставя."""

from sqlalchemy import select

from app.models import AuditAction, AuditLog, Ruleset, RulesetStatus

WEIGHTS = {
    "required_skills": 0.6,
    "preferred_skills": 0.1,
    "experience": 0.2,
    "education": 0.1,
}


def create(client, version="2026.08.1", **overrides):
    body = {
        "version": version,
        "name": "Базови правила",
        "definition": {"weights": WEIGHTS},
    } | overrides
    return client.post("/rulesets", json=body)


def activate(client, ruleset_id):
    return client.post(f"/rulesets/{ruleset_id}/activate")


class TestCreate:
    def test_new_version_is_born_as_a_draft(self, client):
        response = create(client)
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["status"] == "draft"
        assert body["activated_at"] is None
        assert body["definition"]["weights"]["required_skills"] == 0.6

    def test_duplicate_version_is_a_409(self, client):
        create(client)
        response = create(client)
        assert response.status_code == 409
        assert "неизменими" in response.json()["detail"]

    def test_writes_an_audit_entry(self, client, session):
        create(client)

        entry = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.RULESET_CREATED)
        ).one()
        assert entry.entity_type == "ruleset"
        assert entry.ruleset_id is not None

    def test_empty_definition_means_default_weights(self, client):
        assert create(client, definition={}).status_code == 201


class TestCreateValidation:
    def test_unknown_factor_is_rejected(self, client):
        response = create(client, definition={"weights": {"charisma": 1}})
        assert response.status_code == 422
        assert "charisma" in response.text

    def test_negative_weight_is_rejected(self, client):
        assert create(client, definition={"weights": {"experience": -1}}).status_code == 422

    def test_all_zero_weights_are_rejected(self, client):
        response = create(client, definition={"weights": {"experience": 0}})
        assert response.status_code == 422

    def test_nothing_is_persisted_when_validation_fails(self, client, session):
        create(client, definition={"weights": {"charisma": 1}})
        assert session.scalars(select(Ruleset)).all() == []


class TestActivation:
    def test_activating_puts_the_version_in_force(self, client):
        ruleset_id = create(client).json()["id"]

        body = activate(client, ruleset_id).json()
        assert body["status"] == "active"
        assert body["activated_at"] is not None

    def test_activating_retires_the_previous_version(self, client, session):
        first = create(client, version="2026.08.1").json()["id"]
        activate(client, first)
        second = create(client, version="2026.09.1").json()["id"]

        activate(client, second)

        assert client.get(f"/rulesets/{first}").json()["status"] == "retired"
        assert client.get("/rulesets/active").json()["id"] == second

    def test_activation_is_audited_with_the_retired_version(self, client, session):
        first = create(client, version="2026.08.1").json()["id"]
        activate(client, first)
        second = create(client, version="2026.09.1").json()["id"]
        activate(client, second)

        activations = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.RULESET_ACTIVATED)
        ).all()
        assert len(activations) == 2
        assert activations[-1].payload_out["retired"] == ["2026.08.1"]

        retirements = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.RULESET_RETIRED)
        ).all()
        assert retirements[0].payload_in["replaced_by"] == "2026.09.1"

    def test_activating_twice_is_idempotent(self, client, session):
        ruleset_id = create(client).json()["id"]
        activate(client, ruleset_id)
        first_time = client.get(f"/rulesets/{ruleset_id}").json()["activated_at"]

        assert activate(client, ruleset_id).status_code == 200
        assert client.get(f"/rulesets/{ruleset_id}").json()["activated_at"] == first_time
        # Без промяна няма и одитен запис.
        assert (
            len(
                session.scalars(
                    select(AuditLog).where(AuditLog.action == AuditAction.RULESET_ACTIVATED)
                ).all()
            )
            == 1
        )

    def test_a_retired_version_can_be_brought_back(self, client):
        first = create(client, version="2026.08.1").json()["id"]
        activate(client, first)
        second = create(client, version="2026.09.1").json()["id"]
        activate(client, second)

        assert activate(client, first).json()["status"] == "active"
        assert client.get(f"/rulesets/{second}").json()["status"] == "retired"

    def test_unknown_id_is_a_404(self, client):
        assert activate(client, "00000000-0000-0000-0000-000000000000").status_code == 404


class TestImmutability:
    def test_draft_can_be_edited(self, client):
        ruleset_id = create(client).json()["id"]

        body = client.patch(
            f"/rulesets/{ruleset_id}", json={"notes": "уточнено", "definition": {"weights": {"experience": 1}}}
        ).json()
        assert body["notes"] == "уточнено"
        assert body["definition"]["weights"] == {"experience": 1}

    def test_active_version_cannot_be_edited(self, client):
        ruleset_id = create(client).json()["id"]
        activate(client, ruleset_id)

        response = client.patch(f"/rulesets/{ruleset_id}", json={"notes": "късна редакция"})
        assert response.status_code == 409
        assert "нова версия" in response.json()["detail"]

    def test_active_version_cannot_be_deleted(self, client, session):
        ruleset_id = create(client).json()["id"]
        activate(client, ruleset_id)

        assert client.delete(f"/rulesets/{ruleset_id}").status_code == 409
        assert session.scalars(select(Ruleset)).all()

    def test_retired_version_cannot_be_edited(self, client):
        first = create(client, version="2026.08.1").json()["id"]
        activate(client, first)
        activate(client, create(client, version="2026.09.1").json()["id"])

        assert client.patch(f"/rulesets/{first}", json={"notes": "нов текст"}).status_code == 409

    def test_draft_can_be_deleted(self, client, session):
        ruleset_id = create(client).json()["id"]

        assert client.delete(f"/rulesets/{ruleset_id}").status_code == 204
        assert session.scalars(select(Ruleset)).all() == []

    def test_edit_is_validated_like_creation(self, client):
        ruleset_id = create(client).json()["id"]
        response = client.patch(f"/rulesets/{ruleset_id}", json={"definition": {"weights": {"x": 1}}})
        assert response.status_code == 422


class TestRead:
    def test_lists_and_filters_by_status(self, client):
        draft = create(client, version="2026.08.1").json()["id"]
        active = create(client, version="2026.09.1").json()["id"]
        activate(client, active)

        drafts = client.get("/rulesets", params={"status": "draft"}).json()
        assert [row["id"] for row in drafts] == [draft]
        assert len(client.get("/rulesets").json()) == 2

    def test_active_endpoint_without_an_active_version_is_a_404(self, client):
        create(client)
        assert client.get("/rulesets/active").status_code == 404

    def test_unknown_id_is_a_404(self, client):
        assert client.get("/rulesets/00000000-0000-0000-0000-000000000000").status_code == 404


class TestEndToEndWithRanking:
    def test_created_role_and_ruleset_are_enough_to_rank(self, client, session):
        """Пълният път през API-то, без нито един ред, вкаран отвън."""
        from app.models import Candidate

        session.add(
            Candidate(
                full_name="Ivan Petrov",
                profile={"skills": ["python", "postgresql"]},
                protected_attributes={},
            )
        )
        session.commit()

        ruleset_id = create(client).json()["id"]
        activate(client, ruleset_id)
        role_id = client.post(
            "/roles",
            json={
                "title": "Backend Developer",
                "status": "open",
                "requirements": {"required_skills": ["python", "postgresql"]},
            },
        ).json()["id"]

        response = client.post(f"/roles/{role_id}/rank")
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["ruleset_version"] == "2026.08.1"
        assert body["ranked"][0]["score"] == 100.0

    def test_reactivating_an_older_version_changes_the_next_ranking(self, client, session):
        from app.models import Candidate

        session.add(
            Candidate(
                full_name="Ivan Petrov",
                profile={
                    "skills": ["python"],
                    "experience": [{"start": "2010", "end": "2026"}],
                },
                protected_attributes={},
            )
        )
        session.commit()

        skills_only = create(
            client, version="2026.08.1", definition={"weights": {"required_skills": 1}}
        ).json()["id"]
        experience_only = create(
            client, version="2026.09.1", definition={"weights": {"experience": 1}}
        ).json()["id"]

        role_id = client.post(
            "/roles",
            json={
                "title": "Backend Developer",
                "requirements": {
                    "required_skills": ["python", "kafka"],
                    "min_years_experience": 5,
                },
            },
        ).json()["id"]

        activate(client, skills_only)
        by_skills = client.post(f"/roles/{role_id}/rank").json()["ranked"][0]["score"]
        activate(client, experience_only)
        by_experience = client.post(f"/roles/{role_id}/rank").json()["ranked"][0]["score"]

        assert by_skills == 50.0
        assert by_experience == 100.0
