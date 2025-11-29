import os
import sqlite3
from typing import Dict, Optional, Set

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "guild_configs.db")

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id INTEGER PRIMARY KEY,
        auto_role_id INTEGER,
        gem_role_id INTEGER,
        gem_trigger_phrase TEXT,
        audit_log_channel_id INTEGER,
        voice_channel_ids TEXT,
        private_voice_lobby_id INTEGER
    )
    """
)
_conn.commit()


def _serialize_voice_channels(channels: Optional[Set[int]]) -> Optional[str]:
    if not channels:
        return None
    return ",".join(str(cid) for cid in sorted(channels))


def _parse_voice_channels(raw: Optional[str]) -> Optional[Set[int]]:
    if not raw:
        return None

    channel_ids: Set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            channel_ids.add(int(token))
        except ValueError:
            continue
    return channel_ids or None


def load_all_guild_settings() -> Dict[int, dict]:
    cur = _conn.execute(
        """
        SELECT guild_id, auto_role_id, gem_role_id, gem_trigger_phrase,
               audit_log_channel_id, voice_channel_ids, private_voice_lobby_id
        FROM guild_settings
        """
    )

    configs: Dict[int, dict] = {}
    for row in cur.fetchall():
        configs[row["guild_id"]] = {
            "auto_role_id": row["auto_role_id"],
            "gem_role_id": row["gem_role_id"],
            "gem_trigger_phrase": row["gem_trigger_phrase"],
            "audit_log_channel_id": row["audit_log_channel_id"],
            "voice_channel_ids": _parse_voice_channels(row["voice_channel_ids"]),
            "private_voice_lobby_id": row["private_voice_lobby_id"],
        }
    return configs


def save_guild_settings(
    guild_id: int,
    *,
    auto_role_id: Optional[int],
    gem_role_id: Optional[int],
    gem_trigger_phrase: Optional[str],
    audit_log_channel_id: Optional[int],
    voice_channel_ids: Optional[Set[int]],
    private_voice_lobby_id: Optional[int],
) -> None:
    _conn.execute(
        """
        INSERT INTO guild_settings (
            guild_id,
            auto_role_id,
            gem_role_id,
            gem_trigger_phrase,
            audit_log_channel_id,
            voice_channel_ids,
            private_voice_lobby_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            auto_role_id=excluded.auto_role_id,
            gem_role_id=excluded.gem_role_id,
            gem_trigger_phrase=excluded.gem_trigger_phrase,
            audit_log_channel_id=excluded.audit_log_channel_id,
            voice_channel_ids=excluded.voice_channel_ids,
            private_voice_lobby_id=excluded.private_voice_lobby_id
        """,
        (
            guild_id,
            auto_role_id,
            gem_role_id,
            gem_trigger_phrase,
            audit_log_channel_id,
            _serialize_voice_channels(voice_channel_ids),
            private_voice_lobby_id,
        ),
    )
    _conn.commit()
