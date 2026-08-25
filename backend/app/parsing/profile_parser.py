"""Извлича структуриран профил от суровия текст на CV.

Подходът е правилово-базиран: разделяне по заглавия на секции, после регулярни
изрази в рамките на секцията. Умишлено не е ML — резултатът трябва да е
обясним и проверим от рекрутер, а грешките да са предвидими.

Всичко тук е евристика върху свободен текст. Полето `confidence` казва колко
от очакваните секции са намерени, за да не се преструва изходът на сигурен.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.parsing.vocabulary import (
    DEGREE_KEYWORDS,
    PRESENT_MARKERS,
    SECTION_HEADINGS,
    SKILL_ALIASES,
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?){2,4}\d{2,4}")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# 2019 - 2023 / 2019–настоящем / 03.2019 - 05.2021
DATE_RANGE_RE = re.compile(
    r"((?:\d{1,2}[./])?(?:19|20)\d{2})\s*[-–—]{1,2}\s*"
    r"((?:\d{1,2}[./])?(?:19|20)\d{2}|" + "|".join(PRESENT_MARKERS) + r")",
    re.IGNORECASE,
)
# Разделители на изброени умения в рамките на ред.
SKILL_SPLIT_RE = re.compile(r"[,;•·|/]|\s{3,}")
BULLET_RE = re.compile(r"^\s*[-•*·–—]\s*")


@dataclass
class ParsedProfile:
    """Структурираният профил, който отива в Candidate.profile (JSONB)."""

    full_name: str | None = None
    contact: dict[str, str] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("full_name")  # името живее в собствена колона на Candidate
        return data


def parse_profile(text: str) -> ParsedProfile:
    """Превръща суров текст на CV в структуриран профил."""
    lines = [line.strip() for line in text.splitlines()]
    sections = _split_sections(lines)

    profile = ParsedProfile()
    profile.full_name = _find_name(lines)
    profile.contact = _find_contact(text)
    profile.skills = _find_skills(text, sections.get("skills", []))
    profile.experience = _parse_experience(sections.get("experience", []))
    profile.education = _parse_education(sections.get("education", []))
    profile.languages = _parse_flat_list(sections.get("languages", []))
    profile.confidence = _confidence(profile)
    return profile


# --- секции ---


def _match_heading(line: str) -> str | None:
    """Връща ключа на секцията, ако редът е нейно заглавие."""
    stripped = line.strip().rstrip(":").strip()
    # Заглавията са къси. Дълъг ред, съдържащ "опит", е изречение, не заглавие.
    if not stripped or len(stripped) > 40:
        return None

    lowered = stripped.lower()
    for section, headings in SECTION_HEADINGS.items():
        if any(lowered == heading for heading in headings):
            return section
    # По-хлабаво съвпадение: "Професионален опит (последни 5 години)"
    for section, headings in SECTION_HEADINGS.items():
        if any(lowered.startswith(heading) for heading in headings):
            return section
    return None


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in lines:
        heading = _match_heading(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        if current and line:
            sections[current].append(line)

    return sections


# --- отделните полета ---


def _find_name(lines: list[str]) -> str | None:
    """Първият смислен ред обикновено е името — стандарт де факто в CV-тата."""
    for line in lines[:12]:
        if not line or _match_heading(line):
            continue
        if EMAIL_RE.search(line) or YEAR_RE.search(line) or "@" in line:
            continue
        words = line.replace(",", " ").split()
        if not 2 <= len(words) <= 4:
            continue
        if all(word[:1].isupper() and word.isalpha() for word in words):
            return " ".join(words)
    return None


def _find_contact(text: str) -> dict[str, str]:
    contact: dict[str, str] = {}
    email = EMAIL_RE.search(text)
    if email:
        contact["email"] = email.group(0)

    # Телефонният шаблон лесно лапа години и пощенски кодове — искаме поне 8 цифри.
    for match in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) >= 8:
            contact["phone"] = match.group(0).strip()
            break

    return contact


def _find_skills(full_text: str, section_lines: list[str]) -> list[str]:
    """Умения от секцията + всичко познато, срещнато другаде в текста."""
    found: set[str] = set()
    lowered_text = full_text.lower()

    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            # Границите пазят "go" от "Google" и "js" от "jsx".
            if re.search(rf"(?<![\w#+.]){re.escape(alias)}(?![\w#+])", lowered_text):
                found.add(canonical)
                break

    # Изброените в секцията "Умения" се пазят и когато не са в речника —
    # иначе тихо губим специфични за домейна технологии.
    for line in section_lines:
        line = BULLET_RE.sub("", line)
        for chunk in SKILL_SPLIT_RE.split(line):
            chunk = chunk.strip(" .\t")
            if 2 <= len(chunk) <= 32 and not YEAR_RE.search(chunk):
                found.add(chunk.lower())

    return sorted(found)


def _parse_experience(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for line in lines:
        clean = BULLET_RE.sub("", line).strip()
        if not clean:
            continue

        match = DATE_RANGE_RE.search(clean)
        if not match:
            # Ред без дати най-често е описание към предходната позиция.
            if entries:
                entries[-1].setdefault("details", []).append(clean)
            continue

        remainder = DATE_RANGE_RE.sub("", clean).strip(" ,;-–—|")
        title, organization = _split_title_org(remainder)
        end = match.group(2)
        entries.append(
            {
                "title": title,
                "organization": organization,
                "start": match.group(1),
                "end": None if end.lower() in PRESENT_MARKERS else end,
                "current": end.lower() in PRESENT_MARKERS,
                "raw": clean,
            }
        )

    return entries


def _split_title_org(text: str) -> tuple[str | None, str | None]:
    """Разделя "Backend Developer, Acme" или "Developer at Acme"."""
    for separator in (" — ", " – ", " - ", ", ", " at ", " в ", " @ "):
        if separator in text:
            left, _, right = text.partition(separator)
            return left.strip() or None, right.strip() or None
    return (text.strip() or None), None


def _parse_education(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for line in lines:
        clean = BULLET_RE.sub("", line).strip()
        if not clean:
            continue

        lowered = clean.lower()
        degree = next((word for word in DEGREE_KEYWORDS if word in lowered), None)
        year_match = re.findall(r"\b(?:19|20)\d{2}\b", clean)

        if not degree and not year_match:
            if entries:
                entries[-1].setdefault("details", []).append(clean)
            continue

        remainder = re.sub(r"\b(?:19|20)\d{2}\b", "", clean).strip(" ,;-–—|")
        left, right = _split_title_org(remainder)
        # "Бакалавър, СУ" и "СУ, бакалавър" носят едно и също — степента отпада,
        # институцията е другата страна.
        if degree and left and degree in left.lower():
            institution = right
        elif degree and right and degree in right.lower():
            institution = left
        else:
            institution = left

        entries.append(
            {
                "degree": degree,
                "institution": institution,
                "year": year_match[-1] if year_match else None,
                "raw": clean,
            }
        )

    return entries


def _parse_flat_list(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        line = BULLET_RE.sub("", line)
        for chunk in SKILL_SPLIT_RE.split(line):
            chunk = chunk.strip(" .\t")
            if chunk:
                items.append(chunk)
    return items


def _confidence(profile: ParsedProfile) -> float:
    """Дял на попълнените очаквани секции. Груб, но честен сигнал."""
    signals = (
        bool(profile.full_name),
        bool(profile.contact),
        bool(profile.skills),
        bool(profile.experience),
        bool(profile.education),
    )
    return round(sum(signals) / len(signals), 2)
