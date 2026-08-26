"""Синтетични данни за разработка и демо: правила, роли, кандидати.

    python -m app.seed

Всички хора тук са измислени. Нито едно име, CV или защитен признак не е на
реален човек — PRD-то забранява реални лични данни в този проект.

Три решения си струват обяснение:

  * Кандидатите се раждат от суров CV текст през `parse_profile`, а не от готови
    JSON профили. Така seed наборът минава през същия код като продукцията и
    чупенето на парсера си личи веднага.
  * Идемпотентността е на `external_ref` — повторното пускане обновява, вместо да
    дублира. Затова колоната съществува.
  * Ruleset редовете не се пипат, ако версията вече е там. Правилата са
    неизменими по замисъл: промяна значи нова версия, не UPDATE на стара.

Защитените атрибути се попълват само тук. Те не идват и не бива да идват от
CV-то — единственият им консуматор е bias-одитът.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base, SessionLocal, engine
from app.models import (
    AuditAction,
    AuditLog,
    Candidate,
    Role,
    RoleStatus,
    Ruleset,
    RulesetStatus,
)
from app.parsing import parse_profile

logger = logging.getLogger(__name__)

SEED_ACTOR = "seed"

SYNTHETIC_RULESET: dict[str, Any] = {
    "version": "2026.08.1",
    "name": "Базови правила за инженерни роли",
    "notes": "Уменията носят 65 точки, опитът 25, образованието 10.",
    "definition": {
        "weights": {
            "required_skills": 0.50,
            "preferred_skills": 0.15,
            "experience": 0.25,
            "education": 0.10,
            "languages": 0.00,
        }
    },
}

SYNTHETIC_ROLES: tuple[dict[str, Any], ...] = (
    {
        "external_ref": "role-backend-01",
        "title": "Backend Developer (Python)",
        "description": "Python/FastAPI екип, услуги върху PostgreSQL.",
        "requirements": {
            "required_skills": [
                {"name": "python", "weight": 3},
                {"name": "postgresql", "weight": 2},
                {"name": "fastapi", "weight": 1},
            ],
            "preferred_skills": ["docker", "ci/cd", "pytest"],
            "min_years_experience": 4,
            "min_degree": "bachelor",
        },
        "status": RoleStatus.OPEN,
    },
    {
        "external_ref": "role-devops-01",
        "title": "DevOps Engineer",
        "description": "Контейнери, оркестрация и инфраструктура като код.",
        "requirements": {
            "required_skills": [
                {"name": "kubernetes", "weight": 3},
                {"name": "docker", "weight": 2},
                {"name": "linux", "weight": 2},
                {"name": "terraform", "weight": 1},
            ],
            "preferred_skills": ["aws", "ci/cd", "python"],
            "min_years_experience": 3,
        },
        "status": RoleStatus.OPEN,
    },
)

# (external_ref, суров CV текст, защитени атрибути) — синтетични, до един.
SYNTHETIC_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "external_ref": "cand-001",
        "filename": "maria_ivanova.pdf",
        "protected_attributes": {"gender": "female", "age_band": "35-44", "origin": "BG"},
        "cv_text": """Мария Иванова
maria.ivanova@example.com
+359 88 100 1001

Умения
Python, FastAPI, PostgreSQL, Docker, CI/CD, pytest

Професионален опит
2016 - 2021 Backend Developer, Telerik Academy
Изгражда REST услуги и CI процеси.
2021 - настоящем Senior Backend Engineer, Sirma Solutions

Образование
2012 - 2016 Магистър, Софийски университет

Езици
Български, Английски
""",
    },
    {
        "external_ref": "cand-002",
        "filename": "ivan_petrov.pdf",
        "protected_attributes": {"gender": "male", "age_band": "25-34", "origin": "BG"},
        "cv_text": """Ivan Petrov
ivan.petrov@example.com
+359 88 100 1002

Skills
Python, PostgreSQL, FastAPI, Git, REST

Experience
2019 - 2023 Backend Developer, Acme Corp
Built REST services and CI pipelines.
2023 - present Senior Backend Engineer, Globex

Education
2015 - 2019 Bachelor, Sofia University

Languages
Bulgarian, English
""",
    },
    {
        "external_ref": "cand-003",
        "filename": "georgi_georgiev.pdf",
        "protected_attributes": {"gender": "male", "age_band": "45-54", "origin": "BG"},
        "cv_text": """Георги Георгиев
georgi.georgiev@example.com
+359 88 100 1003

Умения
Java, Spring, MySQL, Linux

Професионален опит
2008 - 2019 Java Developer, Sirma Group
2019 - настоящем Tech Lead, Bulpros

Образование
2004 - 2008 Бакалавър, Технически университет

Езици
Български, Английски, Немски
""",
    },
    {
        "external_ref": "cand-004",
        "filename": "elena_todorova.pdf",
        "protected_attributes": {"gender": "female", "age_band": "25-34", "origin": "BG"},
        "cv_text": """Елена Тодорова
elena.todorova@example.com
+359 88 100 1004

Умения
Python, Django, SQL, Docker, Git

Професионален опит
2022 - настоящем Junior Backend Developer, Paysafe

Образование
2018 - 2022 Бакалавър, Пловдивски университет

Езици
Български, Английски
""",
    },
    {
        "external_ref": "cand-005",
        "filename": "nikolay_stoyanov.pdf",
        "protected_attributes": {"gender": "male", "age_band": "18-24", "origin": "BG"},
        "cv_text": """Николай Стоянов
nikolay.stoyanov@example.com
+359 88 100 1005

