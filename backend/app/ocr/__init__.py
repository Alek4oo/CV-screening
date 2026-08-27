"""Регистър на OCR адаптерите.

Смяната на реализация е смяна на OCR_BACKEND в средата — нищо в API слоя не се
пипа. Нова реализация се добавя с един ред в _BACKENDS.
"""

from collections.abc import Callable
from functools import lru_cache

from app.core.config import settings
from app.ocr.base import (
    Document,
    OcrEngineUnavailableError,
    OcrError,
    TextExtractor,
    UnreadableDocumentError,
    sniff_media_type,
)
from app.ocr.tesseract import TesseractExtractor

__all__ = [
    "Document",
    "OcrEngineUnavailableError",
    "OcrError",
    "TextExtractor",
    "UnreadableDocumentError",
    "get_text_extractor",
    "sniff_media_type",
]


def _build_tesseract() -> TextExtractor:
    return TesseractExtractor(
        languages=settings.ocr_languages,
        tesseract_cmd=settings.tesseract_cmd,
        dpi=settings.ocr_dpi,
    )


_BACKENDS: dict[str, Callable[[], TextExtractor]] = {
    "tesseract": _build_tesseract,
}


@lru_cache(maxsize=1)
def get_text_extractor() -> TextExtractor:
    """FastAPI зависимост — адаптерът, избран от конфигурацията.

    Тестовете го подменят през app.dependency_overrides, без да пипат средата.
    """
    try:
        factory = _BACKENDS[settings.ocr_backend]
    except KeyError:
        known = ", ".join(sorted(_BACKENDS))
        raise OcrEngineUnavailableError(
            f"Unknown OCR_BACKEND {settings.ocr_backend!r}. Available: {known}"
        ) from None
    return factory()
