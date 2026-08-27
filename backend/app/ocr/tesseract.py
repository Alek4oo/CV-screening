"""Tesseract реализация на TextExtractor (bul+eng).

Три пътя през един интерфейс: обикновеният текст се декодира, PDF с текстов слой
се чете директно (по-точно и многократно по-бързо от OCR), а сканиран PDF минава
през Tesseract. Прагът MIN_TEXT_LAYER_CHARS решава кой от двата PDF пътя е.

Растеризирането е през pypdfium2 — колело от PyPI, без системен двоичен файл.
Затова средата е еднаква на Windows, в контейнера и в CI.

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

# PDF точката е 1/72 от инча — оттам се смята мащабът за исканите DPI.
PDF_POINTS_PER_INCH = 72

# Редът е важен: utf-8 отсява себе си сам, а cp1251 е това, което Windows
# редакторите у нас още произвеждат. Латиница-1 нарочно липсва — тя приема всичко
# и би превърнала кирилицата в безшумни глупости.
TEXT_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1251")


class TesseractExtractor:
    """Извлича текст от TXT (директно), PDF (pypdf) и сканиран PDF (pytesseract)."""

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
        if file.media_type == "text/plain":
            return self._plain_text(file.content)

        if file.media_type == "application/pdf":
            text = self._pdf_text_layer(file.content)
            if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
                logger.info("%s: text layer, %d characters", file.filename, len(text))
                return text
            logger.info("%s: no text layer, going through OCR", file.filename)
            return self._ocr_pdf(file.content)

        raise UnreadableDocumentError(f"Unsupported type for extraction: {file.media_type}")

    # --- реализация ---

    def _plain_text(self, content: bytes) -> str:
        """TXT не изисква нито OCR, нито двигател — само правилното декодиране."""
        for encoding in TEXT_ENCODINGS:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue

        raise UnreadableDocumentError(
            f"The text decodes with none of {', '.join(TEXT_ENCODINGS)}"
        )

    def _pdf_text_layer(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pypdf is not installed") from exc

        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise UnreadableDocumentError(f"Corrupt PDF: {exc}") from exc

        if not pages:
            raise UnreadableDocumentError("PDF with no pages")

        return "\n".join(pages)

    def _ocr_pdf(self, content: bytes) -> str:
        """Растеризира страница по страница и подава всяка на Tesseract."""
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pypdfium2 is not installed") from exc

        try:
            document = pdfium.PdfDocument(content)
        except pdfium.PdfiumError as exc:
            raise UnreadableDocumentError(f"The PDF cannot be opened: {exc}") from exc

        try:
            if len(document) == 0:
                raise UnreadableDocumentError("PDF with no pages to OCR")

            scale = self.dpi / PDF_POINTS_PER_INCH
            pages = []
            for index in range(len(document)):
                try:
                    # Една страница в паметта наведнъж — 300 DPI изображенията са
                    # десетки мегабайти, а CV-тата не са едностранични по правило.
                    image = document[index].render(scale=scale).to_pil()
                except pdfium.PdfiumError as exc:
                    raise UnreadableDocumentError(
                        f"Page {index + 1} cannot be rasterised: {exc}"
                    ) from exc
                pages.append(self._run_tesseract(image))
        finally:
            document.close()

        return "\n".join(pages)

    def _run_tesseract(self, image) -> str:
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover - липсваща зависимост
            raise OcrEngineUnavailableError("pytesseract is not installed") from exc

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        try:
            return pytesseract.image_to_string(image, lang=self.languages)
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrEngineUnavailableError("Tesseract was not found on PATH") from exc
        except pytesseract.TesseractError as exc:
            # Най-честият случай тук е липсващ езиков пакет (bul).
            raise OcrEngineUnavailableError(f"Tesseract returned an error: {exc}") from exc
