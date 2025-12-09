from typing import List, Tuple, Dict

from .engine import get_connection

_conn = get_connection("levels.db")

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS user_levels (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        messages INTEGER NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
_conn.commit()


def _calculate_level(xp: int) -> int:
    """Simple level formula: 100 XP per level."""
    return xp // 100


def increment_activity(guild_id: int, user_id: int, xp_gain: int = 5) -> Tuple[int, int, int, bool]:
    """Increment message count and XP, return (messages, xp, level, leveled_up)."""
    cur = _conn.execute(
        "SELECT messages, xp, level FROM user_levels WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = cur.fetchone()

    if row is None:
        messages = 1
        xp = xp_gain
        old_level = 0
    else:
        messages = row["messages"] + 1
        xp = row["xp"] + xp_gain
        old_level = row["level"]

    level = _calculate_level(xp)
    leveled_up = level > old_level

    _conn.execute(
        """
        INSERT INTO user_levels (guild_id, user_id, messages, xp, level)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            messages=excluded.messages,
            xp=excluded.xp,
            level=excluded.level
        """,
        (guild_id, user_id, messages, xp, level),
    )
    _conn.commit()

    return messages, xp, level, leveled_up


def get_user_stats(guild_id: int, user_id: int) -> Dict[str, int]:
    cur = _conn.execute(
        "SELECT messages, xp, level FROM user_levels WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    row = cur.fetchone()
    if row is None:
        return {"messages": 0, "xp": 0, "level": 0}
    return {"messages": row["messages"], "xp": row["xp"], "level": row["level"]}


def get_top_users(guild_id: int, limit: int = 10) -> List[Dict]:
    cur = _conn.execute(
        """
        SELECT user_id, messages, xp, level
        FROM user_levels
        WHERE guild_id = ?
        ORDER BY messages DESC
        LIMIT ?
        """,
        (guild_id, limit),
    )
    rows = cur.fetchall()
    return [dict(row) for row in rows]
