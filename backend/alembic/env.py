"""Alembic среда.

Две неща стават тук и двете са нарочни:

  * `target_metadata` е `Base.metadata` след импорт на `app.models` — целият
    пакет, не отделни модули. Пропуснат модел значи таблица, която autogenerate
    не вижда в моделите и предлага да изтрие от базата.
  * Връзката се чете от DATABASE_URL, не от alembic.ini. Същата променлива
    ползва и приложението (`app.core.config`), така че миграциите не могат да
    се озоват на друга база от тази, срещу която върви кодът. Изключение прави
    само `sqlalchemy.url`, зададен програмно на Config обекта — така тестовете
    насочват миграциите към своята база, без да пипат средата.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.db import Base

# Импортът регистрира всички таблици в Base.metadata. Без него autogenerate
# вижда празна схема и генерира миграция, която трие всичко.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Изрично зададен URL → DATABASE_URL → стойността от конфигурацията."""
    return (
        config.get_main_option("sqlalchemy.url")
        or os.getenv("DATABASE_URL")
        or settings.database_url
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — рендерира SQL, без да пипа база."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Обичайният път: свързва се и прилага миграциите."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Без тези две autogenerate мълчи за сменен тип на колона или
            # сменен server_default — точно промените, които се пропускат.
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
