"""Роли: описание на изискванията и класиране на кандидати спрямо тях.

Разделението на грешките следва „чия е вината", както при качването:
  422 — изискванията в заявката са неизползваеми (валидира се в схемата)
  404 — ролята, кандидат или посочената версия правила не съществува
  409 — няма активна версия правила, или дефиницията ѝ е неизползваема
  503 — скоринг адаптерът липсва

Класирането е винаги в режим MASKED: скорерът получава кандидата през протокол,
който изобщо не съдържа `protected_attributes`. UNMASKED редовете се раждат само
от bias-одита и не минават оттук.

Роля с класирания не се трие. Затварянето ѝ е смяна на статуса — решение, взето
по нея, трябва да продължи да сочи към нещо.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    RankedCandidate,
    RankRequest,
    RankResponse,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)
from app.core.db import get_session
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
from app.scoring import (
    InvalidRulesError,
    ScorerFactory,
    ScoreResult,
    ScoringEngineUnavailableError,
    get_scorer_factory,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["roles"])

MODE = RankingMode.MASKED

MAX_PAGE_SIZE = 200


@router.post(
    "",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Създава роля с нейните изисквания",
)
def create_role(payload: RoleCreate, session: Session = Depends(get_session)) -> Role:
    if payload.external_ref and _role_by_ref(session, payload.external_ref) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Вече има роля с external_ref {payload.external_ref!r}.",
        )

    role = Role(**payload.model_dump())
    session.add(role)
    session.flush()

    session.add(
        AuditLog(
            actor="api",
            action=AuditAction.ROLE_CREATED,
            entity_type="role",
            entity_id=role.id,
            payload_in=payload.model_dump(mode="json"),
            payload_out={"id": str(role.id)},
        )
    )
    session.commit()
    session.refresh(role)
    return role


@router.get("", response_model=list[RoleRead], summary="Изброява ролите")
def list_roles(
    session: Session = Depends(get_session),
    role_status: RoleStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> list[Role]:
    statement = select(Role).order_by(Role.created_at.desc(), Role.title)
    if role_status is not None:
        statement = statement.where(Role.status == role_status)
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get("/{role_id}", response_model=RoleRead, summary="Връща една роля")
def get_role(role_id: UUID, session: Session = Depends(get_session)) -> Role:
    return _require_role(session, role_id)


@router.patch("/{role_id}", response_model=RoleRead, summary="Обновява роля частично")
def update_role(
    role_id: UUID, payload: RoleUpdate, session: Session = Depends(get_session)
) -> Role:
    role = _require_role(session, role_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return role

    for field, value in changes.items():
        setattr(role, field, value)

    session.add(
        AuditLog(
            actor="api",
            action=AuditAction.ROLE_UPDATED,
            entity_type="role",
            entity_id=role.id,
            payload_in=payload.model_dump(mode="json", exclude_unset=True),
            payload_out={"id": str(role.id)},
        )
    )
    session.commit()
    session.refresh(role)
    return role


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Трие роля без класирания",
)
def delete_role(role_id: UUID, session: Session = Depends(get_session)) -> None:
    role = _require_role(session, role_id)

    rankings = session.scalar(
        select(func.count()).select_from(Ranking).where(Ranking.role_id == role.id)
    )
    if rankings:
        # Триенето би отнесло класиранията с cascade, а с тях и следата зад
        # решенията. Затварянето е смяна на статуса, не изтриване.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ролята има {rankings} класирания и не се трие. "
                f"Затворете я със status={RoleStatus.CLOSED.value}."
            ),
        )

    session.delete(role)
    session.commit()


@router.post(
    "/{role_id}/rank",
    response_model=RankResponse,
    summary="Класира кандидатите за роля по активните правила",
)
def rank_candidates(
    role_id: UUID,
    payload: RankRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    scorer_factory: ScorerFactory = Depends(get_scorer_factory),
) -> RankResponse:
    role = _require_role(session, role_id)
    request = payload or RankRequest()
    ruleset = _resolve_ruleset(session, request.ruleset_version)

    try:
        scorer = scorer_factory(ruleset)
    except InvalidRulesError as exc:
        logger.error("Неизползваеми правила %s: %s", ruleset.version, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Правилата {ruleset.version} са неизползваеми: {exc}",
        ) from exc
    except ScoringEngineUnavailableError as exc:
        logger.error("Скоринг адаптерът е недостъпен: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Скоринг услугата е временно недостъпна.",
        ) from exc

    candidates = _select_candidates(session, request.candidate_ids)

    scored: list[tuple[Candidate, Ranking, ScoreResult]] = []
    for candidate in candidates:
        try:
            result = scorer.score(candidate, role)
        except InvalidRulesError as exc:
            # Изискванията на ролята, не правилата — но и двете са конфигурация.
            logger.error("Неизползваеми изисквания на роля %s: %s", role.id, exc)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Изискванията на ролята са неизползваеми: {exc}",
            ) from exc

        ranking = _upsert_ranking(session, candidate, role, ruleset, result)
        session.add(
            AuditLog(
                actor="system",
                action=AuditAction.CANDIDATE_SCORED,
                entity_type="ranking",
                entity_id=ranking.id,
                ruleset_id=ruleset.id,
                payload_in={
                    "role_id": str(role.id),
                    "candidate_id": str(candidate.id),
                    "mode": MODE.value,
                },
                payload_out=result.to_explanation(),
            )
        )
        scored.append((candidate, ranking, result))

    session.commit()

    # Подредбата по име е втори ключ нарочно: равни скорове трябва да излизат в
    # един и същи ред при всяко извикване, иначе класацията „трепти".
    scored.sort(key=lambda row: (-row[2].score, row[0].full_name))

    return RankResponse(
        role_id=role.id,
        role_title=role.title,
        ruleset_id=ruleset.id,
        ruleset_version=ruleset.version,
        engine=getattr(scorer, "name", type(scorer).__name__),
        mode=MODE.value,
        ranked=[
            RankedCandidate(
                position=position,
                ranking_id=ranking.id,
                candidate_id=candidate.id,
                full_name=candidate.full_name,
                score=float(result.score),
                meets_minimum=result.meets_minimum,
                factors=[factor.to_dict() for factor in result.factors],
            )
            for position, (candidate, ranking, result) in enumerate(scored, start=1)
        ],
    )


def _require_role(session: Session, role_id: UUID) -> Role:
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Няма роля с id {role_id}.",
        )
    return role


def _role_by_ref(session: Session, external_ref: str) -> Role | None:
    return session.scalars(select(Role).where(Role.external_ref == external_ref)).one_or_none()


def _resolve_ruleset(session: Session, version: str | None) -> Ruleset:
    """Посочената версия, или активната. Без правила няма класиране."""
    if version:
        ruleset = session.scalars(select(Ruleset).where(Ruleset.version == version)).one_or_none()
        if ruleset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Няма версия правила {version!r}.",
            )
        return ruleset

    ruleset = session.scalars(
        select(Ruleset)
        .where(Ruleset.status == RulesetStatus.ACTIVE)
        # Postgres слага NULL най-отпред при DESC, SQLite — най-отзад. Изричното
        # nulls_last() прави избора еднакъв в двете.
        .order_by(Ruleset.activated_at.desc().nulls_last())
    ).first()
    if ruleset is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Няма активна версия правила. Активирайте ruleset или подайте ruleset_version.",
        )
    return ruleset


def _select_candidates(session: Session, candidate_ids: list[UUID] | None) -> list[Candidate]:
    statement = select(Candidate).order_by(Candidate.full_name)
    if candidate_ids is not None:
        statement = statement.where(Candidate.id.in_(candidate_ids))

    candidates = list(session.scalars(statement))

    if candidate_ids is not None:
        missing = set(candidate_ids) - {candidate.id for candidate in candidates}
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Няма кандидати с id: {', '.join(sorted(str(item) for item in missing))}.",
            )

    return candidates


def _upsert_ranking(
    session: Session,
    candidate: Candidate,
    role: Role,
    ruleset: Ruleset,
    result: ScoreResult,
) -> Ranking:
    """Едно класиране на (кандидат, роля, правила, режим) — преизчислението го обновява.

    Нова версия правила ражда нов ред; старият остава, защото решение, взето с
    него, трябва да сочи към това, което е било сметнато тогава.
    """
    ranking = session.scalars(
        select(Ranking).where(
            Ranking.candidate_id == candidate.id,
            Ranking.role_id == role.id,
            Ranking.ruleset_id == ruleset.id,
            Ranking.mode == MODE,
        )
    ).one_or_none()

    if ranking is None:
        ranking = Ranking(
            candidate_id=candidate.id,
            role_id=role.id,
            ruleset_id=ruleset.id,
            mode=MODE,
            score=result.score,
            explanation=result.to_explanation(),
        )
        session.add(ranking)
    else:
        ranking.score = result.score
        ranking.explanation = result.to_explanation()

    session.flush()
    return ranking
