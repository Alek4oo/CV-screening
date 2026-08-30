"""Класация за преглед и решението на рекрутера по нея.

Тук живее human-in-the-loop частта от PRD-то. Три неща в този модул не са
въпрос на вкус:

  * Няма ендпойнт, който да отхвърля кандидат автоматично. Единственият път до
    `Decision` е PUT-ът по-долу, а той изисква име на човек и обосновка.
  * `meets_minimum=false` не филтрира и не отхвърля — само вдига флаг в реда.
  * Отговорите не съдържат `protected_attributes`. Схемата няма такова поле, за
    да не може изглед да ги покаже дори по невнимание.

Разделението на грешките следва останалите модули:
  422 — обосновката или името липсват (валидира се в схемата)
  404 — няма такава роля или класиране
  409 — ролята няма класирания с исканата версия правила

Позицията в класацията се смята върху пълния набор за (роля, версия), преди
филтрите. Иначе „покажи само за преглед" би преномерирал кандидатите и рекрутер,
който е видял №3, после би го намерил като №1.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import (
    AuditEntryRead,
    DecisionRead,
    DecisionWrite,
    FactorOut,
    RankingDetail,
    RankingListResponse,
    RankingRow,
    RoleRef,
    RulesetRef,
)
from app.core.db import get_session
from app.models import (
    AuditAction,
    AuditLog,
    Decision,
    DecisionOutcome,
    Ranking,
    RankingMode,
    Role,
    Ruleset,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rankings"])

MODE = RankingMode.MASKED

MAX_PAGE_SIZE = 200

# Колко фактора влизат в резюмето на реда. Таблицата показва защо кандидатът е
# където е; цялото обяснение стои в детайла.
TOP_FACTORS = 3

# Факторите, които описват твърдия минимум. Липсващо предпочитано умение не е
# пропуск и не влиза в колоната „липсва".
HARD_FACTORS = ("required_skills", "experience", "education", "languages")

SORTS = ("score_desc", "score_asc", "name_asc", "name_desc")


@router.get(
    "/roles/{role_id}/rankings",
    response_model=RankingListResponse,
    summary="A role's leaderboard — stored rankings with their decisions",
)
def list_role_rankings(
    role_id: UUID,
    session: Session = Depends(get_session),
    ruleset_version: str | None = Query(
        default=None, description="Ruleset version. Defaults to the most recently activated."
    ),
    outcome: DecisionOutcome | None = Query(
        default=None, description="Decision status. pending covers the undecided too."
    ),
    meets_minimum: bool | None = Query(
        default=None, description="Only those meeting, or only those missing, the minimum"
    ),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    q: str | None = Query(default=None, description="Search by name or email"),
    sort: str = Query(default="score_desc", description=" | ".join(SORTS)),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> RankingListResponse:
    role = _require_role(session, role_id)

    if sort not in SORTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown sort {sort!r}. Allowed: {', '.join(SORTS)}.",
        )

    available = _available_rulesets(session, role.id)
    if not available:
        # Ролята съществува, но още не е класирана. Празна класация, не грешка —
        # рекрутерът вижда роля без кандидати, а не счупен изглед.
        return RankingListResponse(
            role_id=role.id,
            role_title=role.title,
            role_status=role.status,
            mode=MODE.value,
            total=0,
            total_unfiltered=0,
            counts=_empty_counts(),
            rows=[],
        )

    chosen = _choose_ruleset(available, ruleset_version)

    rankings = _ordered_rankings(session, role.id, chosen.id)
    rows = [_row(ranking, position) for position, ranking in enumerate(rankings, start=1)]

    filtered = [
        row for row in rows if _matches(row, outcome, meets_minimum, min_score, max_score, q)
    ]
    filtered.sort(key=_sort_key(sort))

    return RankingListResponse(
        role_id=role.id,
        role_title=role.title,
        role_status=role.status,
        ruleset=RulesetRef.model_validate(chosen),
        available_rulesets=[RulesetRef.model_validate(item) for item in available],
        mode=MODE.value,
        total=len(filtered),
        total_unfiltered=len(rows),
        # Броенето е върху пълната класация, не върху филтрираната: иначе
        # „за преглед: 0" би значело и „няма такива", и „скрити са от филтъра".
        counts=_counts(rows),
        rows=filtered[offset : offset + limit],
    )


@router.get(
    "/rankings/{ranking_id}",
    response_model=RankingDetail,
    summary="One ranking with the explanation behind it",
)
def get_ranking(ranking_id: UUID, session: Session = Depends(get_session)) -> RankingDetail:
    ranking = _require_ranking(session, ranking_id)
    explanation = ranking.explanation or {}

    ordered = _ordered_rankings(session, ranking.role_id, ranking.ruleset_id)
    position = next(
        (index for index, item in enumerate(ordered, start=1) if item.id == ranking.id), 0
    )

    weights = (ranking.ruleset.definition or {}).get("weights") or {}

    return RankingDetail(
        ranking_id=ranking.id,
        position=position,
        score=float(ranking.score),
        meets_minimum=bool(explanation.get("meets_minimum", False)),
        mode=ranking.mode.value,
        engine=str(explanation.get("engine") or ""),
        factors=_factors(explanation),
        weights={name: float(value) for name, value in weights.items()},
        candidate=ranking.candidate,
        role=RoleRef.model_validate(ranking.role),
        ruleset=RulesetRef.model_validate(ranking.ruleset),
        decision=(
            DecisionRead.model_validate(ranking.decision) if ranking.decision is not None else None
        ),
        ranked_at=ranking.updated_at,
    )


@router.get(
    "/rankings/{ranking_id}/audit",
    response_model=list[AuditEntryRead],
    summary="The audit trail of the ranking and the decisions on it",
)
def get_ranking_audit(
    ranking_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
) -> list[AuditLog]:
    ranking = _require_ranking(session, ranking_id)

    # Логът сочи ту към класирането, ту към решението по него. За рекрутера това
    # е една история — „сметнато тогава, решено от този" — затова се чете наведнъж.
    entity_ids = [ranking.id]
    if ranking.decision is not None:
        entity_ids.append(ranking.decision.id)

    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_id.in_(entity_ids))
            .order_by(AuditLog.occurred_at.desc())
            .limit(limit)
        )
    )


@router.put(
    "/rankings/{ranking_id}/decision",
    response_model=DecisionRead,
    summary="Records the recruiter's decision on the ranking",
)
def put_decision(
    ranking_id: UUID,
    payload: DecisionWrite,
    session: Session = Depends(get_session),
) -> Decision:
    """Единственият път, по който кандидат сменя статус.

    Няма автоматичен вариант на този ендпойнт и това е нарочно: по PRD крайното
    решение е на човек. Затова заявката носи име и обосновка, а те влизат и в
    `Decision`, и в одита — заедно с версията правила, дала скора.
    """
    ranking = _require_ranking(session, ranking_id)

    decision = ranking.decision
    previous = decision.outcome.value if decision is not None else DecisionOutcome.PENDING.value
    now = datetime.now(timezone.utc)

    if decision is None:
        decision = Decision(ranking_id=ranking.id, ruleset_id=ranking.ruleset_id)
        session.add(decision)

    decision.outcome = payload.outcome
    decision.decided_by = payload.decided_by
    decision.decided_at = now
    decision.rationale = payload.rationale
    # Версията, с която е сметнат скорът в момента на решението. Преизчисление с
    # нови правила ражда ново класиране, така че тази стойност после не мърда.
    decision.ruleset_id = ranking.ruleset_id
    session.flush()

    session.add(
        AuditLog(
            actor=payload.decided_by,
            action=AuditAction.DECISION_RECORDED,
            entity_type="decision",
            entity_id=decision.id,
            ruleset_id=ranking.ruleset_id,
            payload_in={
                "ranking_id": str(ranking.id),
                "candidate_id": str(ranking.candidate_id),
                "role_id": str(ranking.role_id),
                "outcome": payload.outcome.value,
                "rationale": payload.rationale,
            },
            payload_out={
                "previous_outcome": previous,
                "decided_at": now.isoformat(),
                "score": float(ranking.score),
                "meets_minimum": bool((ranking.explanation or {}).get("meets_minimum", False)),
            },
        )
    )
    session.commit()
    session.refresh(decision)

    logger.info(
        "Decision %s on ranking %s by %s",
        decision.outcome.value,
        ranking.id,
        payload.decided_by,
    )
    return decision


# --- помощни ---


def _require_role(session: Session, role_id: UUID) -> Role:
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No role with id {role_id}.",
        )
    return role


def _require_ranking(session: Session, ranking_id: UUID) -> Ranking:
    ranking = session.scalars(
        select(Ranking)
        .where(Ranking.id == ranking_id)
        .options(
            selectinload(Ranking.candidate),
            selectinload(Ranking.role),
            selectinload(Ranking.ruleset),
            selectinload(Ranking.decision),
        )
    ).one_or_none()
    if ranking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ranking with id {ranking_id}.",
        )
    return ranking


def _available_rulesets(session: Session, role_id: UUID) -> list[Ruleset]:
    """Версиите, с които ролята вече е класирана — най-скорошната отпред."""
    return list(
        session.scalars(
            select(Ruleset)
            .join(Ranking, Ranking.ruleset_id == Ruleset.id)
            .where(Ranking.role_id == role_id, Ranking.mode == MODE)
            .group_by(Ruleset.id)
            # Както в /rank: изричното nulls_last() изравнява Postgres и SQLite.
            .order_by(Ruleset.activated_at.desc().nulls_last(), Ruleset.created_at.desc())
        )
    )


def _choose_ruleset(available: list[Ruleset], version: str | None) -> Ruleset:
    if version is None:
        return available[0]

    chosen = next((item for item in available if item.version == version), None)
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The role has no rankings under version {version!r}. "
                f"Available: {', '.join(item.version for item in available)}."
            ),
        )
    return chosen


def _ordered_rankings(session: Session, role_id: UUID, ruleset_id: UUID) -> list[Ranking]:
    """Пълната класация за (роля, версия), подредена стабилно.

    Името е втори ключ по същата причина както в /rank: равни скорове трябва да
    излизат в един и същ ред при всяко четене, иначе позициите „трептят".
    """
    rankings = list(
        session.scalars(
            select(Ranking)
            .where(
                Ranking.role_id == role_id,
                Ranking.ruleset_id == ruleset_id,
                Ranking.mode == MODE,
            )
            .options(selectinload(Ranking.candidate), selectinload(Ranking.decision))
        )
    )
    rankings.sort(key=lambda item: (-float(item.score), item.candidate.full_name))
    return rankings


def _factors(explanation: dict) -> list[FactorOut]:
    raw = explanation.get("factors")
    if not isinstance(raw, list):
        return []
    return [FactorOut.model_validate(item) for item in raw if isinstance(item, dict)]


def _row(ranking: Ranking, position: int) -> RankingRow:
    explanation = ranking.explanation or {}
    factors = _factors(explanation)
    decision = ranking.decision

    return RankingRow(
        ranking_id=ranking.id,
        position=position,
        candidate_id=ranking.candidate_id,
        full_name=ranking.candidate.full_name,
        email=ranking.candidate.email,
        score=float(ranking.score),
        meets_minimum=bool(explanation.get("meets_minimum", False)),
        top_factors=sorted(factors, key=lambda factor: -factor.contribution)[:TOP_FACTORS],
        missing=[
            item
            for factor in factors
            if factor.name in HARD_FACTORS
            for item in factor.missing
        ],
        outcome=decision.outcome if decision is not None else DecisionOutcome.PENDING,
        decided_by=decision.decided_by if decision is not None else None,
        decided_at=decision.decided_at if decision is not None else None,
        ranked_at=ranking.updated_at,
    )


def _empty_counts() -> dict[str, int]:
    return {member.value: 0 for member in DecisionOutcome}


def _counts(rows: list[RankingRow]) -> dict[str, int]:
    counts = _empty_counts()
    for row in rows:
        counts[row.outcome.value] += 1
    return counts


def _matches(
    row: RankingRow,
    outcome: DecisionOutcome | None,
    meets_minimum: bool | None,
    min_score: float | None,
    max_score: float | None,
    q: str | None,
) -> bool:
    if outcome is not None and row.outcome is not outcome:
        return False
    if meets_minimum is not None and row.meets_minimum is not meets_minimum:
        return False
    if min_score is not None and row.score < min_score:
        return False
    if max_score is not None and row.score > max_score:
        return False
    if q and q.strip():
        haystack = f"{row.full_name} {row.email or ''}".casefold()
        if q.strip().casefold() not in haystack:
            return False
    return True


def _sort_key(sort: str):
    """Ключ за подредбата. Вторият елемент е tie-breaker, за да е детерминирана."""
    if sort == "score_asc":
        return lambda row: (row.score, row.full_name.casefold())
    if sort == "name_asc":
        return lambda row: (row.full_name.casefold(), -row.score)
    if sort == "name_desc":
        return lambda row: (_Descending(row.full_name.casefold()), -row.score)
    return lambda row: (-row.score, row.full_name.casefold())


class _Descending:
    """Обръща сравнението на низ — низходящо име при възходящ втори ключ."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: "_Descending") -> bool:
        return other.value < self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Descending) and other.value == self.value
