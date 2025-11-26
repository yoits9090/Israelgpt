import os
import sqlite3
from datetime import datetime
from typing import Iterable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "voice_logs.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS voice_segments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        channel_id INTEGER,
        participants TEXT,
        transcript TEXT,
        note TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT NOT NULL
    )
    """
)
_conn.commit()


def record_segment(
    *,
    guild_id: int,
    channel_id: int,
    participants: Iterable[int] | None,
    transcript: str | None,
    note: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> None:
    started_ts = (started_at or datetime.utcnow()).isoformat()
    ended_ts = (ended_at or datetime.utcnow()).isoformat()
    participant_text = ",".join(str(p) for p in (participants or []))

    _conn.execute(
        """
        INSERT INTO voice_segments (
            guild_id,
            channel_id,
            participants,
            transcript,
            note,
            started_at,
            ended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, channel_id, participant_text, transcript or "", note or "", started_ts, ended_ts),
    )
    _conn.commit()
