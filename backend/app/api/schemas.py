"""Pydantic схеми на API слоя."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtractionInfo(BaseModel):
    """Как е добит текстът — част от проследимостта, не козметика."""

    engine: str = Field(description="Име на OCR адаптера, свършил работата")
    characters: int = Field(description="Дължина на извлечения текст")
    confidence: float = Field(description="Дял намерени секции при парсването, 0..1")


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str | None = None
    source_filename: str | None = None
    profile: dict[str, Any]
    created_at: datetime


class CandidateUploadResponse(BaseModel):
    candidate: CandidateRead
    extraction: ExtractionInfo
