from datetime import datetime
from typing import List, Tuple

from .engine import get_connection

_conn = get_connection("llm.db")

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
    channel_id: int | None = None,
    max_messages: int = 40,
    max_chars: int = 6000,
) -> List[Tuple[str, str]]:
    channel_filter = ""
    params: list[object] = [guild_id, guild_id, user_id, user_id]
    if channel_id is not None:
        channel_filter = " AND channel_id = ?"
        params.append(channel_id)
    params.append(max_messages)

    cur = _conn.execute(
        f"""
        SELECT role, content
        FROM llm_messages
        WHERE (guild_id IS ? OR guild_id = ?) AND (user_id IS ? OR user_id = ?)
        {channel_filter}
        ORDER BY id DESC
        LIMIT ?
        """,
        params,
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
