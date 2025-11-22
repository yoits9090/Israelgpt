import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "users.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS user_activity (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        first_seen TEXT NOT NULL,
        last_message_at TEXT NOT NULL,
        total_messages INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
_conn.commit()


def record_message(guild_id: int, user_id: int, when: Optional[datetime] = None) -> None:
    if when is None:
        when = datetime.utcnow()
    ts = when.isoformat()

    _conn.execute(
        """
        INSERT INTO user_activity (guild_id, user_id, first_seen, last_message_at, total_messages)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            last_message_at=excluded.last_message_at,
            total_messages=user_activity.total_messages + 1
        """,
        (guild_id, user_id, ts, ts),
    )
    _conn.commit()


def get_user_activity(guild_id: int, user_id: int) -> Optional[Dict]:
    cur = _conn.execute(
        "SELECT first_seen, last_message_at, total_messages FROM user_activity WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "first_seen": row["first_seen"],
        "last_message_at": row["last_message_at"],
        "total_messages": row["total_messages"],
    }
