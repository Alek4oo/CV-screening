"""Качване на CV: валидация → OCR → парсване → Candidate + одитен запис.

Разделението на грешките е нарочно и следва „чия е вината":
  415 — не приемаме такъв тип файл
  413 — файлът е над лимита
  422 — типът е приемлив, но документът е нечетим
  503 — документът е наред, двигателят липсва
"""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.models import AuditAction, AuditLog, Candidate
from app.ocr import (
    Document,
    OcrEngineUnavailableError,
    TextExtractor,
    UnreadableDocumentError,
    get_text_extractor,
    sniff_media_type,
)
from app.api.schemas import (
    CandidateDetailRead,
    CandidateRead,
    CandidateUploadResponse,
    ExtractionInfo,
)
from app.parsing import parse_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"])

_READ_CHUNK = 64 * 1024

MAX_PAGE_SIZE = 200


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=CandidateUploadResponse,
    summary="Uploads a CV (PDF or TXT) and creates a candidate",
)
async def upload_candidate(
    file: UploadFile = File(..., description="A CV as PDF or plain text"),
    session: Session = Depends(get_session),
    extractor: TextExtractor = Depends(get_text_extractor),
) -> CandidateUploadResponse:
    content = await _read_within_limit(file)
    media_type = _validate_type(file, content)

    document = Document(
        filename=file.filename or "cv",
        media_type=media_type,
        content=content,
    )

    try:
        text = extractor.extract_text(document)
    except UnreadableDocumentError as exc:
        logger.warning("Unreadable document %s: %s", document.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The document could not be read: {exc}",
        ) from exc
    except OcrEngineUnavailableError as exc:
        # Не е вина на подателя — не го караме да коригира файла си.
        logger.error("The OCR engine is unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The OCR service is temporarily unavailable.",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text was extracted. If the document is scanned, check its quality.",
        )

    parsed = parse_profile(text)
    candidate = Candidate(
        full_name=parsed.full_name or Path(document.filename).stem or "Unknown candidate",
        email=parsed.contact.get("email"),
        source_filename=document.filename,
        raw_text=text,
        profile=parsed.to_dict(),
        # Защитените атрибути не се извличат от CV-то на този етап. Празно е
        # правилната стойност, а не измислена.
        protected_attributes={},
    )
    session.add(candidate)
    session.flush()

    session.add(
        AuditLog(
            actor="system",
            action=AuditAction.CV_INGESTED,
            entity_type="candidate",
            entity_id=candidate.id,
            payload_in={
                "filename": document.filename,
                "media_type": media_type,
                "bytes": len(content),
            },
            payload_out={
                "engine": getattr(extractor, "name", type(extractor).__name__),
                "characters": len(text),
                "confidence": parsed.confidence,
            },
        )
    )
    session.commit()
    session.refresh(candidate)

    return CandidateUploadResponse(
        candidate=candidate,
        extraction=ExtractionInfo(
            engine=getattr(extractor, "name", type(extractor).__name__),
            characters=len(text),
            confidence=parsed.confidence,
        ),
    )


@router.get(
    "",
    response_model=list[CandidateRead],
    summary="Lists candidates",
)
def list_candidates(
    session: Session = Depends(get_session),
    q: str | None = Query(default=None, description="Search by name or email"),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> list[Candidate]:
    statement = select(Candidate).order_by(Candidate.created_at.desc(), Candidate.full_name)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        statement = statement.where(
            Candidate.full_name.ilike(needle) | Candidate.email.ilike(needle)
        )
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get(
    "/{candidate_id}",
    response_model=CandidateDetailRead,
    summary="Returns one candidate, without their protected attributes",
)
def get_candidate(candidate_id: UUID, session: Session = Depends(get_session)) -> Candidate:
    """Профилът, суровият текст и метаданните — но не и `protected_attributes`.

    Схемата на отговора няма такова поле нарочно (виж CandidateDetailRead):
    признаците са вход единствено на bias-одита, не на прегледа от рекрутер.
    """
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No candidate with id {candidate_id}.",
        )
    return candidate


async def _read_within_limit(file: UploadFile) -> bytes:
    """Чете на парчета и спира на лимита, вместо да поеме файла в паметта."""
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"The file exceeds the {settings.max_upload_bytes} byte limit.",
            )
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The file is empty.",
        )

    return b"".join(chunks)


def _validate_type(file: UploadFile, content: bytes) -> str:
    """Декларираният тип трябва и да е позволен, и да отговаря на байтовете."""
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in settings.allowed_upload_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported type {declared or 'unknown'!r}. "
                f"Accepted: {', '.join(settings.allowed_upload_types)}."
            ),
        )

    sniffed = sniff_media_type(content)
    if sniffed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content was not recognised as PDF or text.",
        )
    if sniffed != declared:
        # Разминаването е или объркан клиент, или преименуван файл. И в двата
        # случая вярваме на байтовете и отказваме.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"The content is {sniffed} but was declared as {declared}.",
        )

    return sniffed
