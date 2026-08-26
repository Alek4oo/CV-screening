"""Парсване на суров CV текст в структуриран профил."""

from app.parsing.profile_parser import ParsedProfile, parse_profile
from app.parsing.vocabulary import canonical_language, canonical_skill, degree_rank

__all__ = [
    "ParsedProfile",
    "canonical_language",
    "canonical_skill",
    "degree_rank",
    "parse_profile",
]
