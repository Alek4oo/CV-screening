"""initial schema

Цялата схема наведнъж: кандидати, роли, версионирани правила, класирания,
решения, одитна следа и bias-одит. Чист старт — няма предишна миграция и няма
пренос от дев базата.

Postgres-specific, нарочно: JSONB за вариращите полета, native UUID ключове с
gen_random_uuid(), timestamptz навсякъде, ENUM типове за статусите и BEFORE
UPDATE/DELETE тригер, който прави audit_log наистина append-only.

Revision ID: 0001
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ENUM типовете се създават изрично, а в create_table се подават с
# create_type=False. Иначе Alembic се опитва да ги създаде втори път, ако
# някога втора таблица посегне към същия тип.
role_status = postgresql.ENUM("draft", "open", "closed", name="role_status")
ruleset_status = postgresql.ENUM("draft", "active", "archived", name="ruleset_status")
ranking_mode = postgresql.ENUM("masked", "unmasked", name="ranking_mode")
decision_outcome = postgresql.ENUM(
    "for_review", "advanced", "rejected", "on_hold", name="decision_outcome"
)
audit_action = postgresql.ENUM(
    "cv_ingested",
    "profile_parsed",
    "candidate_scored",
    "decision_recorded",
    "ruleset_created",
    "ruleset_activated",
    "ruleset_archived",
    "role_created",
    "role_updated",
    "bias_audit_run",
    name="audit_action",
)

ENUMS = (role_status, ruleset_status, ranking_mode, decision_outcome, audit_action)

# Append-only на ниво база. GRANT-ите се сменят с една заявка от кой да е
# суперпотребител; тригерът важи за всекиго, включително за собственика.
AUDIT_LOG_GUARD = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $guard$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP;
END;
$guard$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()
"""


def _uuid_pk() -> sa.Column:
    """UUID ключ, генериран от базата. gen_random_uuid() е в ядрото от PG 13."""
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUMS:
        enum_type.create(bind, checkfirst=False)

    # --- candidate -----------------------------------------------------
    op.create_table(
        "candidate",
        _uuid_pk(),
        sa.Column("external_ref", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        # Профилът и защитените признаци са отделни колони: скорингът чете само
        # profile и няма достъп до другото.
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "protected_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_index("ix_candidate_email", "candidate", ["email"])

    # --- role ----------------------------------------------------------
    op.create_table(
        "role",
        _uuid_pk(),
        sa.Column("external_ref", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="role_status", create_type=False),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_ref"),
    )

    # --- ruleset -------------------------------------------------------
    op.create_table(
        "ruleset",
        _uuid_pk(),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="ruleset_status", create_type=False),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        # Една версия, един ред. Правилата зад взето решение не се пренаписват.
        sa.UniqueConstraint("version"),
    )

    # --- ranking -------------------------------------------------------
    op.create_table(
        "ranking",
        _uuid_pk(),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ruleset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM(name="ranking_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        # RESTRICT: версия правила, с която има класирания, не се трие.
        sa.ForeignKeyConstraint(["ruleset_id"], ["ruleset.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "candidate_id",
            "role_id",
            "ruleset_id",
            "mode",
            name="uq_ranking_candidate_role_ruleset_mode",
        ),
        sa.CheckConstraint("score >= 0", name="ck_ranking_score_non_negative"),
    )
    op.create_index("ix_ranking_candidate_id", "ranking", ["candidate_id"])
    op.create_index("ix_ranking_role_id", "ranking", ["role_id"])
    op.create_index("ix_ranking_ruleset_id", "ranking", ["ruleset_id"])
    # Класацията за роля се чете точно така: филтър по роля, низходящ резултат.
    # С DESC в индекса първите N реда идват от него, без отделен sort.
    op.create_index("ix_ranking_role_score", "ranking", ["role_id", sa.text("score DESC")])

    # --- decision ------------------------------------------------------
    op.create_table(
        "decision",
        _uuid_pk(),
        sa.Column("ranking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ruleset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "outcome",
            postgresql.ENUM(name="decision_outcome", create_type=False),
            nullable=False,
        ),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ranking_id"], ["ranking.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ruleset_id"], ["ruleset.id"], ondelete="RESTRICT"),
        # Едно решение на класиране.
        sa.UniqueConstraint("ranking_id"),
        # Human-in-the-loop, наложен от базата: нищо не напуска for_review без
        # човек и час.
        sa.CheckConstraint(
            "outcome = 'for_review' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_decision_requires_human",
        ),
    )
    op.create_index("ix_decision_ruleset_id", "decision", ["ruleset_id"])

    # --- audit_log -----------------------------------------------------
    # Без updated_at: ред веднъж записан не се променя.
    op.create_table(
        "audit_log",
        _uuid_pk(),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column(
            "action",
            postgresql.ENUM(name="audit_action", create_type=False),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        # Логическа препратка, без FK: сочи различни таблици и преживява
        # триенето на това, което описва.
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ruleset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_in", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_out", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["ruleset_id"], ["ruleset.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_audit_log_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"]
    )
    op.create_index("ix_audit_log_ruleset_id", "audit_log", ["ruleset_id"])
    op.execute(AUDIT_LOG_GUARD)

    # --- bias_audit ----------------------------------------------------
    op.create_table(
        "bias_audit",
        _uuid_pk(),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ruleset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Метрики по групи и разликата между masked и unmasked класирането.
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ruleset_id"], ["ruleset.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_bias_audit_role_id", "bias_audit", ["role_id"])
    op.create_index("ix_bias_audit_ruleset_id", "bias_audit", ["ruleset_id"])
    op.create_index(
        "ix_bias_audit_role_created_at",
        "bias_audit",
        ["role_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")

    op.drop_table("bias_audit")
    op.drop_table("audit_log")
    op.drop_table("decision")
    op.drop_table("ranking")
    op.drop_table("ruleset")
    op.drop_table("role")
    op.drop_table("candidate")

    bind = op.get_bind()
    for enum_type in reversed(ENUMS):
        enum_type.drop(bind, checkfirst=False)
