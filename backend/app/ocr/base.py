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
    """Двигателят липсва или е счупен (няма Tesseract, липсва зависимост).

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
# байтовете са доказателство. Изображенията остават тук, макар вече да не ги
# приемаме: разпознат PNG дава ясен отказ вместо мъгливото „непознато съдържание".
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)

# Колко байта гледаме, преди да отсъдим „това е текст". Достатъчно, за да хванем
# двоичен файл, и достатъчно малко, за да не струва нищо при голям файл.
_TEXT_SAMPLE_BYTES = 8192

# Управляващите знаци, които се срещат в нормален текст: tab, LF, VT, FF, CR, ESC.
_TEXT_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1B})


def sniff_media_type(content: bytes) -> str | None:
    """Разпознава типа по съдържанието. None, ако не е нито един от познатите.

    Обикновеният текст няма подпис, затова се разпознава по изключване: щом
    байтовете не са ничий познат формат и не носят двоичен шум, това е text/plain.
    """
    for signature, media_type in _MAGIC:
        if content.startswith(signature):
            return media_type
    if content and _looks_like_text(content):
        return "text/plain"
    return None


def _looks_like_text(content: bytes) -> bool:
    """Евристиката на git: управляващ шум (в т.ч. нулев байт) значи двоичен файл."""
    sample = content[:_TEXT_SAMPLE_BYTES]
    return all(byte >= 0x20 or byte in _TEXT_CONTROL_BYTES for byte in sample)
