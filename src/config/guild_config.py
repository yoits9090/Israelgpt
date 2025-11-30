"""Guild-specific configuration management."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Dict

import discord

from .settings import (
    GUILD_CONFIG_PATH,
    PRIMARY_GUILD_ID,
    AUTO_ROLE_ID,
    GEM_ROLE_ID,
    GEM_TRIGGER_PHRASE,
    AUDIT_LOG_CHANNEL_ID,
    DEFAULT_VOICE_CHANNEL_IDS,
    DEFAULT_PRIVATE_VOICE_LOBBY_ID,
)


@dataclass
class GuildSettings:
    """Per-guild configuration overrides."""

    auto_role_id: int | None = None
    gem_role_id: int | None = None
    gem_trigger_phrase: str = GEM_TRIGGER_PHRASE
    audit_log_channel_id: int | None = None
    voice_channel_ids: set[int] | None = None
    private_voice_lobby_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GuildSettings:
        voice_channels = data.get("voice_channel_ids") or []
        return cls(
            auto_role_id=int(data.get("auto_role_id")) if data.get("auto_role_id") else None,
            gem_role_id=int(data.get("gem_role_id")) if data.get("gem_role_id") else None,
            gem_trigger_phrase=data.get("gem_trigger_phrase", GEM_TRIGGER_PHRASE),
            audit_log_channel_id=int(data.get("audit_log_channel_id"))
            if data.get("audit_log_channel_id")
            else None,
            voice_channel_ids={int(v) for v in voice_channels} if voice_channels else None,
            private_voice_lobby_id=int(data.get("private_voice_lobby_id"))
            if data.get("private_voice_lobby_id")
            else None,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["voice_channel_ids"] = (
            list(self.voice_channel_ids) if self.voice_channel_ids is not None else None
        )
        return payload


# In-memory guild settings cache
guild_settings: Dict[int, GuildSettings] = {}


def load_guild_configs() -> None:
    """Load guild configurations from disk."""
    if not GUILD_CONFIG_PATH.exists():
        return

    try:
        data = json.loads(GUILD_CONFIG_PATH.read_text())
        for key, value in data.items():
            try:
                guild_settings[int(key)] = GuildSettings.from_dict(value)
            except Exception as e:
                print(f"Skipping invalid guild config for {key}: {e}")
    except Exception as e:
        print(f"Failed to load guild configs: {e}")


def save_guild_configs() -> None:
    """Persist guild configurations to disk."""
    try:
        serializable = {str(k): v.to_dict() for k, v in guild_settings.items()}
        GUILD_CONFIG_PATH.write_text(json.dumps(serializable, indent=2))
    except Exception as e:
        print(f"Failed to save guild configs: {e}")


def get_guild_settings(guild_id: int | None) -> GuildSettings:
    """Get merged settings for a guild (defaults + overrides)."""
    if guild_id is None:
        return GuildSettings()

    base_settings = GuildSettings()
    if PRIMARY_GUILD_ID == 0 or guild_id == PRIMARY_GUILD_ID:
        base_settings = GuildSettings(
            auto_role_id=AUTO_ROLE_ID or None,
            gem_role_id=GEM_ROLE_ID or None,
            gem_trigger_phrase=GEM_TRIGGER_PHRASE,
            audit_log_channel_id=AUDIT_LOG_CHANNEL_ID or None,
            voice_channel_ids=set(DEFAULT_VOICE_CHANNEL_IDS),
            private_voice_lobby_id=DEFAULT_PRIVATE_VOICE_LOBBY_ID or None,
        )

    overrides = guild_settings.get(guild_id)
    if overrides is None:
        return base_settings

    return GuildSettings(
        auto_role_id=overrides.auto_role_id
        if overrides.auto_role_id is not None
        else base_settings.auto_role_id,
        gem_role_id=overrides.gem_role_id
        if overrides.gem_role_id is not None
        else base_settings.gem_role_id,
        gem_trigger_phrase=overrides.gem_trigger_phrase or base_settings.gem_trigger_phrase,
        audit_log_channel_id=overrides.audit_log_channel_id
        if overrides.audit_log_channel_id is not None
        else base_settings.audit_log_channel_id,
        voice_channel_ids=overrides.voice_channel_ids
        if overrides.voice_channel_ids is not None
        else base_settings.voice_channel_ids,
        private_voice_lobby_id=overrides.private_voice_lobby_id
        if overrides.private_voice_lobby_id is not None
        else base_settings.private_voice_lobby_id,
    )


# Helper accessors
def get_auto_role_id(guild: discord.Guild | None) -> int | None:
    settings = get_guild_settings(guild.id if guild else None)
    return settings.auto_role_id


def get_gem_role_id(guild: discord.Guild | None) -> int | None:
    settings = get_guild_settings(guild.id if guild else None)
    return settings.gem_role_id


def get_gem_trigger_phrase(guild: discord.Guild | None) -> str:
    settings = get_guild_settings(guild.id if guild else None)
    return settings.gem_trigger_phrase or GEM_TRIGGER_PHRASE


def get_audit_log_channel_id(guild: discord.Guild | None) -> int | None:
    settings = get_guild_settings(guild.id if guild else None)
    return settings.audit_log_channel_id


def get_voice_channel_ids(guild: discord.Guild | None) -> set[int]:
    settings = get_guild_settings(guild.id if guild else None)
    if settings.voice_channel_ids is not None:
        return set(settings.voice_channel_ids)
    if guild and PRIMARY_GUILD_ID and guild.id == PRIMARY_GUILD_ID:
        return set(DEFAULT_VOICE_CHANNEL_IDS)
    return set()


def get_private_voice_lobby_id(guild: discord.Guild | None) -> int | None:
    settings = get_guild_settings(guild.id if guild else None)
    if settings.private_voice_lobby_id is not None:
        return settings.private_voice_lobby_id
    if guild and PRIMARY_GUILD_ID and guild.id == PRIMARY_GUILD_ID:
        return DEFAULT_PRIVATE_VOICE_LOBBY_ID
    return None


# Load configs on module import
load_guild_configs()
