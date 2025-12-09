from datetime import datetime
from typing import Optional, Dict

from .engine import get_connection

_conn = get_connection("audit.db")

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS message_log (
        message_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        channel_id INTEGER,
        author_id INTEGER,
        content TEXT,
        created_at TEXT NOT NULL
    )
    """
)

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS message_deletions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        guild_id INTEGER,
        channel_id INTEGER,
        author_id INTEGER,
        deleter_id INTEGER,
        content TEXT,
        created_at TEXT,
        deleted_at TEXT NOT NULL
    )
    """
)
_conn.commit()


def log_message(
    *,
    message_id: int,
    guild_id: int | None,
    channel_id: int | None,
    author_id: int | None,
    content: str,
    created_at: datetime | None = None,
) -> None:
    ts = (created_at or datetime.utcnow()).isoformat()
    _conn.execute(
        """
        INSERT INTO message_log (message_id, guild_id, channel_id, author_id, content, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            content=excluded.content,
            guild_id=excluded.guild_id,
            channel_id=excluded.channel_id,
            author_id=excluded.author_id
        """,
        (message_id, guild_id, channel_id, author_id, content, ts),
    )
    _conn.commit()


def get_message(message_id: int) -> Optional[Dict]:
    cur = _conn.execute(
        "SELECT guild_id, channel_id, author_id, content, created_at FROM message_log WHERE message_id=?",
        (message_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "guild_id": row["guild_id"],
        "channel_id": row["channel_id"],
        "author_id": row["author_id"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def record_deletion(
    *,
    message_id: int,
    guild_id: int | None,
    channel_id: int | None,
    author_id: int | None,
    deleter_id: int | None,
    content: str,
    created_at: str | None,
    deleted_at: datetime | None = None,
) -> None:
    ts = (deleted_at or datetime.utcnow()).isoformat()
    _conn.execute(
        """
        INSERT INTO message_deletions (
            message_id,
            guild_id,
            channel_id,
            author_id,
            deleter_id,
            content,
            created_at,
            deleted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, guild_id, channel_id, author_id, deleter_id, content, created_at, ts),
    )
    _conn.commit()
