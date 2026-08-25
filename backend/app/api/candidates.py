"""Качване на CV: валидация → OCR → парсване → Candidate + одитен запис.

Разделението на грешките е нарочно и следва „чия е вината":
  415 — не приемаме такъв тип файл
  413 — файлът е над лимита
  422 — типът е приемлив, но документът е нечетим
  503 — документът е наред, двигателят липсва
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
from app.api.schemas import CandidateUploadResponse, ExtractionInfo
from app.parsing import parse_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/candidates", tags=["candidates"])

_READ_CHUNK = 64 * 1024


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=CandidateUploadResponse,
    summary="Качва CV (PDF/изображение) и създава кандидат",
)
async def upload_candidate(
    file: UploadFile = File(..., description="CV във формат PDF, PNG, JPEG или TIFF"),
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
        logger.warning("Нечетим документ %s: %s", document.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Документът не може да бъде прочетен: {exc}",
        ) from exc
    except OcrEngineUnavailableError as exc:
        # Не е вина на подателя — не го караме да коригира файла си.
        logger.error("OCR двигателят е недостъпен: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR услугата е временно недостъпна.",
        ) from exc

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="От документа не е извлечен текст. Ако е сканиран, проверете качеството.",
        )

    parsed = parse_profile(text)
    candidate = Candidate(
        full_name=parsed.full_name or Path(document.filename).stem or "Неизвестен кандидат",
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


async def _read_within_limit(file: UploadFile) -> bytes:
    """Чете на парчета и спира на лимита, вместо да поеме файла в паметта."""
    chunks: list[bytes] = []
    total = 0

    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Файлът надхвърля лимита от {settings.max_upload_bytes} байта.",
            )
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файлът е празен.",
        )

    return b"".join(chunks)


def _validate_type(file: UploadFile, content: bytes) -> str:
    """Декларираният тип трябва и да е позволен, и да отговаря на байтовете."""
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared not in settings.allowed_upload_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Неподдържан тип {declared or 'неизвестен'!r}. "
                f"Приемаме: {', '.join(settings.allowed_upload_types)}."
            ),
        )

    sniffed = sniff_media_type(content)
    if sniffed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Съдържанието на файла не е разпознато като PDF или изображение.",
        )
    if sniffed != declared:
        # Разминаването е или объркан клиент, или преименуван файл. И в двата
        # случая вярваме на байтовете и отказваме.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Съдържанието е {sniffed}, а е обявено като {declared}.",
        )

    return sniffed
