"""Пълният поток през POST /candidates/upload."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditAction, AuditLog, Candidate
from app.ocr import Document, OcrEngineUnavailableError, UnreadableDocumentError

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def upload(client, content: bytes, filename="cv.pdf", media_type="application/pdf"):
    return client.post(
        "/candidates/upload",
        files={"file": (filename, content, media_type)},
    )


class TestHappyPath:
    def test_returns_201_with_parsed_profile(self, client, sample_pdf_bytes):
        response = upload(client, sample_pdf_bytes)
        assert response.status_code == 201, response.text

        body = response.json()
        candidate = body["candidate"]
        assert candidate["full_name"] == "Ivan Petrov"
        assert candidate["email"] == "ivan.petrov@example.com"
        assert candidate["source_filename"] == "cv.pdf"

        profile = candidate["profile"]
        assert "python" in profile["skills"]
        assert "fastapi" in profile["skills"]
        assert profile["experience"][0]["organization"] == "Acme Corp"
        assert profile["education"][0]["institution"] == "Sofia University"

    def test_reports_extraction_metadata(self, client, sample_pdf_bytes):
        extraction = upload(client, sample_pdf_bytes).json()["extraction"]
        assert extraction["engine"] == "tesseract"
        assert extraction["characters"] > 0
        assert extraction["confidence"] == 1.0

    def test_persists_candidate_with_jsonb_profile(self, client, session, sample_pdf_bytes):
        upload(client, sample_pdf_bytes)

        candidate = session.scalars(select(Candidate)).one()
        assert candidate.full_name == "Ivan Petrov"
        # JSONB се връща като Python структура, не като низ.
        assert isinstance(candidate.profile, dict)
        assert isinstance(candidate.profile["skills"], list)
        assert candidate.raw_text and "Ivan Petrov" in candidate.raw_text
        # Защитените атрибути не се извличат от CV-то.
        assert candidate.protected_attributes == {}

    def test_writes_audit_log_entry(self, client, session, sample_pdf_bytes):
        upload(client, sample_pdf_bytes)

        entry = session.scalars(select(AuditLog)).one()
        assert entry.action is AuditAction.CV_INGESTED
        assert entry.entity_type == "candidate"
        assert entry.payload_in["filename"] == "cv.pdf"
        assert entry.payload_out["engine"] == "tesseract"


class TestValidation:
    def test_rejects_unsupported_type(self, client):
        response = upload(client, b"hello", filename="cv.txt", media_type="text/plain")
        assert response.status_code == 415

    def test_rejects_content_type_mismatch(self, client):
        # PNG байтове, обявени за PDF — вярваме на байтовете.
        response = upload(client, PNG_HEADER + b"\x00" * 64)
        assert response.status_code == 415
        assert "image/png" in response.json()["detail"]

    def test_rejects_unrecognised_content(self, client):
        response = upload(client, b"MZ\x90\x00 definitely not a pdf")
        assert response.status_code == 415

    def test_rejects_oversized_file(self, client, monkeypatch):
        monkeypatch.setattr(settings, "max_upload_bytes", 1024)
        response = upload(client, b"%PDF-1.4\n" + b"x" * 4096)
        assert response.status_code == 413

    def test_rejects_empty_file(self, client):
        response = upload(client, b"")
        assert response.status_code == 422

    def test_accepts_file_at_exactly_the_limit(self, client, monkeypatch, sample_pdf_bytes):
        monkeypatch.setattr(settings, "max_upload_bytes", len(sample_pdf_bytes))
        assert upload(client, sample_pdf_bytes).status_code == 201


class TestUnreadableDocuments:
    def test_corrupt_pdf_gives_422(self, client):
        response = upload(client, b"%PDF-1.4\n" + b"\x00\xff" * 200)
        assert response.status_code == 422

    def test_extractor_failure_gives_422(self, use_extractor, sample_pdf_bytes):
        class FailingExtractor:
            name = "failing"

            def extract_text(self, file: Document) -> str:
                raise UnreadableDocumentError("нечетимо")

        response = upload(use_extractor(FailingExtractor()), sample_pdf_bytes)
        assert response.status_code == 422
        assert "не може да бъде прочетен" in response.json()["detail"]

    def test_blank_extraction_gives_422(self, use_extractor, sample_pdf_bytes):
        class BlankExtractor:
            name = "blank"

            def extract_text(self, file: Document) -> str:
                return "   \n  "

        response = upload(use_extractor(BlankExtractor()), sample_pdf_bytes)
        assert response.status_code == 422
        assert "не е извлечен текст" in response.json()["detail"]

    def test_nothing_is_persisted_on_failure(self, use_extractor, session, sample_pdf_bytes):
        class BlankExtractor:
            name = "blank"

            def extract_text(self, file: Document) -> str:
                return ""

        upload(use_extractor(BlankExtractor()), sample_pdf_bytes)
        assert session.scalars(select(Candidate)).all() == []
        assert session.scalars(select(AuditLog)).all() == []


class TestEngineUnavailable:
    def test_missing_engine_gives_503_not_422(self, use_extractor, sample_pdf_bytes):
        """Липсващ Tesseract е наша грешка — не караме подателя да оправя файла."""

        class MissingEngineExtractor:
            name = "missing"

            def extract_text(self, file: Document) -> str:
                raise OcrEngineUnavailableError("няма Tesseract")

        response = upload(use_extractor(MissingEngineExtractor()), sample_pdf_bytes)
        assert response.status_code == 503


class TestSwappableAdapterEndToEnd:
    def test_endpoint_uses_injected_adapter(self, use_extractor):
        """Смяната на адаптер не изисква промяна в API слоя."""

        class StubExtractor:
            name = "stub"

            def extract_text(self, file: Document) -> str:
                return "Petar Georgiev\np.georgiev@example.com\n\nSkills\nGo, Kubernetes\n"

        response = upload(use_extractor(StubExtractor()), b"%PDF-1.4\nignored by stub")
        assert response.status_code == 201

        body = response.json()
        assert body["extraction"]["engine"] == "stub"
        assert body["candidate"]["full_name"] == "Petar Georgiev"
        assert "kubernetes" in body["candidate"]["profile"]["skills"]


@pytest.mark.parametrize("media_type", ["image/png", "image/jpeg", "image/tiff"])
def test_image_types_are_accepted_by_validation(use_extractor, media_type):
    """Валидацията пуска изображения; OCR-ът е подменен, за да не иска Tesseract."""

    class StubExtractor:
        name = "stub"

        def extract_text(self, file: Document) -> str:
            return "Ana Dimitrova\nSkills\nPython\n"

    headers = {
        "image/png": PNG_HEADER,
        "image/jpeg": b"\xff\xd8\xff\xe0",
        "image/tiff": b"II*\x00",
    }
    response = upload(
        use_extractor(StubExtractor()),
        headers[media_type] + b"\x00" * 128,
        filename=f"cv.{media_type.split('/')[1]}",
        media_type=media_type,
    )
    assert response.status_code == 201
