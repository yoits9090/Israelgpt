import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import yt_dlp
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re
from dataclasses import dataclass, asdict
from typing import Dict, Optional
import random

from tickets import setup_ticket_system, register_ticket_view
from db.levels import increment_activity, get_user_stats, get_top_users
from db.users import record_message
from db.audit import log_message as log_audit_message, get_message as get_logged_message, record_deletion
from db.guild_config import load_all_guild_settings, save_guild_settings
from llm_client import generate_israeli_reply, classify_message_safety

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
AUTO_ROLE_ID = int(os.getenv('AUTO_ROLE_ID', '0'))  # Unpolished role
GEM_ROLE_ID = 1441889921102118963  # Gem role granted at 150 messages
GEM_TRIGGER_PHRASE = "/wearegems"
AUDIT_LOG_CHANNEL_ID = 1442833351307300874
DEFAULT_VOICE_CHANNEL_IDS = {1441899961225576458, 1441877144413278228}
DEFAULT_PRIVATE_VOICE_LOBBY_ID = 1444420249264066591
VOICE_TRANSCRIBE_INTERVAL = 5
PRIMARY_GUILD_ID = int(os.getenv("PRIMARY_GUILD_ID", "0"))

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Bot setup
bot = commands.Bot(command_prefix=',', intents=intents)
bot.remove_command("help")

# Setup external systems (tickets, etc.)
setup_ticket_system(bot)

# In-memory tracking only for anti-nuke
message_timestamps = defaultdict(list)  # Track message timestamps for anti-nuke
voice_monitors: Dict[int, "VoiceMonitor"] = {}
private_voice_by_owner: Dict[int, "PrivateVoiceSession"] = {}
private_voice_by_channel: Dict[int, int] = {}
guild_settings: Dict[int, "GuildSettings"] = {}
chat_activity: Dict[int, deque[tuple[datetime, int]]] = defaultdict(deque)
chat_activity_cooldowns: Dict[int, datetime] = {}


def _truncate(text: str, limit: int = 1700) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class VoiceMonitor:
    def __init__(self, channel: discord.VoiceChannel):
        self.channel = channel
        self.voice_client: Optional[discord.VoiceClient] = None
        self.task: Optional[asyncio.Task] = None
        self._running = False
        self._warned_unavailable = False

    async def ensure_running(self):
        await self._connect()
        if not self._running:
            self._running = True
            self.task = bot.loop.create_task(self._transcription_loop())

    async def _connect(self):
        guild = self.channel.guild
        if guild is None:
            return

        client = guild.voice_client
        if client is None:
            try:
                client = await self.channel.connect()
            except Exception as e:
                print(f"Failed to join voice channel {self.channel.id}: {e}")
                return
        elif client.channel != self.channel:
            try:
                await client.move_to(self.channel)
            except Exception as e:
                print(f"Failed to move to monitored channel {self.channel.id}: {e}")
                return

        self.voice_client = client

    async def _capture_audio_chunk(self) -> Optional[bytes]:
        if self.voice_client is None:
            return None

        # discord.py (2.6.x) does not provide voice receive primitives; store participant snapshots.
        if not self._warned_unavailable:
            print(
                "Voice receive is unavailable in discord.py; capturing participant snapshot without audio."
            )
            self._warned_unavailable = True
        return None

    async def _transcription_loop(self):
        while self._running:
            start_time = datetime.utcnow()
            participants = [m.id for m in self.channel.members if not m.bot]

            transcript: Optional[str] = None
            note: Optional[str] = None

            audio_bytes = await self._capture_audio_chunk()
            if audio_bytes:
                transcript = await transcribe_audio_bytes(audio_bytes)
                if not transcript:
                    note = "Transcription returned empty text."
            else:
                note = "Audio capture not available; stored participant snapshot only."

            try:
                record_segment(
                    guild_id=self.channel.guild.id if self.channel.guild else 0,
                    channel_id=self.channel.id,
                    participants=participants,
                    transcript=transcript,
                    note=note,
                    started_at=start_time,
                    ended_at=datetime.utcnow(),
                )
            except Exception as e:
                print(f"Failed to write voice segment: {e}")

            await asyncio.sleep(VOICE_TRANSCRIBE_INTERVAL)

    async def stop(self):
        self._running = False
        if self.task:
            self.task.cancel()
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.is_playing():
                return
            try:
                await self.voice_client.disconnect()
            except Exception as e:
                print(f"Failed to disconnect monitor client: {e}")


async def _ensure_voice_monitor(channel: discord.VoiceChannel):
    monitor = voice_monitors.get(channel.id)
    if monitor is None:
        monitor = VoiceMonitor(channel)
        voice_monitors[channel.id] = monitor
    else:
        monitor.channel = channel

    await monitor.ensure_running()


async def _stop_monitor_if_empty(channel: discord.VoiceChannel):
    monitor = voice_monitors.get(channel.id)
    if monitor is None:
        return

    non_bot_members = [m for m in channel.members if not m.bot]
    if non_bot_members:
        return

    await monitor.stop()
    voice_monitors.pop(channel.id, None)


async def _find_message_deleter(message: discord.Message) -> discord.abc.User | None:
    if message.guild is None or message.guild.me is None:
        return None

    me_permissions = message.guild.me.guild_permissions
    if not me_permissions.view_audit_log:
        return None

    try:
        async for entry in message.guild.audit_logs(
            limit=5, action=discord.AuditLogAction.message_delete
        ):
            if entry.target.id != getattr(message.author, "id", None):
                continue

            extra_channel = getattr(entry.extra, "channel", None)
            if extra_channel is not None and extra_channel.id != message.channel.id:
                continue

            if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                continue

            return entry.user
    except Exception as e:
        print(f"Failed to inspect audit log for deletions: {e}")

    return None


