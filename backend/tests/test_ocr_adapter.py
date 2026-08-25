"""OCR адаптерът: текстов слой, обикновен текст, грешки и сменяемост."""

import io
import shutil

import pytest

from app.core.config import settings
from app.ocr import Document, TextExtractor, UnreadableDocumentError, sniff_media_type
from app.ocr.tesseract import TesseractExtractor


def make_document(content: bytes, media_type: str = "application/pdf") -> Document:
    return Document(filename="cv.pdf", media_type=media_type, content=content)


class TestTextLayer:
    def test_reads_pdf_text_layer_without_tesseract(self, sample_pdf_bytes):
        # PDF с текстов слой не бива да минава през OCR изобщо.
        text = TesseractExtractor().extract_text(make_document(sample_pdf_bytes))
        assert "Ivan Petrov" in text
        assert "FastAPI" in text

    def test_corrupt_pdf_raises_unreadable(self):
        broken = b"%PDF-1.4\n" + b"\x00\xff" * 200
        with pytest.raises(UnreadableDocumentError):
            TesseractExtractor().extract_text(make_document(broken))

    def test_unsupported_media_type_raises_unreadable(self):
        # Изображенията отпаднаха — четими са само PDF и TXT.
        with pytest.raises(UnreadableDocumentError):
            TesseractExtractor().extract_text(
                make_document(b"\x89PNG\r\n\x1a\n", media_type="image/png")
            )


class TestPlainText:
    def test_reads_utf8_text(self):
        text = TesseractExtractor().extract_text(
            make_document("Ivan Petrov\nPython".encode("utf-8"), media_type="text/plain")
        )
        assert text == "Ivan Petrov\nPython"

    def test_strips_utf8_bom(self):
        text = TesseractExtractor().extract_text(
            make_document("Иван Петров".encode("utf-8-sig"), media_type="text/plain")
        )
        assert text == "Иван Петров"

    def test_reads_cyrillic_in_cp1251(self):
        # Windows редакторите у нас още произвеждат cp1251.
        text = TesseractExtractor().extract_text(
            make_document("Умения: Python".encode("cp1251"), media_type="text/plain")
        )
        assert text == "Умения: Python"

    def test_undecodable_bytes_raise_unreadable(self):
        with pytest.raises(UnreadableDocumentError):
            TesseractExtractor().extract_text(
                make_document(b"\x98\x98\x98", media_type="text/plain")
            )


class TestSniffing:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (b"%PDF-1.7\n...", "application/pdf"),
            (b"\x89PNG\r\n\x1a\n...", "image/png"),
            (b"\xff\xd8\xff\xe0...", "image/jpeg"),
            (b"II*\x00...", "image/tiff"),
            (b"Ivan Petrov\nPython, FastAPI\n", "text/plain"),
            ("Иван Петров".encode("utf-8"), "text/plain"),
            ("Иван Петров".encode("cp1251"), "text/plain"),
            (b"MZ\x90\x00", None),
            (b"", None),
        ],
    )
    def test_sniff(self, content, expected):
        assert sniff_media_type(content) == expected

    def test_binary_beyond_the_sample_is_still_accepted_as_text(self):
        """Гледаме само началото — това е цената на евристиката, не пропуск."""
        assert sniff_media_type(b"a" * 9000 + b"\x00") == "text/plain"


class TestSwappability:
    def test_custom_extractor_satisfies_protocol(self):
        class UpperCaseExtractor:
            name = "uppercase"

            def extract_text(self, file: Document) -> str:
                return file.content.decode().upper()

        extractor = UpperCaseExtractor()
        assert isinstance(extractor, TextExtractor)
        assert extractor.extract_text(make_document(b"cv")) == "CV"

    def test_tesseract_extractor_satisfies_protocol(self):
        assert isinstance(TesseractExtractor(), TextExtractor)

    def test_languages_are_configurable(self):
        assert TesseractExtractor(languages="bul+eng").languages == "bul+eng"


@pytest.mark.skipif(
    shutil.which("tesseract") is None and not settings.tesseract_cmd,
    reason="Tesseract не е нито на PATH, нито посочен през TESSERACT_CMD",
)
class TestRealOcr:
    """Пуска се само там, където двигателят го има — в образа го има.

    На Windows Tesseract рядко е на PATH, затова уважаваме и TESSERACT_CMD.
    """

    def test_ocr_reads_scanned_pdf(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (700, 140), "white")
        ImageDraw.Draw(image).text((12, 40), "Python Developer", fill="black")

        buffer = io.BytesIO()
        # PDF без текстов слой — точно случаят, заради който OCR-ът съществува.
        image.save(buffer, format="PDF")

        extractor = TesseractExtractor(
            languages=settings.ocr_languages,
            tesseract_cmd=settings.tesseract_cmd,
        )
        text = extractor.extract_text(
            Document(
                filename="scan.pdf",
                media_type="application/pdf",
                content=buffer.getvalue(),
            )
        )
        assert "Python" in text
