"""Tesseract реализация на TextExtractor (bul+eng).

Два пътя през един интерфейс: PDF с текстов слой се чете директно (по-точно и
многократно по-бързо от OCR), а сканиран PDF или изображение минава през
Tesseract. Прагът MIN_TEXT_LAYER_CHARS решава кой път е кой.

Тежките зависимости се внасят вътре в методите нарочно — модулът трябва да е
importable на машина без Tesseract, за да работят тестовете с друг адаптер.
"""

import io
import logging

from app.ocr.base import (
    Document,
    OcrEngineUnavailableError,
    UnreadableDocumentError,
)

logger = logging.getLogger(__name__)

# Под този брой знаци приемаме, че PDF-ът няма истински текстов слой (сканиран
# документ често носи няколко знака шум от воден знак или метаданни).
MIN_TEXT_LAYER_CHARS = 40


class TesseractExtractor:
    """Извлича текст през pypdf (текстов слой) и pytesseract (OCR)."""

    name = "tesseract"

    def __init__(
        self,
        languages: str = "bul+eng",
        tesseract_cmd: str | None = None,
        dpi: int = 300,
    ) -> None:
        self.languages = languages
        self.tesseract_cmd = tesseract_cmd
        self.dpi = dpi

    # --- публичен интерфейс ---

    def extract_text(self, file: Document) -> str:
        if file.media_type == "application/pdf":
            text = self._pdf_text_layer(file.content)
            if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
                logger.info("%s: текстов слой, %d знака", file.filename, len(text))
                return text
            logger.info("%s: няма текстов слой, минава през OCR", file.filename)
            return self._ocr_pdf(file.content)

        if file.media_type.startswith("image/"):
            return self._ocr_image(file.content)

        raise UnreadableDocumentError(f"Неподдържан тип за OCR: {file.media_type}")

    # --- реализация ---

    def _pdf_text_layer(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pypdf не е инсталиран") from exc

        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise UnreadableDocumentError(f"Повреден PDF: {exc}") from exc

        if not pages:
            raise UnreadableDocumentError("PDF без страници")

        return "\n".join(pages)

    def _ocr_pdf(self, content: bytes) -> str:
        try:
            from pdf2image import convert_from_bytes
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pdf2image не е инсталиран") from exc

        try:
            images = convert_from_bytes(content, dpi=self.dpi)
        except Exception as exc:
            # pdf2image бърка липсващия poppler с невалиден PDF — разделяме ги по
            # името на изключението, защото типовете идват от вътрешен модул.
            if "poppler" in str(exc).lower() or "Info" in type(exc).__name__:
                raise OcrEngineUnavailableError(f"poppler липсва или е счупен: {exc}") from exc
            raise UnreadableDocumentError(f"PDF-ът не може да се растеризира: {exc}") from exc

        if not images:
            raise UnreadableDocumentError("PDF без страници за OCR")

        return "\n".join(self._run_tesseract(image) for image in images)

    def _ocr_image(self, content: bytes) -> str:
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("Pillow не е инсталиран") from exc

        try:
            image = Image.open(io.BytesIO(content))
            image.load()
        except UnidentifiedImageError as exc:
            raise UnreadableDocumentError("Файлът не е разпознаваемо изображение") from exc
        except Exception as exc:
            raise UnreadableDocumentError(f"Повредено изображение: {exc}") from exc

        return self._run_tesseract(image)

    def _run_tesseract(self, image) -> str:
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pytesseract не е инсталиран") from exc

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        try:
            return pytesseract.image_to_string(image, lang=self.languages)
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrEngineUnavailableError("Tesseract не е намерен на PATH") from exc
        except pytesseract.TesseractError as exc:
            # Най-честият случай тук е липсващ езиков пакет (bul).
            raise OcrEngineUnavailableError(f"Tesseract върна грешка: {exc}") from exc
