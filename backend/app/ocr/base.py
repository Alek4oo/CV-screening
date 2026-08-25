"""Договорът на OCR слоя.

Всичко над този модул знае само `extract_text(file) -> str`. Коя библиотека
върши работата, дали PDF-ът има текстов слой и как се растеризира са детайли на
реализацията — точно затова адаптерът е сменяем.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class OcrError(Exception):
    """Базова грешка на OCR слоя."""


class UnreadableDocumentError(OcrError):
    """Файлът е повреден, празен или не е това, за което се представя.

    Грешка на входа — вина на подадения документ, не на системата.
    """


class OcrEngineUnavailableError(OcrError):
    """Двигателят липсва или е счупен (няма Tesseract, няма poppler).

    Грешка на средата — документът може да е напълно наред.
    """


@dataclass(frozen=True, slots=True)
class Document:
    """Качен файл в паметта, заедно с това, което твърдим за него."""

    filename: str
    media_type: str
    content: bytes


@runtime_checkable
class TextExtractor(Protocol):
    """Интерфейсът, който всяка OCR реализация трябва да покрие."""

    name: str

    def extract_text(self, file: Document) -> str:
        """Връща суровия текст на документа.

        Хвърля UnreadableDocumentError при негоден вход и
        OcrEngineUnavailableError при липсващ двигател.
        """
        ...


# Подпис на файла → media type. Декларираният от клиента тип е твърдение;
# байтовете са доказателство.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)


def sniff_media_type(content: bytes) -> str | None:
    """Разпознава типа по първите байтове. None, ако подписът е непознат."""
    for signature, media_type in _MAGIC:
        if content.startswith(signature):
            return media_type
    return None
