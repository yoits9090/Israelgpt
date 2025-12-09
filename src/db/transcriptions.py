"""Voice transcription database storage."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from .engine import get_connection, using_postgres

_conn = get_connection("transcriptions.db")
_cursor = _conn.cursor()
_IS_POSTGRES = using_postgres()

# Create tables
_ID_COLUMN = "id SERIAL PRIMARY KEY" if _IS_POSTGRES else "id INTEGER PRIMARY KEY AUTOINCREMENT"

_cursor.execute(
    f"""
CREATE TABLE IF NOT EXISTS transcriptions (
    {_ID_COLUMN},
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    content TEXT NOT NULL,
    duration_secs REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""
)

_cursor.execute(
    f"""
CREATE TABLE IF NOT EXISTS voice_sessions (
    {_ID_COLUMN},
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    total_transcriptions INTEGER DEFAULT 0
)
"""
)

_cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_guild ON transcriptions(guild_id)")
_cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_user ON transcriptions(user_id)")
_cursor.execute("CREATE INDEX IF NOT EXISTS idx_transcriptions_created ON transcriptions(created_at)")
_conn.commit()


@dataclass
class Transcription:
    id: int
    guild_id: int
    channel_id: int
    user_id: int
    username: Optional[str]
    content: str
    duration_secs: Optional[float]
    created_at: datetime


def save_transcription(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
    username: Optional[str] = None,
    duration_secs: Optional[float] = None,
) -> int:
    """Save a voice transcription to the database. Returns the transcription ID."""
    _cursor.execute(
        """
        INSERT INTO transcriptions (guild_id, channel_id, user_id, username, content, duration_secs)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (guild_id, channel_id, user_id, username, content, duration_secs),
    )
    _conn.commit()
    return _cursor.lastrowid


def get_transcriptions(
    guild_id: int,
    channel_id: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = 50,
) -> List[Transcription]:
    """Get transcriptions with optional filters."""
    query = "SELECT * FROM transcriptions WHERE guild_id = ?"
    params = [guild_id]

    if channel_id:
        query += " AND channel_id = ?"
        params.append(channel_id)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    _cursor.execute(query, params)
    rows = _cursor.fetchall()

    return [
        Transcription(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            user_id=row["user_id"],
            username=row["username"],
            content=row["content"],
            duration_secs=row["duration_secs"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )
        for row in rows
    ]


def start_voice_session(guild_id: int, channel_id: int) -> int:
    """Start a new voice recording session. Returns session ID."""
    _cursor.execute(
        "INSERT INTO voice_sessions (guild_id, channel_id) VALUES (?, ?)",
        (guild_id, channel_id),
    )
    _conn.commit()
    return _cursor.lastrowid


def end_voice_session(session_id: int, total_transcriptions: int = 0):
    """End a voice recording session."""
    _cursor.execute(
        "UPDATE voice_sessions SET ended_at = CURRENT_TIMESTAMP, total_transcriptions = ? WHERE id = ?",
        (total_transcriptions, session_id),
    )
    _conn.commit()