@dataclass
class PrivateVoiceSession:
    owner_id: int
    channel_id: int
    role_id: int


@dataclass
class GuildSettings:
    auto_role_id: int | None = None
    gem_role_id: int | None = None
    gem_trigger_phrase: str = GEM_TRIGGER_PHRASE
    audit_log_channel_id: int | None = None
    voice_channel_ids: set[int] | None = None
    private_voice_lobby_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GuildSettings":
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


def load_guild_configs():
    try:
        stored_configs = load_all_guild_settings()
    except Exception as e:
        print(f"Failed to load guild configs: {e}")
        return

    for key, value in stored_configs.items():
        try:
            guild_settings[int(key)] = GuildSettings.from_dict(value)
        except Exception as e:
            print(f"Skipping invalid guild config for {key}: {e}")


def save_guild_config(guild_id: int, settings: "GuildSettings"):
    try:
        save_guild_settings(
            guild_id,
            auto_role_id=settings.auto_role_id,
            gem_role_id=settings.gem_role_id,
            gem_trigger_phrase=settings.gem_trigger_phrase,
            audit_log_channel_id=settings.audit_log_channel_id,
            voice_channel_ids=settings.voice_channel_ids,
            private_voice_lobby_id=settings.private_voice_lobby_id,
        )
    except Exception as e:
        print(f"Failed to persist guild settings for {guild_id}: {e}")


def get_guild_settings(guild_id: int | None) -> GuildSettings:
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


load_guild_configs()


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


def _register_private_voice_session(session: PrivateVoiceSession):
    private_voice_by_owner[session.owner_id] = session
    private_voice_by_channel[session.channel_id] = session.owner_id


def _unregister_private_voice_session(owner_id: int):
    session = private_voice_by_owner.pop(owner_id, None)
    if session:
        private_voice_by_channel.pop(session.channel_id, None)


def _get_private_session_by_channel(channel_id: int) -> Optional[PrivateVoiceSession]:
    owner_id = private_voice_by_channel.get(channel_id)
    if owner_id is None:
        return None
    return private_voice_by_owner.get(owner_id)


async def _ensure_private_voice(member: discord.Member, lobby_channel: discord.VoiceChannel):
    if member.guild is None:
        return

    existing_session = private_voice_by_owner.get(member.id)
    guild = member.guild

    if existing_session:
        channel = guild.get_channel(existing_session.channel_id)
        role = guild.get_role(existing_session.role_id)
        if channel and role:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="Restoring private voice owner role")
                except Exception as e:
                    print(f"Failed to restore VC owner role: {e}")
            try:
                await member.move_to(channel)
            except Exception as e:
                print(f"Failed to move member to existing private VC: {e}")
            return
        else:
            _unregister_private_voice_session(member.id)

    parent_category = lobby_channel.category
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
    }

    try:
        role = await guild.create_role(
            name=f"{member.display_name}'s VC",
            mentionable=False,
            reason="Creating private voice channel owner role",
        )
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            stream=True,
            use_voice_activation=True,
        )

        bot_member = guild.me
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                move_members=True,
                manage_channels=True,
            )

        channel = await guild.create_voice_channel(
            name=f"{member.display_name}'s Room",
            category=parent_category,
            overwrites=overwrites,
            reason="Creating private voice channel",
        )

        session = PrivateVoiceSession(
            owner_id=member.id,
            channel_id=channel.id,
            role_id=role.id,
        )
        _register_private_voice_session(session)

        await member.add_roles(role, reason="Granting private voice ownership")
        await member.move_to(channel)
    except Exception as e:
        print(f"Failed to create private voice channel: {e}")


async def _cleanup_private_voice(channel: discord.VoiceChannel):
    session = _get_private_session_by_channel(channel.id)
    if session is None:
        return

    if any(not m.bot for m in channel.members):
        return

    guild = channel.guild
    role = guild.get_role(session.role_id) if guild else None

    try:
        await channel.delete(reason="Removing empty private voice channel")
    except Exception as e:
        print(f"Failed to delete private voice channel: {e}")

    if role:
        try:
            await role.delete(reason="Removing private voice owner role")
        except Exception as e:
            print(f"Failed to delete private voice role: {e}")

    _unregister_private_voice_session(session.owner_id)


def _get_owner_role(guild: discord.Guild, owner_id: int) -> Optional[discord.Role]:
    session = private_voice_by_owner.get(owner_id)
    if session is None:
        return None
    role = guild.get_role(session.role_id)
    if role is None:
        _unregister_private_voice_session(owner_id)
        return None
    return role


def _record_chat_activity(message: discord.Message) -> bool:
    if message.guild is None:
        return False

    if message.author.bot:
        return False

    if message.content and message.content.startswith(str(bot.command_prefix)):
        return False

    now = datetime.utcnow()
    window = chat_activity[message.guild.id]
    window.append((now, message.author.id))

    while window and (now - window[0][0]) > timedelta(seconds=30):
        window.popleft()

    active_window = [(ts, uid) for ts, uid in window if (now - ts) <= timedelta(seconds=20)]
    unique_users = {uid for _, uid in active_window}

    if len(active_window) < 6 or len(unique_users) < 3:
        return False

    last_trigger = chat_activity_cooldowns.get(message.guild.id)
    if last_trigger and (now - last_trigger) < timedelta(seconds=45):
        return False

    if random.random() < 0.35:
        chat_activity_cooldowns[message.guild.id] = now
        return True

    return False


