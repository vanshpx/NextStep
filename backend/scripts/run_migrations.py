#!/usr/bin/env python
"""
scripts/run_migrations.py
--------------------------
Applies docs/database/05-implementation.sql to the configured Postgres database.

Usage:
    python scripts/run_migrations.py [--dry-run]

Exit codes:
    0 — migrations applied successfully (or dry-run completed)
    1 — connection failed or SQL error

Environment variables (all have defaults — override as needed):
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    (same vars used by db/connection.py)

Notes:
    - The script wraps the DDL in a single transaction so all-or-nothing semantics apply.
    - Re-running is idempotent: all CREATE TABLE / CREATE INDEX statements use
      IF NOT EXISTS, and CREATE EXTENSION uses IF NOT EXISTS.
    - Indexes that are implicitly created by UNIQUE constraints are not duplicated.
"""

from __future__ import annotations

import argparse
import os
import sys
import pathlib

# Add the backend directory to sys.path so that config is importable
_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

import psycopg2
import config


_SQL_FILE = _BACKEND_DIR / "docs" / "database" / "05-implementation.sql"


def _read_sql() -> str:
    if not _SQL_FILE.exists():
        raise FileNotFoundError(f"SQL file not found: {_SQL_FILE}")
    return _SQL_FILE.read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    """
    Remove block comments (/* ... */) which contain non-executable documentation
    in the schema file. psycopg2 executes through psycopg2.extras but the plain
    cursor.execute() chokes on the multi-statement blocks — we split and skip blanks.
    """
    import re
    # Remove /* ... */ block comments
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    # Remove -- inline comments
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def _split_statements(sql: str) -> list[str]:
    """Split on semicolons; return non-empty statements."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def run(dry_run: bool = False) -> None:
    raw_sql = _read_sql()
    cleaned = _strip_comments(raw_sql)
    statements = _split_statements(cleaned)

    print(f"[migrations] SQL file   : {_SQL_FILE}")
    print(f"[migrations] Statements : {len(statements)}")
    print(f"[migrations] Target DB  : {config.POSTGRES_DB} @ "
          f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}")

    if dry_run:
        print("[migrations] DRY-RUN — no changes applied.")
        for i, stmt in enumerate(statements, 1):
            preview = stmt[:80].replace("\n", " ")
            print(f"  [{i:03d}] {preview}...")
        return

    conn = psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                try:
                    cur.execute(stmt)
                except psycopg2.Error as exc:
                    print(f"  [✗] Statement {i} failed: {exc.pgerror or exc}")
                    raise
                else:
                    preview = stmt[:60].replace("\n", " ")
                    print(f"  [✓] {preview}")
        conn.commit()
        print(f"[migrations] Done — {len(statements)} statements applied.")
    except Exception:
        conn.rollback()
        print("[migrations] ROLLED BACK due to error.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Postgres schema migrations.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print statements without executing them.",
    )
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as exc:
        print(f"[migrations] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
