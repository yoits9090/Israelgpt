"""Database engine helpers to smooth a future move from SQLite to Postgres."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from config import DATABASE_URL

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # psycopg is optional until Postgres is used
    psycopg = None
    dict_row = None


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ALLOW_EXPERIMENTAL_POSTGRES = os.getenv("ALLOW_EXPERIMENTAL_POSTGRES", "false").lower() == "true"


def is_postgres_url(url: Optional[str]) -> bool:
    if not url:
        return False
    return url.startswith("postgres://") or url.startswith("postgresql://")


def get_db_path(db_name: str) -> Path:
    """Return the on-disk path for a sqlite database."""
    return DATA_DIR / db_name


def using_postgres() -> bool:
    """True when a Postgres URL is configured."""
    return is_postgres_url(DATABASE_URL)


def get_connection(db_name: str):
    """Return a DB connection, choosing Postgres when DATABASE_URL is set."""
    if using_postgres():
        if not ALLOW_EXPERIMENTAL_POSTGRES:
            raise RuntimeError(
                "Postgres backend is planned but not fully migrated. "
                "Set ALLOW_EXPERIMENTAL_POSTGRES=true after updating SQL placeholders to Postgres format."
            )
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg is required for Postgres connections")
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    db_path = get_db_path(db_name)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