async def _send_flagged_message_report(
    message: discord.Message, verdict: dict[str, object]
) -> None:
    if message.guild is None:
        return

    channel_id = get_audit_log_channel_id(message.guild)
    channel = message.guild.get_channel(channel_id) if channel_id else None
    if channel is None:
        return

    categories = verdict.get("categories") or []
    details = verdict.get("details") or "Flagged by safety model."
    verdict_label = str(verdict.get("verdict", "unknown")).title()

    description = (
        f"Message flagged by Llama Guard in {message.channel.mention}.\n"
        f"Author: {message.author.mention} ({message.author.id})\n"
        f"Verdict: {verdict_label}\n"
        f"Categories: {', '.join(categories) if categories else 'n/a'}\n"
        f"Details: {details}"
    )

    content = message.content or "[no text content]"
    embed = discord.Embed(
        description=description,
        color=0xE74C3C,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="Message Content",
        value=f"```{_truncate(content, 900)}```",
        inline=False,
    )
    embed.set_footer(text=f"Message ID: {message.id}")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send flagged message report: {e}")


async def _scan_message_safety(message: discord.Message) -> None:
    if not message.content:
        return

    verdict = await classify_message_safety(message.content)
    if verdict is None:
        return

    if str(verdict.get("verdict", "safe")).lower() != "safe":
        await _send_flagged_message_report(message, verdict)



async def send_audit_log(
    guild: discord.Guild | None, description: str, *, user: discord.abc.User | None = None
) -> None:
    if guild is None:
        return

    channel_id = get_audit_log_channel_id(guild)
    channel = guild.get_channel(channel_id) if channel_id else None
    if channel is None:
        return

    embed = discord.Embed(
        description=description,
        color=0x2F3136,
        timestamp=datetime.utcnow(),
    )

    if user is not None:
        avatar = getattr(user, "display_avatar", None)
        embed.set_author(
            name=f"{user} ({user.id})",
            icon_url=avatar.url if avatar else None,
        )

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to write to audit log channel: {e}")


async def grant_gem_role(member: discord.Member, *, trigger: str) -> None:
    if member.guild is None:
        return

    gem_role_id = get_gem_role_id(member.guild)
    gem_role = member.guild.get_role(gem_role_id) if gem_role_id else None
    if gem_role is None or gem_role in member.roles:
        return

    try:
        await member.add_roles(gem_role, reason=f"Gem role via {trigger}")
    except Exception as e:
        print(f"Failed to assign gem role: {e}")
        return

    await send_audit_log(
        member.guild,
        f"{member.mention} granted **{gem_role.name}** ({gem_role.id}) for {trigger}.",
        user=member,
    )


def _text_contains_gem_phrase(text: str | None, phrase: str) -> bool:
    return text is not None and phrase in text.lower()


async def mentions_gem_phrase(member: discord.Member) -> bool:
    # Check rich presence and custom status
    trigger_phrase = get_gem_trigger_phrase(member.guild).lower()
    for activity in member.activities or []:
        if isinstance(activity, discord.CustomActivity):
            if _text_contains_gem_phrase(
                str(activity.name or activity.state or ""), trigger_phrase
            ):
                return True
        elif _text_contains_gem_phrase(getattr(activity, "name", None), trigger_phrase):
            return True

    # Check profile/about me when available
    profile_method = getattr(member, "profile", None)
    if callable(profile_method):
        try:
            profile = await profile_method()
            if _text_contains_gem_phrase(getattr(profile, "bio", None), trigger_phrase):
                return True
        except Exception as e:
            print(f"Failed to check member profile for gem phrase: {e}")

    return False


def parse_duration(duration: str) -> timedelta | None:
    match = re.match(r"^(\d+)([smhdw])$", duration)
    if not match:
        return None

    value, unit = match.groups()
    value = int(value)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 60 * 60 * 24,
        "w": 60 * 60 * 24 * 7,
    }

    seconds = value * multipliers[unit]
    return timedelta(seconds=seconds)


