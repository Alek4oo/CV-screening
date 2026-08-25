"""OCR адаптерът: текстов слой, грешки и сменяемост."""

import shutil

import pytest

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
        with pytest.raises(UnreadableDocumentError):
            TesseractExtractor().extract_text(
                make_document(b"plain text", media_type="text/plain")
            )

    def test_garbage_image_raises_unreadable(self):
        with pytest.raises(UnreadableDocumentError):
            TesseractExtractor().extract_text(
                make_document(b"not an image", media_type="image/png")
            )


class TestSniffing:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (b"%PDF-1.7\n...", "application/pdf"),
            (b"\x89PNG\r\n\x1a\n...", "image/png"),
            (b"\xff\xd8\xff\xe0...", "image/jpeg"),
            (b"II*\x00...", "image/tiff"),
            (b"MZ\x90\x00", None),
            (b"", None),
        ],
    )
    def test_sniff(self, content, expected):
        assert sniff_media_type(content) == expected


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
    shutil.which("tesseract") is None,
    reason="Tesseract не е инсталиран на тази машина",
)
class TestRealOcr:
    """Пуска се само там, където бинарникът го има — в образа го има."""

    def test_ocr_reads_rendered_text(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (700, 140), "white")
        ImageDraw.Draw(image).text((12, 40), "Python Developer", fill="black")

        buffer = __import__("io").BytesIO()
        image.save(buffer, format="PNG")

        text = TesseractExtractor().extract_text(
            Document(filename="cv.png", media_type="image/png", content=buffer.getvalue())
        )
        assert "Python" in text
