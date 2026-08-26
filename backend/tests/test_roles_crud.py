"""CRUD за роли: създаване, преглед, обновяване и кога триенето се отказва."""

from uuid import UUID

from sqlalchemy import select

from app.models import AuditAction, AuditLog, Candidate, Role, RoleStatus

VALID_REQUIREMENTS = {
    "required_skills": [{"name": "python", "weight": 3}, "postgresql"],
    "preferred_skills": ["docker"],
    "min_years_experience": 4,
    "min_degree": "bachelor",
}


def create(client, **overrides):
    body = {"title": "Backend Developer", "requirements": VALID_REQUIREMENTS} | overrides
    return client.post("/roles", json=body)


class TestCreate:
    def test_creates_a_role_as_draft_by_default(self, client):
        response = create(client)
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["title"] == "Backend Developer"
        assert body["status"] == "draft"
        assert body["requirements"]["min_years_experience"] == 4
        assert body["id"]

    def test_status_can_be_set_on_creation(self, client):
        assert create(client, status="open").json()["status"] == "open"

    def test_writes_an_audit_entry(self, client, session):
        create(client)

        entry = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.ROLE_CREATED)
        ).one()
        assert entry.entity_type == "role"
        assert entry.payload_in["title"] == "Backend Developer"

    def test_duplicate_external_ref_is_a_409(self, client):
        create(client, external_ref="role-backend-01")
        assert create(client, external_ref="role-backend-01").status_code == 409

    def test_role_without_requirements_is_allowed(self, client):
        """Чернова без изисквания е нормална стъпка — класирането ще е нула."""
        response = client.post("/roles", json={"title": "Още неясна роля"})
        assert response.status_code == 201
        assert response.json()["requirements"] == {}


class TestCreateValidation:
    def test_empty_title_is_rejected(self, client):
        assert create(client, title="").status_code == 422

    def test_unknown_degree_is_rejected_at_the_door(self, client):
        response = create(client, requirements={"min_degree": "бакалавърче"})
        assert response.status_code == 422
        assert "min_degree" in response.text

    def test_negative_years_are_rejected(self, client):
        assert create(client, requirements={"min_years_experience": -3}).status_code == 422

    def test_malformed_skills_are_rejected(self, client):
        assert create(client, requirements={"required_skills": "python"}).status_code == 422

    def test_nothing_is_persisted_when_validation_fails(self, client, session):
        create(client, requirements={"min_years_experience": -3})
        assert session.scalars(select(Role)).all() == []


class TestRead:
    def test_lists_roles(self, client):
        create(client, title="Backend Developer")
        create(client, title="DevOps Engineer")

        titles = [row["title"] for row in client.get("/roles").json()]
        assert set(titles) == {"Backend Developer", "DevOps Engineer"}

    def test_filters_by_status(self, client):
        create(client, title="Отворена", status="open")
        create(client, title="Чернова")

        rows = client.get("/roles", params={"status": "open"}).json()
        assert [row["title"] for row in rows] == ["Отворена"]

    def test_pagination_limits_the_page(self, client):
        for index in range(3):
            create(client, title=f"Роля {index}")

        assert len(client.get("/roles", params={"limit": 2}).json()) == 2
        assert len(client.get("/roles", params={"limit": 2, "offset": 2}).json()) == 1

    def test_get_by_id(self, client):
        role_id = create(client).json()["id"]
        assert client.get(f"/roles/{role_id}").json()["id"] == role_id

    def test_unknown_id_is_a_404(self, client):
        assert client.get("/roles/00000000-0000-0000-0000-000000000000").status_code == 404


class TestUpdate:
    def test_patches_only_what_is_sent(self, client):
        role_id = create(client, description="първоначално").json()["id"]

        body = client.patch(f"/roles/{role_id}", json={"status": "open"}).json()
        assert body["status"] == "open"
        assert body["description"] == "първоначално"
        assert body["title"] == "Backend Developer"

    def test_requirements_are_validated_on_update(self, client):
        role_id = create(client).json()["id"]
        response = client.patch(f"/roles/{role_id}", json={"requirements": {"languages": [42]}})
        assert response.status_code == 422

    def test_empty_patch_changes_nothing(self, client, session):
        role_id = create(client).json()["id"]
        assert client.patch(f"/roles/{role_id}", json={}).status_code == 200
        assert (
            session.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.ROLE_UPDATED)
            ).all()
            == []
        )

    def test_writes_an_audit_entry(self, client, session):
        role_id = create(client).json()["id"]
        client.patch(f"/roles/{role_id}", json={"title": "Ново име"})

        entry = session.scalars(
            select(AuditLog).where(AuditLog.action == AuditAction.ROLE_UPDATED)
        ).one()
        assert entry.payload_in == {"title": "Ново име"}

    def test_unknown_id_is_a_404(self, client):
        response = client.patch(
            "/roles/00000000-0000-0000-0000-000000000000", json={"title": "X"}
        )
        assert response.status_code == 404


class TestDelete:
    def test_deletes_a_role_without_rankings(self, client, session):
        role_id = create(client).json()["id"]

        assert client.delete(f"/roles/{role_id}").status_code == 204
        assert session.scalars(select(Role)).all() == []

    def test_role_with_rankings_is_not_deleted(self, client, session, seeded_ruleset):
        role_id = create(client, status="open").json()["id"]
        session.add(
            Candidate(full_name="Ivan Petrov", profile={"skills": ["python"]}, protected_attributes={})
        )
        session.commit()
        assert client.post(f"/roles/{role_id}/rank").status_code == 200

        response = client.delete(f"/roles/{role_id}")
        assert response.status_code == 409
        assert "closed" in response.json()["detail"]
        assert session.get(Role, UUID(role_id)) is not None

    def test_closing_is_the_way_to_retire_a_role(self, client):
        role_id = create(client, status="open").json()["id"]
        body = client.patch(f"/roles/{role_id}", json={"status": "closed"}).json()
        assert body["status"] == RoleStatus.CLOSED.value

    def test_unknown_id_is_a_404(self, client):
        assert client.delete("/roles/00000000-0000-0000-0000-000000000000").status_code == 404