class HelpPaginator(discord.ui.View):
    def __init__(self, ctx, pages: list[discord.Embed]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the person who asked for help can use these buttons, chaver!",
                ephemeral=True,
            )
            return False
        return True

    def _update_footer(self) -> discord.Embed:
        embed = self.pages[self.current_page]
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{len(self.pages)} • Use the buttons below to navigate"
        )
        return embed

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self._update_footer(), view=self)

    @discord.ui.button(label="⏮️ Back", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = (self.current_page - 1) % len(self.pages)
        await self.update_message(interaction)

    @discord.ui.button(label="🏠 Overview", style=discord.ButtonStyle.primary)
    async def home_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="Next ⏭️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_page = (self.current_page + 1) % len(self.pages)
        await self.update_message(interaction)


def build_help_pages(prefix: str) -> list[discord.Embed]:

    overview = discord.Embed(
        title="IsraelGPT Command Guide",
        description=(
            "Interactive guide for every command. Navigate with the buttons to see detailed "
            "usage, permissions, and examples."
        ),
        color=0x3498DB,
    )
    overview.add_field(
        name="How to use",
        value=(
            f"Use `{prefix}command` with the arguments shown on each page. "
            "Only the user who requested this help can flip through the pages."
        ),
        inline=False,
    )
    overview.add_field(
        name="Need this guide again?",
        value=f"Type `{prefix}help` anytime to reopen the navigator.",
        inline=False,
    )
    overview.add_field(
        name="Navigation tips",
        value="⏮️ Back • 🏠 Overview • Next ⏭️",
        inline=False,
    )

    moderation = discord.Embed(title="Moderation & Safety", color=0xE74C3C)
    moderation.add_field(
        name=f"{prefix}ban <user> [reason]",
        value="Ban a member with an optional reason. Requires Ban Members permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}kick <user> [reason]",
        value="Kick a member from the server. Requires Kick Members permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}mute <user> <duration>",
        value=(
            "Timeout a user for a duration like `10m`, `2h`, or `1d`. You can also reply "
            "to a user's message instead of mentioning them."
        ),
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}clear <amount>",
        value="Bulk delete the given number of messages in the current channel.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}role <user> <role>",
        value="Toggle a role for a user by name or ID. Requires Manage Roles permission.",
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}slowmode <seconds>",
        value=(
            "Set channel slowmode in seconds (use 0 to disable). Great for calming a chat "
            "without full lockdown. Requires Manage Channels permission."
        ),
        inline=False,
    )
    moderation.add_field(
        name=f"{prefix}guildconfig", 
        value=(
            "Show or adjust server-specific defaults (auto roles, audit log channel, voice lobby) "
            "so you can run IsraelGPT beyond the primary guild. Subcommands: `set`, `clear`."
        ),
        inline=False,
    )

    community = discord.Embed(title="Community & Utility", color=0x2ECC71)
    community.add_field(
        name=f"{prefix}leaderboard",
        value="Show the top 10 chatters by messages and level.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}rank [user]",
        value="See your own or another member's message, XP, and level stats.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}info",
        value="Server overview including member count and region.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}avatar [user] / {prefix}banner [user]",
        value="Display avatars or banners for yourself or a mentioned user.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}servericon / {prefix}serverbanner",
        value="Preview the guild's icon or banner if available.",
        inline=False,
    )
    community.add_field(
        name=f"{prefix}poll <question> | <option 1> | <option 2> ...",
        value=(
            "Create a quick reaction poll with up to 10 options. Separate options using `|` "
            "and I'll add number emojis automatically."
        ),
        inline=False,
    )
    community.add_field(
        name=f"{prefix}remind <duration> <message>",
        value=(
            "Set a reminder like `,remind 15m Drink water`. I'll ping you in this channel "
            "when time's up."
        ),
        inline=False,
    )
    community.add_field(
        name=f"{prefix}botresources",
        value=(
            "Quick links and command highlights for BleedBot and Greed so members can explore "
            "those ecosystems from any server."
        ),
        inline=False,
    )

    music = discord.Embed(title="Music & Media", color=0x9B59B6)
    music.add_field(
        name=f"{prefix}play <url/search>",
        value="Join your voice channel and start playing audio from YouTube.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}pause / {prefix}resume",
        value="Pause or resume the current track.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}skip",
        value="Skip the current track and move to the next queued song if available.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}stop",
        value="Stop playback and clear the queue for this server.",
        inline=False,
    )
    music.add_field(
        name=f"{prefix}leave",
        value="Disconnect the bot from voice and clear the queue.",
        inline=False,
    )

    ai = discord.Embed(title="AI & Tickets", color=0xF1C40F)
    ai.add_field(
        name="Mentioning IsraelGPT",
        value=(
            "Mention the bot to get a friendly AI reply tailored to your server. "
            "Great for quick answers or conversation starters."
        ),
        inline=False,
    )
    ai.add_field(
        name="Ticket system",
        value=(
            "Use the configured ticket panel to reach staff. Replies are routed through the "
            "ticket tools once you set them up (see server setup)."
        ),
        inline=False,
    )

    return [overview, moderation, community, music, ai]

@bot.event
async def on_ready():
    print(f'{bot.user} has arrived! Shalom everyone!')
    await bot.change_presence(activity=discord.Game(name="Backgammon (Shesh Besh)"))
    register_ticket_view(bot)


@bot.command(name='help')
async def help_command(ctx):
    pages = build_help_pages(ctx.clean_prefix)
    view = HelpPaginator(ctx, pages)
    await ctx.send(embed=view._update_footer(), view=view)


@bot.group(name="guildconfig", invoke_without_command=True)
async def guildconfig(ctx):
    if ctx.guild is None:
        return
    settings = get_guild_settings(ctx.guild.id)

    resolved_voice = get_voice_channel_ids(ctx.guild)
    resolved_lobby = get_private_voice_lobby_id(ctx.guild)

    embed = discord.Embed(
        title=f"Guild configuration for {ctx.guild.name}", color=0x1ABC9C
    )
    embed.add_field(
        name="Auto role",
        value=str(settings.auto_role_id or "Not set (inherit default)"),
        inline=False,
    )
    embed.add_field(
        name="Gem role",
        value=str(settings.gem_role_id or "Not set (inherit default)"),
        inline=False,
    )
    embed.add_field(
        name="Gem trigger phrase",
        value=settings.gem_trigger_phrase or "Not set",
        inline=False,
    )
    embed.add_field(
        name="Audit log channel",
        value=str(settings.audit_log_channel_id or "Not set (inherit default)"),
        inline=False,
    )
    embed.add_field(
        name="Voice monitor channels",
        value=", ".join(str(cid) for cid in sorted(resolved_voice))
        if resolved_voice
        else "None configured",
        inline=False,
    )
    embed.add_field(
        name="Private VC lobby",
        value=str(resolved_lobby or "None configured"),
        inline=False,
    )

    await ctx.send(embed=embed)


