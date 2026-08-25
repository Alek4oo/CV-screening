"""Парсерът върху текст — без OCR и без база."""

from app.parsing import parse_profile

ENGLISH_CV = """\
Ivan Petrov
ivan.petrov@example.com
+359 88 123 4567

Skills
Python, FastAPI, PostgreSQL, Docker, SQL, Git

Experience
2019 - 2023 Backend Developer, Acme Corp
Built REST services and CI pipelines.
2023 - present Senior Backend Engineer, Globex

Education
2015 - 2019 Bachelor, Sofia University

Languages
Bulgarian, English
"""

BULGARIAN_CV = """\
Мария Иванова
maria.ivanova@example.com
+359 87 765 4321

Умения
Python, Django, PostgreSQL, Docker, машинно обучение

Професионален опит
2018 - 2022 Софтуерен инженер, Технолинк
2022 - настоящем Водещ разработчик, Дейта Софт

Образование
2014 - 2018 Бакалавър, Технически университет

Езици
български, английски, немски
"""


class TestEnglishCv:
    def test_extracts_name_and_contact(self):
        profile = parse_profile(ENGLISH_CV)
        assert profile.full_name == "Ivan Petrov"
        assert profile.contact["email"] == "ivan.petrov@example.com"
        assert "359" in profile.contact["phone"]

    def test_extracts_skills(self):
        profile = parse_profile(ENGLISH_CV)
        for skill in ("python", "fastapi", "postgresql", "docker", "sql", "git"):
            assert skill in profile.skills

    def test_extracts_experience_with_dates(self):
        profile = parse_profile(ENGLISH_CV)
        assert len(profile.experience) == 2

        first = profile.experience[0]
        assert first["title"] == "Backend Developer"
        assert first["organization"] == "Acme Corp"
        assert first["start"] == "2019"
        assert first["end"] == "2023"
        assert first["current"] is False
        # Редът без дати е описание към предходната позиция, не нова позиция.
        assert "Built REST services and CI pipelines." in first["details"]

    def test_marks_current_position(self):
        profile = parse_profile(ENGLISH_CV)
        current = profile.experience[1]
        assert current["current"] is True
        assert current["end"] is None
        assert current["organization"] == "Globex"

    def test_extracts_education(self):
        profile = parse_profile(ENGLISH_CV)
        assert len(profile.education) == 1
        entry = profile.education[0]
        assert entry["degree"] == "bachelor"
        assert entry["institution"] == "Sofia University"
        assert entry["year"] == "2019"

    def test_confidence_is_full_when_all_sections_found(self):
        assert parse_profile(ENGLISH_CV).confidence == 1.0


class TestBulgarianCv:
    def test_extracts_name_and_contact(self):
        profile = parse_profile(BULGARIAN_CV)
        assert profile.full_name == "Мария Иванова"
        assert profile.contact["email"] == "maria.ivanova@example.com"

    def test_extracts_skills_including_bulgarian_terms(self):
        profile = parse_profile(BULGARIAN_CV)
        for skill in ("python", "django", "postgresql", "docker", "machine learning"):
            assert skill in profile.skills

    def test_extracts_experience(self):
        profile = parse_profile(BULGARIAN_CV)
        assert len(profile.experience) == 2
        assert profile.experience[0]["title"] == "Софтуерен инженер"
        assert profile.experience[0]["organization"] == "Технолинк"
        assert profile.experience[1]["current"] is True

    def test_extracts_education(self):
        profile = parse_profile(BULGARIAN_CV)
        entry = profile.education[0]
        assert entry["degree"] == "бакалавър"
        assert entry["institution"] == "Технически университет"

    def test_extracts_languages(self):
        profile = parse_profile(BULGARIAN_CV)
        assert "български" in profile.languages
        assert "английски" in profile.languages


class TestDegenerateInput:
    def test_empty_text_gives_empty_profile(self):
        profile = parse_profile("")
        assert profile.full_name is None
        assert profile.skills == []
        assert profile.experience == []
        assert profile.confidence == 0.0

    def test_prose_without_sections_still_finds_known_skills(self):
        profile = parse_profile("I have worked with Python and Kubernetes for years.")
        assert "python" in profile.skills
        assert "kubernetes" in profile.skills

    def test_word_boundaries_avoid_false_positives(self):
        # "Google" не бива да мине за "go", нито "jsx" за "js".
        profile = parse_profile("Worked at Google on jsx templates.")
        assert "go" not in profile.skills
        assert "javascript" not in profile.skills

    def test_to_dict_omits_name(self):
        # Името живее в колона на Candidate, не в JSONB полето.
        assert "full_name" not in parse_profile(ENGLISH_CV).to_dict()
