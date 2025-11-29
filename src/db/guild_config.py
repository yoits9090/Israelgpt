import json
import os
import sqlite3
from typing import Dict, Optional, Set

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "guild_configs.db")
LEGACY_JSON_PATH = os.path.join(DATA_DIR, "guild_configs.json")

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


def _coerce_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _migrate_legacy_json() -> None:
    """Populate the SQLite store from the previous JSON config if present.

    Migration runs only when the database is empty to avoid overwriting
    new configuration and to preserve existing data. Any malformed entries
    are skipped so a bad record does not break startup.
    """

    try:
        row = _conn.execute("SELECT COUNT(*) AS count FROM guild_settings").fetchone()
        if row and int(row["count"]) > 0:
            return
    except Exception:
        # If we can't read the table count, fall through and try to migrate anyway.
        pass

    if not os.path.exists(LEGACY_JSON_PATH):
        return

    try:
        with open(LEGACY_JSON_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"Failed to read legacy guild config JSON: {e}")
        return

    if not isinstance(payload, dict):
        return

    for key, config in payload.items():
        try:
            guild_id = int(key)
        except (TypeError, ValueError):
            continue

        if not isinstance(config, dict):
            continue

        voice_channels_raw = config.get("voice_channel_ids")
        if isinstance(voice_channels_raw, (list, set, tuple)):
            voice_channels: Set[int] = set()
            for cid in voice_channels_raw:
                parsed = _coerce_int(cid)
                if parsed is not None:
                    voice_channels.add(parsed)
        else:
            voice_channels = None

        try:
            save_guild_settings(
                guild_id,
                auto_role_id=_coerce_int(config.get("auto_role_id")),
                gem_role_id=_coerce_int(config.get("gem_role_id")),
                gem_trigger_phrase=config.get("gem_trigger_phrase"),
                audit_log_channel_id=_coerce_int(config.get("audit_log_channel_id")),
                voice_channel_ids=voice_channels,
                private_voice_lobby_id=_coerce_int(config.get("private_voice_lobby_id")),
            )
        except Exception as e:
            print(f"Failed to migrate guild config for {guild_id}: {e}")


_migrate_legacy_json()


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