@guildconfig.command(name="set")
async def guildconfig_set(ctx, key: str | None = None, *, value: str | None = None):
    if ctx.guild is None:
        return

    if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
        await ctx.send("You need Manage Server permissions to change this, chaver.")
        return

    if key is None or value is None:
        await ctx.send(
            "Usage: ,guildconfig set <auto_role|gem_role|audit_channel|voice_channels|lobby_channel|gem_phrase> <value>"
        )
        return

    key = key.lower()
    settings = guild_settings.setdefault(ctx.guild.id, GuildSettings())

    try:
        if key in {"auto_role", "gem_role"}:
            role = await commands.RoleConverter().convert(ctx, value)
            if key == "auto_role":
                settings.auto_role_id = role.id
            else:
                settings.gem_role_id = role.id
            await ctx.send(f"Updated {key.replace('_', ' ')} to {role.mention} ({role.id}).")
        elif key == "audit_channel":
            channel = await commands.TextChannelConverter().convert(ctx, value)
            settings.audit_log_channel_id = channel.id
            await ctx.send(f"Audit log channel set to {channel.mention} ({channel.id}).")
        elif key == "voice_channels":
            converter = commands.VoiceChannelConverter()
            channel_ids: set[int] = set()
            for token in value.split():
                channel = await converter.convert(ctx, token)
                channel_ids.add(channel.id)
            settings.voice_channel_ids = channel_ids or None
            await ctx.send(
                "Voice monitor channels updated to: "
                + (", ".join(f"<#{cid}>" for cid in channel_ids) if channel_ids else "None")
            )
        elif key == "lobby_channel":
            channel = await commands.VoiceChannelConverter().convert(ctx, value)
            settings.private_voice_lobby_id = channel.id
            await ctx.send(f"Private VC lobby set to {channel.mention} ({channel.id}).")
        elif key == "gem_phrase":
            settings.gem_trigger_phrase = value.lower()
            await ctx.send(f"Gem trigger phrase updated to `{settings.gem_trigger_phrase}`.")
        else:
            await ctx.send("Unknown key. Valid options: auto_role, gem_role, audit_channel, voice_channels, lobby_channel, gem_phrase")
            return

        save_guild_config(ctx.guild.id, settings)
    except commands.BadArgument as e:
        await ctx.send(f"I couldn't parse that value: {e}")
    except Exception as e:
        await ctx.send(f"Something went wrong while updating config: {e}")


@guildconfig.command(name="clear")
async def guildconfig_clear(ctx, key: str | None = None):
    if ctx.guild is None:
        return

    if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
        await ctx.send("You need Manage Server permissions to change this, chaver.")
        return

    if key is None:
        await ctx.send("Specify which key to clear.")
        return

    key = key.lower()
    settings = guild_settings.setdefault(ctx.guild.id, GuildSettings())

    if key == "auto_role":
        settings.auto_role_id = None
    elif key == "gem_role":
        settings.gem_role_id = None
    elif key == "audit_channel":
        settings.audit_log_channel_id = None
    elif key == "voice_channels":
        settings.voice_channel_ids = None
    elif key == "lobby_channel":
        settings.private_voice_lobby_id = None
    elif key == "gem_phrase":
        settings.gem_trigger_phrase = GEM_TRIGGER_PHRASE
    else:
        await ctx.send("Unknown key. Valid options: auto_role, gem_role, audit_channel, voice_channels, lobby_channel, gem_phrase")
        return

    save_guild_config(ctx.guild.id, settings)
    await ctx.send(f"Cleared custom value for {key}; now using defaults.")

@bot.event
async def on_member_join(member):
    # Auto Role - Assign "unpolished" role
    auto_role_id = get_auto_role_id(member.guild)
    if auto_role_id:
        role = member.guild.get_role(auto_role_id)
        if role:
            try:
                await member.add_roles(role)
                print(f"Assigned role {role.name} ({role.id}) to {member.name}")
                await send_audit_log(
                    member.guild,
                    f"{member.mention} auto-assigned **{role.name}** ({role.id}) on join.",
                    user=member,
                )
            except Exception as e:
                print(f"Failed to assign role: {e}")
        else:
            print(f"Role with ID {auto_role_id} not found")

    # Welcome Message
    channel = member.guild.system_channel
    if channel:
        await channel.send(f"What's up! Welcome to Gems! {member.mention}")


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    if after.bot or after.guild is None:
        return

    if await mentions_gem_phrase(after):
        trigger_phrase = get_gem_trigger_phrase(after.guild)
        await grant_gem_role(after, trigger=f"displaying {trigger_phrase} in profile")


