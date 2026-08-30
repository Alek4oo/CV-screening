"""Миграциите и моделите описват една и съща схема.

Без Postgres подръка не може да се пусне `alembic upgrade head` срещу истинска
база, но може нещо почти толкова полезно: и двете страни се рендерират като
Postgres DDL и се сравняват. Разминаване значи, че някой е пипнал модел, без да
напише миграция — точно грешката, която иначе се вижда чак на деплой.

Сравнява се текстът на CREATE TABLE / CREATE INDEX. Редът на клаузите вътре в
CREATE TABLE няма значение — SQLAlchemy и Alembic ги подреждат различно, а това
е един и същ SQL. Съдържанието на клаузите има значение.
"""

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401  регистрира таблиците в Base.metadata
from app.core.db import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]

# alembic_version е на Alembic, не на домейна — в моделите го няма и не бива.
IGNORED_TABLES = {"alembic_version"}


def _normalise(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip().rstrip(";")


def _split_clauses(body: str) -> list[str]:
    """Реже по запетаите на нулево ниво — NUMERIC(7, 4) остава цяло."""
    clauses: list[str] = []
    depth = 0
    current = ""
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            clauses.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        clauses.append(current.strip())
    return clauses


def _canonical(statement: str) -> str:
    """CREATE TABLE с подредени клаузи; всичко останало — както си е."""
    match = re.match(r"(CREATE TABLE \w+) \((.*)\)$", statement, flags=re.IGNORECASE)
    if match is None:
        return statement
    head, body = match.groups()
    return f"{head} (" + ", ".join(sorted(_split_clauses(body))) + ")"


def _interesting(statement: str) -> bool:
    if not statement.upper().startswith(("CREATE TABLE", "CREATE INDEX")):
        return False
    return not any(f" {name} " in f" {statement} " for name in IGNORED_TABLES)


def _from_models() -> set[str]:
    dialect = postgresql.dialect()
    statements: set[str] = set()
    for table in Base.metadata.sorted_tables:
        statements.add(_canonical(_normalise(str(CreateTable(table).compile(dialect=dialect)))))
        for index in table.indexes:
            statements.add(_normalise(str(CreateIndex(index).compile(dialect=dialect))))
    return statements


def _from_migrations() -> set[str]:
    """`alembic upgrade head --sql` срещу Postgres диалект, без връзка."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://u:p@localhost/db")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)

    # Разделянето по ';' реже и тялото на plpgsql функцията, но парчетата от
    # нея не почват с CREATE TABLE/INDEX и отпадат във филтъра.
    parts = (_normalise(part) for part in buffer.getvalue().split(";"))
    return {_canonical(part) for part in parts if _interesting(part)}


@pytest.fixture(scope="module")
def rendered() -> tuple[set[str], set[str]]:
    return _from_models(), _from_migrations()


def test_migrations_create_every_table_the_models_declare(rendered):
    from_models, from_migrations = rendered
    missing = {s for s in from_models if s.upper().startswith("CREATE TABLE")} - from_migrations
    assert not missing, "Модел без миграция:\n" + "\n".join(sorted(missing))


def test_migrations_create_no_table_the_models_do_not_declare(rendered):
    from_models, from_migrations = rendered
    extra = {s for s in from_migrations if s.upper().startswith("CREATE TABLE")} - from_models
    assert not extra, "Миграция без модел:\n" + "\n".join(sorted(extra))


def test_indexes_match_on_both_sides(rendered):
    from_models, from_migrations = rendered
    models_indexes = {s for s in from_models if s.upper().startswith("CREATE INDEX")}
    migration_indexes = {s for s in from_migrations if s.upper().startswith("CREATE INDEX")}
    assert models_indexes == migration_indexes


def test_the_schema_is_postgres_native(rendered):
    """JSONB, native UUID и timestamptz — не text, не CHAR(32), не naive."""
    _, from_migrations = rendered
    tables = " ".join(s for s in from_migrations if s.upper().startswith("CREATE TABLE"))

    for column in (
        "profile JSONB",
        "protected_attributes JSONB",
        "requirements JSONB",
        "explanation JSONB",
        "definition JSONB",
        "payload_in JSONB",
        "payload_out JSONB",
        "report JSONB",
    ):
        assert column in tables, f"{column} не е JSONB в миграцията"

    assert "id UUID DEFAULT gen_random_uuid() NOT NULL" in tables
    assert "TIMESTAMP WITHOUT TIME ZONE" not in tables
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in tables


def test_audit_log_is_append_only_in_the_database(rendered):
    """Триггерът, не само уговорката в docstring-а."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://u:p@localhost/db")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)
    sql = buffer.getvalue()

    assert "BEFORE UPDATE OR DELETE ON audit_log" in sql
    # И обратното: audit_log няма updated_at, който да се обновява.
    assert "updated_at" not in sql.split("CREATE TABLE audit_log")[1].split(");")[0]
