import os
import sqlite3
from datetime import datetime
from typing import List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "llm.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS llm_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        channel_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """
)
_conn.commit()


def log_message(
    guild_id: int | None,
    user_id: int | None,
    role: str,
    content: str,
    channel_id: int | None = None,
) -> None:
    if role not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")

    _conn.execute(
        """
        INSERT INTO llm_messages (guild_id, user_id, channel_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            guild_id,
            user_id,
            channel_id,
            role,
            content,
            datetime.utcnow().isoformat(),
        ),
    )
    _conn.commit()


def get_recent_conversation(
    guild_id: int | None,
    user_id: int | None,
    max_messages: int = 40,
    max_chars: int = 6000,
) -> List[Tuple[str, str]]:
    cur = _conn.execute(
        """
        SELECT role, content
        FROM llm_messages
        WHERE (guild_id IS ? OR guild_id = ?) AND (user_id IS ? OR user_id = ?)
        ORDER BY id DESC
        LIMIT ?
        """,
        (guild_id, guild_id, user_id, user_id, max_messages),
    )
    rows = list(cur.fetchall())

    selected: list[sqlite3.Row] = []
    total_chars = 0

    for row in rows:
        c = len(row["content"])
        if total_chars + c > max_chars:
            break
        selected.append(row)
        total_chars += c

    selected.reverse()

    return [(row["role"], row["content"]) for row in selected]