@bot.event
async def on_voice_state_update(member: discord.Member, before, after):
    before_channel = before.channel if before else None
    after_channel = after.channel if after else None

    private_lobby_id = get_private_voice_lobby_id(member.guild)
    if after_channel and private_lobby_id and after_channel.id == private_lobby_id and not member.bot:
        await _ensure_private_voice(member, after_channel)

    configured_voice_channels = get_voice_channel_ids(member.guild)
    if after_channel and after_channel.id in configured_voice_channels and not member.bot:
        await _ensure_voice_monitor(after_channel)

    if (
        before_channel
        and before_channel.id in configured_voice_channels
        and (after_channel is None or after_channel.id != before_channel.id)
    ):
        await _stop_monitor_if_empty(before_channel)

    if before_channel and _get_private_session_by_channel(before_channel.id):
        await _cleanup_private_voice(before_channel)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    try:
        if message.guild is not None:
            log_audit_message(
                message_id=message.id,
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                author_id=message.author.id,
                content=message.content or "",
                created_at=message.created_at,
            )

        # Anti-nuke detection
        user_id = message.author.id
        now = datetime.now()

        # Clean old timestamps (older than 10 seconds)
        message_timestamps[user_id] = [
            ts for ts in message_timestamps[user_id]
            if now - ts < timedelta(seconds=10)
        ]

        message_timestamps[user_id].append(now)

        spam_handled = False

        # If more than 20 messages in 10 seconds, start deleting
        if len(message_timestamps[user_id]) > 20:
            spam_handled = True
            try:
                await message.delete()
                if len(message_timestamps[user_id]) == 21:  # Only warn once
                    await message.channel.send(
                        f"Oy vey {message.author.mention}, slow down! Anti-spam triggered.",
                        delete_after=5
                    )
            except Exception as e:
                print(f"Anti-spam handling failed: {e}")

        if message.guild is not None:
            bot.loop.create_task(_scan_message_safety(message))

        if not spam_handled and message.guild is not None:
            # Track messages for leaderboard, leveling, and user activity
            record_message(message.guild.id, user_id, now)
            messages, xp, level, leveled_up = increment_activity(
                message.guild.id,
                user_id,
                xp_gain=5,
            )

            # Level up notification
            if leveled_up:
                await message.channel.send(
                    f"Mazel tov {message.author.mention}! You leveled up to level {level}! 🎉"
                )

            # Grant Gem role at 150 messages
            if messages == 150:
                await grant_gem_role(message.author, trigger="reaching 150 messages")
                await message.channel.send(
                    f"Sababa! {message.author.mention} reached 150 messages and earned the Gem role! 💎"
                )

        # Jump into active chats with a friendly AI reply when conversations heat up
        should_reply = _record_chat_activity(message)
        if should_reply:
            prompt = message.content or "Join the conversation with something helpful and welcoming."
            try:
                reply = await generate_israeli_reply(
                    user_message=prompt,
                    username=message.author.display_name,
                    guild_name=message.guild.name if message.guild else None,
                    guild_id=message.guild.id if message.guild else None,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                )
                if reply:
                    await message.channel.send(reply)
            except Exception as e:
                print(f"Active chat reply failed: {e}")

        # LLM response when the bot is mentioned (but not when running a command)
        try:
            mentioned_bot = bot.user is not None and bot.user in message.mentions
        except Exception:
            mentioned_bot = False

        if mentioned_bot and (not message.content or not message.content.startswith(str(bot.command_prefix))):
            content = message.content
            if message.guild is not None and message.guild.me is not None:
                content = content.replace(message.guild.me.mention, "").strip()
            if not content:
                content = "Say something helpful and friendly."

            try:
                reply = await generate_israeli_reply(
                    user_message=content,
                    username=message.author.display_name,
                    guild_name=message.guild.name if message.guild else None,
                    guild_id=message.guild.id if message.guild else None,
                    user_id=message.author.id,
                    channel_id=message.channel.id,
                )
                if reply:
                    await message.reply(reply)
            except Exception as e:
                print(f"Mention reply failed: {e}")
    except Exception as e:
        print(f"on_message pipeline failed: {e}")
    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author and message.author.bot:
        return

    logged = get_logged_message(message.id)
    content = message.content or (logged["content"] if logged else "")
    author_id = getattr(message.author, "id", None) or (logged["author_id"] if logged else None)
    created_at = logged["created_at"] if logged else None

    deleter = await _find_message_deleter(message)
    deleter_id = getattr(deleter, "id", None)

    if message.guild is not None:
        record_deletion(
            message_id=message.id,
            guild_id=message.guild.id,
            channel_id=message.channel.id if message.channel else None,
            author_id=author_id,
            deleter_id=deleter_id,
            content=content,
            created_at=created_at,
        )

        deleter_label = (
            f"{deleter.mention} ({deleter.id})" if deleter is not None else "Unknown"
        )
        author_label = (
            f"{message.author.mention} ({message.author.id})"
            if message.author is not None
            else str(author_id)
        )

        description = (
            f"Message deleted in {message.channel.mention if message.channel else '#unknown'}.\n"
            f"Author: {author_label}\n"
            f"Deleted by: {deleter_label}\n"
            f"Message ID: {message.id}"
        )

        content_block = _truncate(content or "[no content captured]", 1500)
        await send_audit_log(
            message.guild,
            description + f"\nContent:\n```{content_block}```",
            user=message.author,
        )

# Moderation Commands
@bot.command(name='ban', aliases=['b'])
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"Oy vey! {member.mention} has been banned! \nReason: {reason if reason else 'No reason given'}")
    except Exception as e:
        await ctx.send(f"Nu? I couldn't ban them. Error: {e}")

@bot.command(name='kick', aliases=['k'])
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Yalla bye! {member.mention} has been kicked out.")
    except Exception as e:
        await ctx.send(f"Problem kicking this guy: {e}")


@bot.command(name='mute', aliases=['timeout'])
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member | None = None, duration: str | None = None):
    target = member

    if ctx.message.reference and target is None:
        try:
            referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            target = referenced_message.author
        except Exception:
            pass

    if target is None:
        await ctx.send("Nu? Who should I mute? Mention someone or reply to their message.")
        return

    if target == ctx.author:
        await ctx.send("You can't mute yourself, chaver!")
        return

    if duration is None:
        await ctx.send("How long? Add a duration like 10m, 1h, or 2d.")
        return

    parsed_duration = parse_duration(duration.lower())
    if parsed_duration is None:
        await ctx.send("I don't understand that duration. Use s, m, h, d, or w (e.g., 10m).")
        return

    if ctx.guild and target.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
        await ctx.send("Their hat is taller than yours—I can't mute them.")
        return

    timeout_until = discord.utils.utcnow() + parsed_duration

    try:
        await target.edit(timeout=timeout_until, reason=f"Muted by {ctx.author} for {duration}")
        await ctx.send(f"Shhhh {target.mention} has been muted for {duration}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to mute this member, bubbeleh.")
    except Exception as e:
        await ctx.send(f"Couldn't apply the mute: {e}")