Умения
PHP, MySQL, JavaScript

Професионален опит
2023 - настоящем Web Developer, местна агенция

Образование
2019 - 2023 Средно образование, Професионална гимназия по електроника

Езици
Български
""",
    },
    {
        "external_ref": "cand-006",
        "filename": "petya_hristova.pdf",
        "protected_attributes": {"gender": "female", "age_band": "45-54", "origin": "EU"},
        "cv_text": """Петя Христова
petya.hristova@example.com
+359 88 100 1006

Умения
Kubernetes, Docker, Linux, Terraform, AWS, Python, CI/CD

Професионален опит
2012 - 2018 System Administrator, Telecom BG
2018 - настоящем Platform Engineer, Cloud Partner

Образование
2006 - 2012 Доктор, Технически университет

Езици
Български, Английски, Френски
""",
    },
)


@dataclass
class SeedReport:
    """Какво е направил seed-ът — печата се и се проверява в тестовете."""

    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def note(self, bucket: dict[str, int], entity: str) -> None:
        bucket[entity] = bucket.get(entity, 0) + 1

    def lines(self) -> list[str]:
        return [
            f"{label}: {', '.join(f'{name} x{count}' for name, count in sorted(bucket.items()))}"
            for label, bucket in (
                ("създадени", self.created),
                ("обновени", self.updated),
                ("без промяна", self.skipped),
            )
            if bucket
        ] or ["няма промени"]


def seed(session: Session) -> SeedReport:
    """Пълни базата със синтетичния набор. Повторното пускане е безопасно."""
    report = SeedReport()
    _seed_ruleset(session, report)
    _seed_roles(session, report)
    _seed_candidates(session, report)
    session.commit()
    return report


def _seed_ruleset(session: Session, report: SeedReport) -> Ruleset:
    version = SYNTHETIC_RULESET["version"]
    ruleset = session.scalars(select(Ruleset).where(Ruleset.version == version)).one_or_none()
    if ruleset is not None:
        # Неизменими по замисъл — промяна значи нова версия, не UPDATE на стара.
        report.note(report.skipped, "ruleset")
        return ruleset

    ruleset = Ruleset(
        version=version,
        name=SYNTHETIC_RULESET["name"],
        notes=SYNTHETIC_RULESET["notes"],
        definition=SYNTHETIC_RULESET["definition"],
        status=RulesetStatus.ACTIVE,
        activated_at=datetime.now(timezone.utc),
    )
    session.add(ruleset)
    session.flush()

    session.add(
        AuditLog(
            actor=SEED_ACTOR,
            action=AuditAction.RULESET_ACTIVATED,
            entity_type="ruleset",
            entity_id=ruleset.id,
            ruleset_id=ruleset.id,
            payload_in={"version": version},
            payload_out={"weights": SYNTHETIC_RULESET["definition"]["weights"]},
        )
    )
    report.note(report.created, "ruleset")
    return ruleset


def _seed_roles(session: Session, report: SeedReport) -> None:
    for spec in SYNTHETIC_ROLES:
        role = session.scalars(
            select(Role).where(Role.external_ref == spec["external_ref"])
        ).one_or_none()

        if role is None:
            session.add(
                Role(
                    external_ref=spec["external_ref"],
                    title=spec["title"],
                    description=spec["description"],
                    requirements=spec["requirements"],
                    status=spec["status"],
                )
            )
            report.note(report.created, "role")
            continue

        if role.requirements == spec["requirements"] and role.title == spec["title"]:
            report.note(report.skipped, "role")
            continue

        role.title = spec["title"]
        role.description = spec["description"]
        role.requirements = spec["requirements"]
        report.note(report.updated, "role")


def _seed_candidates(session: Session, report: SeedReport) -> None:
    for spec in SYNTHETIC_CANDIDATES:
        # Парсваме винаги: така сменен парсер си личи по разликата в профила.
        parsed = parse_profile(spec["cv_text"])
        candidate = session.scalars(
            select(Candidate).where(Candidate.external_ref == spec["external_ref"])
        ).one_or_none()

        if candidate is not None:
            if candidate.profile == parsed.to_dict():
                report.note(report.skipped, "candidate")
                continue
            candidate.full_name = parsed.full_name or spec["external_ref"]
            candidate.email = parsed.contact.get("email")
            candidate.raw_text = spec["cv_text"]
            candidate.profile = parsed.to_dict()
            report.note(report.updated, "candidate")
            continue

        candidate = Candidate(
            external_ref=spec["external_ref"],
            full_name=parsed.full_name or spec["external_ref"],
            email=parsed.contact.get("email"),
            source_filename=spec["filename"],
            raw_text=spec["cv_text"],
            profile=parsed.to_dict(),
            # Единственото място, където защитени признаци влизат в системата.
            protected_attributes=spec["protected_attributes"],
        )
        session.add(candidate)
        session.flush()

        session.add(
            AuditLog(
                actor=SEED_ACTOR,
                action=AuditAction.CV_INGESTED,
                entity_type="candidate",
                entity_id=candidate.id,
                payload_in={
                    "external_ref": spec["external_ref"],
                    "filename": spec["filename"],
                    "source": "synthetic",
                },
                payload_out={
                    "engine": "seed",
                    "characters": len(spec["cv_text"]),
                    "confidence": parsed.confidence,
                },
            )
        )
        report.note(report.created, "candidate")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Същият компромис като в app.main: без Alembic таблиците се създават тук.
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        report = seed(session)

    for line in report.lines():
        logger.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
