"""Версии правила: създаване, преглед, активиране.

Неизменимостта на активираните правила е носещата стена тук. Решение, взето с
версия 2026.08.1, трябва да може да бъде обяснено с точно тези тежести — затова:

  * Нова версия се ражда като чернова (DRAFT).
  * Черновата се редактира свободно — с нея още нищо не е решено.
  * Активираната версия не се редактира и не се трие. Промяна значи нова версия.
  * Активирането ретайрва предишната активна, за да е еднозначно коя е в сила.

Разделението на грешките:
  422 — тежестите в заявката са неизползваеми (валидира се в схемата)
  409 — версията вече съществува, или се пипа нещо, което вече не е чернова
  404 — няма такава версия
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import RulesetCreate, RulesetRead, RulesetUpdate
from app.core.db import get_session
from app.models import AuditAction, AuditLog, Ruleset, RulesetStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rulesets", tags=["rulesets"])

MAX_PAGE_SIZE = 200


@router.post(
    "",
    response_model=RulesetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Създава нова версия правила като чернова",
)
def create_ruleset(payload: RulesetCreate, session: Session = Depends(get_session)) -> Ruleset:
    if _by_version(session, payload.version) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Версия {payload.version!r} вече съществува. Правилата са неизменими.",
        )

    ruleset = Ruleset(**payload.model_dump(), status=RulesetStatus.DRAFT)
    session.add(ruleset)
    session.flush()

    session.add(
        AuditLog(
            actor="api",
            action=AuditAction.RULESET_CREATED,
            entity_type="ruleset",
            entity_id=ruleset.id,
            ruleset_id=ruleset.id,
            payload_in=payload.model_dump(mode="json"),
            payload_out={"id": str(ruleset.id), "status": ruleset.status.value},
        )
    )
    session.commit()
    session.refresh(ruleset)
    return ruleset


@router.get("", response_model=list[RulesetRead], summary="Изброява версиите правила")
def list_rulesets(
    session: Session = Depends(get_session),
    ruleset_status: RulesetStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> list[Ruleset]:
    statement = select(Ruleset).order_by(Ruleset.created_at.desc(), Ruleset.version)
    if ruleset_status is not None:
        statement = statement.where(Ruleset.status == ruleset_status)
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get("/active", response_model=RulesetRead, summary="Версията, която е в сила")
def get_active_ruleset(session: Session = Depends(get_session)) -> Ruleset:
    ruleset = session.scalars(
        select(Ruleset)
        .where(Ruleset.status == RulesetStatus.ACTIVE)
        .order_by(Ruleset.activated_at.desc().nulls_last())
    ).first()
    if ruleset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Няма активна версия правила.",
        )
    return ruleset


@router.get("/{ruleset_id}", response_model=RulesetRead, summary="Връща една версия")
def get_ruleset(ruleset_id: UUID, session: Session = Depends(get_session)) -> Ruleset:
    return _require_ruleset(session, ruleset_id)


@router.patch(
    "/{ruleset_id}",
    response_model=RulesetRead,
    summary="Редактира чернова (активирана версия не се пипа)",
)
def update_ruleset(
    ruleset_id: UUID, payload: RulesetUpdate, session: Session = Depends(get_session)
) -> Ruleset:
    ruleset = _require_ruleset(session, ruleset_id)
    _require_draft(ruleset, "редактира")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(ruleset, field, value)

    session.commit()
    session.refresh(ruleset)
    return ruleset


@router.post(
    "/{ruleset_id}/activate",
    response_model=RulesetRead,
    summary="Активира версия и ретайрва предишната",
)
def activate_ruleset(ruleset_id: UUID, session: Session = Depends(get_session)) -> Ruleset:
    ruleset = _require_ruleset(session, ruleset_id)
    if ruleset.status is RulesetStatus.ACTIVE:
        # Идемпотентно: повторното активиране не е промяна и не влиза в одита.
        return ruleset

    previous = list(
        session.scalars(select(Ruleset).where(Ruleset.status == RulesetStatus.ACTIVE))
    )
    for old in previous:
        old.status = RulesetStatus.RETIRED
        session.add(
            AuditLog(
                actor="api",
                action=AuditAction.RULESET_RETIRED,
                entity_type="ruleset",
                entity_id=old.id,
                ruleset_id=old.id,
                payload_in={"replaced_by": ruleset.version},
                payload_out={"status": RulesetStatus.RETIRED.value},
            )
        )

    ruleset.status = RulesetStatus.ACTIVE
    ruleset.activated_at = datetime.now(timezone.utc)

    session.add(
        AuditLog(
            actor="api",
            action=AuditAction.RULESET_ACTIVATED,
            entity_type="ruleset",
            entity_id=ruleset.id,
            ruleset_id=ruleset.id,
            payload_in={"version": ruleset.version},
            payload_out={
                "weights": ruleset.definition.get("weights"),
                "retired": [old.version for old in previous],
            },
        )
    )
    session.commit()
    session.refresh(ruleset)
    logger.info("Версия правила %s е в сила", ruleset.version)
    return ruleset


@router.delete(
    "/{ruleset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Трие чернова (активирана версия не се трие)",
)
def delete_ruleset(ruleset_id: UUID, session: Session = Depends(get_session)) -> None:
    ruleset = _require_ruleset(session, ruleset_id)
    _require_draft(ruleset, "трие")

    session.delete(ruleset)
    session.commit()


def _require_ruleset(session: Session, ruleset_id: UUID) -> Ruleset:
    ruleset = session.get(Ruleset, ruleset_id)
    if ruleset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Няма версия правила с id {ruleset_id}.",
        )
    return ruleset


def _require_draft(ruleset: Ruleset, verb: str) -> None:
    if ruleset.status is not RulesetStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Версия {ruleset.version} е {ruleset.status.value} и не се {verb}. "
                "Направете нова версия — правилата зад взетите решения не се променят."
            ),
        )


def _by_version(session: Session, version: str) -> Ruleset | None:
    return session.scalars(select(Ruleset).where(Ruleset.version == version)).one_or_none()