@bot.command(name='clear', aliases=['c', 'purge'])
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Cleaned up the balagan! Removed {amount} messages.")
    await asyncio.sleep(3)
    await msg.delete()

# Role toggle command
@bot.command(name='role', aliases=['r'])
@commands.has_permissions(manage_roles=True)
async def toggle_role(ctx, member: discord.Member, *, role_input: str):
    # Try to find role by ID or name
    role = None
    
    # Check if it's an ID
    if role_input.isdigit():
        role = ctx.guild.get_role(int(role_input))
    
    # If not found, search by name
    if not role:
        role = discord.utils.get(ctx.guild.roles, name=role_input)
    
    if not role:
        await ctx.send(f"Oy, I couldn't find that role!")
        return
    
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"Removed {role.name} from {member.mention}")
        else:
            await member.add_roles(role)
            await ctx.send(f"Added {role.name} to {member.mention}")
    except discord.Forbidden:
        await ctx.send(f"Oy vey! I don't have permission to manage that role, chaver!")
    except Exception as e:
        await ctx.send(f"Nu? Something went wrong: {e}")


@bot.command(name='slowmode')
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int | None = None):
    if seconds is None:
        await ctx.send(
            f"Current slowmode is set to {ctx.channel.slowmode_delay} seconds. "
            "Provide a number to update it (use 0 to disable)."
        )
        return

    if seconds < 0 or seconds > 21600:
        await ctx.send("Use a value between 0 seconds and 6 hours (21600 seconds).")
        return

    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("Slowmode disabled. Keep it civil, chaverim!")
        else:
            await ctx.send(f"Slowmode updated to {seconds} seconds. Breathe and type slowly.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to change slowmode here.")
    except Exception as e:
        await ctx.send(f"Couldn't adjust slowmode: {e}")

# Leaderboard and Level Commands
@bot.command(name='leaderboard', aliases=['lb', 'top'])
async def leaderboard(ctx):
    rows = get_top_users(ctx.guild.id, limit=10)

    embed = discord.Embed(
        title="📊 Message Leaderboard",
        description="Top 10 members by message count",
        color=0x0000ff
    )

    for i, row in enumerate(rows, 1):
        user = await bot.fetch_user(row["user_id"])
        embed.add_field(
            name=f"{i}. {user.name}",
            value=f"Messages: {row['messages']} | Level: {row['level']}",
            inline=False
        )

    embed.set_footer(text="Keep chatting to climb the ranks!")
    await ctx.send(embed=embed)

@bot.command(name='rank', aliases=['level', 'stats'])
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    stats = get_user_stats(ctx.guild.id, member.id)
    
    embed = discord.Embed(
        title=f"{member.display_name}'s Stats",
        color=0x0000ff
    )
    embed.add_field(name="Messages", value=stats["messages"], inline=True)
    embed.add_field(name="Level", value=stats["level"], inline=True)
    embed.add_field(name="XP", value=f"{stats['xp']}/100", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await ctx.send(embed=embed)

# Info Commands
@bot.command(name='info')
async def info(ctx):
    embed = discord.Embed(title=f"Info for {ctx.guild.name}", description="Here is the situation...", color=0x0000ff)
    embed.add_field(name="Server Name", value=ctx.guild.name, inline=True)
    embed.add_field(name="Member Count", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="Region", value="The Middle East (probably)", inline=True)
    embed.set_footer(text="Developed with chutzpah")
    await ctx.send(embed=embed)


@bot.command(name="botresources", aliases=["bleedbot", "greed"])
async def botresources(ctx):
    embed = discord.Embed(
        title="Community bot resources",
        description=(
            "Quick references for popular community tools so you can onboard new guilds without leaving the chat."
        ),
        color=0x95A5A6,
    )
    embed.add_field(
        name="BleedBot",
        value=(
            "Moderation, logging, and autorole helper. Common commands include `/setup`, `/automod`, "
            "and `/purge`. Full list: https://bleed.bot/commands"
        ),
        inline=False,
    )
    embed.add_field(
        name="Greed (greed.best)",
        value=(
            "Economy and utility bot with games and leaderboards. Popular commands: `/balance`, "
            "`/daily`, `/work`, and `/shop`. Explore more at https://greed.best/commands"
        ),
        inline=False,
    )
    embed.set_footer(text="These links pull the latest docs directly from the bot authors.")
    await ctx.send(embed=embed)


@bot.command(name='poll')
async def poll(ctx, *, question_and_options: str | None = None):
    if question_and_options is None:
        await ctx.send("Provide a question and at least two options using `|` as a separator.")
        return

    segments = [segment.strip() for segment in question_and_options.split("|") if segment.strip()]
    if len(segments) < 3:
        await ctx.send("Format: `,poll What do we eat? | Pizza | Falafel | Sushi`")
        return

    question, options = segments[0], segments[1:]
    if len(options) > 10:
        await ctx.send("Easy there! Maximum of 10 options.")
        return

    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    embed = discord.Embed(title=f"📊 {question}", color=0x1ABC9C)
    description_lines = [f"{emoji_numbers[i]} {option}" for i, option in enumerate(options)]
    embed.description = "\n".join(description_lines)
    embed.set_footer(text="React below to vote! Votes update live.")

    message = await ctx.send(embed=embed)
    for i in range(len(options)):
        await message.add_reaction(emoji_numbers[i])


@bot.command(name='remind', aliases=['reminder'])
async def remind(ctx, duration: str | None = None, *, reminder: str | None = None):
    if duration is None or reminder is None:
        await ctx.send("Usage: `,remind <duration> <message>` e.g. `,remind 15m Drink water`")
        return

    parsed = parse_duration(duration.lower())
    if parsed is None:
        await ctx.send("I couldn't parse that time. Use values like 10m, 2h, or 1d.")
        return

    await ctx.send(f"Reminder set for {duration}. I'll ping you when time's up!")

    await asyncio.sleep(parsed.total_seconds())

    try:
        await ctx.send(f"{ctx.author.mention} ⏰ Reminder: {reminder}")
    except Exception as e:
        print(f"Failed to send reminder: {e}")

@bot.command(name='avatar', aliases=['av', 'pfp'])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=0x0000ff)
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text="Sababa!")
    await ctx.send(embed=embed)

