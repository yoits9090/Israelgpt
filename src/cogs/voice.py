"""Voice channel management cog (private VCs; monitoring disabled)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import discord
from discord.ext import commands

from config import get_private_voice_lobby_id


@dataclass
class PrivateVoiceSession:
    """Tracks a user's private voice channel."""

    owner_id: int
    channel_id: int
    role_id: int


class VoiceCog(commands.Cog, name="Voice"):
    """Private voice channels with monitoring disabled."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.private_voice_by_owner: Dict[int, PrivateVoiceSession] = {}
        self.private_voice_by_channel: Dict[int, int] = {}

    # --- Private voice session management ---

    def _register_session(self, session: PrivateVoiceSession):
        self.private_voice_by_owner[session.owner_id] = session
        self.private_voice_by_channel[session.channel_id] = session.owner_id

    def _unregister_session(self, owner_id: int):
        session = self.private_voice_by_owner.pop(owner_id, None)
        if session:
            self.private_voice_by_channel.pop(session.channel_id, None)

    def _get_session_by_channel(self, channel_id: int) -> Optional[PrivateVoiceSession]:
        owner_id = self.private_voice_by_channel.get(channel_id)
        if owner_id is None:
            return None
        return self.private_voice_by_owner.get(owner_id)

    def _get_owner_role(self, guild: discord.Guild, owner_id: int) -> Optional[discord.Role]:
        session = self.private_voice_by_owner.get(owner_id)
        if session is None:
            return None
        role = guild.get_role(session.role_id)
        if role is None:
            self._unregister_session(owner_id)
            return None
        return role

    async def _ensure_private_voice(
        self, member: discord.Member, lobby_channel: discord.VoiceChannel
    ):
        if member.guild is None:
            return

        existing_session = self.private_voice_by_owner.get(member.id)
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
                self._unregister_session(member.id)

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
            self._register_session(session)

            await member.add_roles(role, reason="Granting private voice ownership")
            await member.move_to(channel)
        except Exception as e:
            print(f"Failed to create private voice channel: {e}")

    async def _cleanup_private_voice(self, channel: discord.VoiceChannel):
        session = self._get_session_by_channel(channel.id)
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

        self._unregister_session(session.owner_id)

    # --- Event listener ---

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        before_channel = before.channel if before else None
        after_channel = after.channel if after else None

        private_lobby_id = get_private_voice_lobby_id(member.guild)
        if (
            after_channel
            and private_lobby_id
            and after_channel.id == private_lobby_id
            and not member.bot
        ):
            await self._ensure_private_voice(member, after_channel)

        if before_channel and self._get_session_by_channel(before_channel.id):
            await self._cleanup_private_voice(before_channel)

    # --- Commands ---

    @commands.hybrid_command(name="vcinvite")
    async def vcinvite(self, ctx: commands.Context, member: discord.Member | None = None):
        """Invite a member to your private voice channel."""
        if ctx.guild is None:
            return

        if member is None:
            await ctx.send("Mention who you want to invite to your private VC, chaver.")
            return

        if member.bot:
            await ctx.send("Bots don't need an invite—they're already special!")
            return

        owner_role = self._get_owner_role(ctx.guild, ctx.author.id)
        if owner_role is None:
            await ctx.send("You don't own a private voice channel right now.")
            return

        try:
            await member.add_roles(
                owner_role, reason=f"Invited to {ctx.author.display_name}'s private VC"
            )
            await ctx.send(f"Added {member.mention} to your private VC role.")
        except discord.Forbidden:
            await ctx.send("I can't manage roles for that user, bubbeleh.")
        except Exception as e:
            await ctx.send(f"Couldn't invite them: {e}")

    @commands.hybrid_command(name="vcremove")
    async def vcremove(self, ctx: commands.Context, member: discord.Member | None = None):
        """Remove a member from your private voice channel."""
        if ctx.guild is None:
            return

        if member is None:
            await ctx.send("Mention who you want to remove from your private VC role.")
            return

        owner_role = self._get_owner_role(ctx.guild, ctx.author.id)
        if owner_role is None:
            await ctx.send("You don't own a private voice channel right now.")
            return

        if owner_role not in member.roles:
            await ctx.send("They don't have access to your private VC, yalla.")
            return

        try:
            await member.remove_roles(
                owner_role, reason=f"Removed from {ctx.author.display_name}'s private VC"
            )
            await ctx.send(f"Removed {member.mention} from your private VC role.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to adjust their roles.")
        except Exception as e:
            await ctx.send(f"Couldn't remove them: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCog(bot))
