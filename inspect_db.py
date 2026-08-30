"""Бърз преглед на базата: таблици, брой записи и примерни редове.

Пусни от корена на проекта:  python inspect_db.py
Използва DATABASE_URL от .env, ако го има; иначе — SQLite dev.db пътя.
Работи и за SQLite, и за PostgreSQL през SQLAlchemy (вече е зависимост).
"""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


def load_database_url() -> str:
    # 1) от средата
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # 2) от .env, ако съществува
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    # 3) fallback — питай потребителя
    return input("Постави DATABASE_URL (или SQLite път): ").strip()


def main() -> None:
    url = load_database_url()
    print(f"\n== База: {url}\n")

    engine = create_engine(url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if not tables:
        print("Няма таблици — базата е празна или още не са пуснати миграции.")
        return

    with engine.connect() as conn:
        for table in tables:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            print(f"── {table}: {count} записа")

            rows = conn.execute(text(f'SELECT * FROM "{table}" LIMIT 3')).mappings().all()
            for row in rows:
                pretty = {
                    k: (str(v)[:80] + "…" if isinstance(v, str) and len(str(v)) > 80 else v)
                    for k, v in dict(row).items()
                }
                print("   ", json.dumps(pretty, ensure_ascii=False, default=str))
            print()


if __name__ == "__main__":
    main()