@bot.command(name='banner')
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if user.banner:
        embed = discord.Embed(title=f"{member.display_name}'s Banner", color=0x0000ff)
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Oy, {member.display_name} doesn't have a banner!")

@bot.command(name='servericon', aliases=['guildicon'])
async def servericon(ctx):
    if ctx.guild.icon:
        embed = discord.Embed(title=f"{ctx.guild.name}'s Icon", color=0x0000ff)
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no icon, bubbeleh!")

@bot.command(name='serverbanner', aliases=['guildbanner'])
async def serverbanner(ctx):
    if ctx.guild.banner:
        embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=0x0000ff)
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no banner, chaver!")


@bot.command(name='vcinvite')
async def vcinvite(ctx, member: discord.Member | None = None):
    if ctx.guild is None:
        return

    if member is None:
        await ctx.send("Mention who you want to invite to your private VC, chaver.")
        return

    if member.bot:
        await ctx.send("Bots don't need an invite—they're already special!")
        return

    owner_role = _get_owner_role(ctx.guild, ctx.author.id)
    if owner_role is None:
        await ctx.send("You don't own a private voice channel right now.")
        return

    try:
        await member.add_roles(owner_role, reason=f"Invited to {ctx.author.display_name}'s private VC")
        await ctx.send(f"Added {member.mention} to your private VC role.")
    except discord.Forbidden:
        await ctx.send("I can't manage roles for that user, bubbeleh.")
    except Exception as e:
        await ctx.send(f"Couldn't invite them: {e}")


@bot.command(name='vcremove')
async def vcremove(ctx, member: discord.Member | None = None):
    if ctx.guild is None:
        return

    if member is None:
        await ctx.send("Mention who you want to remove from your private VC role.")
        return

    owner_role = _get_owner_role(ctx.guild, ctx.author.id)
    if owner_role is None:
        await ctx.send("You don't own a private voice channel right now.")
        return

    if owner_role not in member.roles:
        await ctx.send("They don't have access to your private VC, yalla.")
        return

    try:
        await member.remove_roles(owner_role, reason=f"Removed from {ctx.author.display_name}'s private VC")
        await ctx.send(f"Removed {member.mention} from your private VC role.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to adjust their roles.")
    except Exception as e:
        await ctx.send(f"Couldn't remove them: {e}")

# Music commands
music_queue = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("Chaver, you need to be in a voice channel!")
        return

    channel = ctx.author.voice.channel
    
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)

    await ctx.send(f"Nu, searching for: {url}...")
    
    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            
            url2 = info['url']
            title = info.get('title', 'Unknown')
            
            source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            
            if ctx.voice_client.is_playing():
                if ctx.guild.id not in music_queue:
                    music_queue[ctx.guild.id] = []
                music_queue[ctx.guild.id].append((url2, title))
                await ctx.send(f"Added to queue: **{title}**")
            else:
                ctx.voice_client.play(source, after=lambda e: play_next(ctx))
                await ctx.send(f"Now playing: **{title}** 🎵")
    except Exception as e:
        await ctx.send(f"Oy vey, error playing audio: {e}")

def play_next(ctx):
    if ctx.guild.id in music_queue and music_queue[ctx.guild.id]:
        url2, title = music_queue[ctx.guild.id].pop(0)
        source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
        ctx.voice_client.play(source, after=lambda e: play_next(ctx))
        asyncio.run_coroutine_threadsafe(
            ctx.send(f"Now playing: **{title}** 🎵"),
            bot.loop
        )

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the music, hold on...")
    else:
        await ctx.send("Nothing is playing, chaver!")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Yalla, resuming!")
    else:
        await ctx.send("Nothing is paused!")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipping this one...")
    else:
        await ctx.send("Nothing is playing!")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        if ctx.guild.id in music_queue:
            music_queue[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send("Stopped the music.")
    else:
        await ctx.send("I'm not in a voice channel!")

@bot.command(name='leave', aliases=['disconnect', 'dc'])
async def leave(ctx):
    if ctx.voice_client:
        if ctx.guild.id in music_queue:
            music_queue[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Shalom, I'm leaving!")
    else:
        await ctx.send("I'm not in a voice channel, bubbeleh!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Chaver, you don't have permissions for this!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Nu? You forgot something in the command.")
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
    else:
        bot.run(TOKEN)
