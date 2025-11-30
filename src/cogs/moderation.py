"""Moderation commands cog."""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from utils import parse_duration


class ModerationCog(commands.Cog, name="Moderation"):
    """Server moderation commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ban", aliases=["b"])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Ban a member from the server."""
        try:
            await member.ban(reason=reason)
            await ctx.send(
                f"Oy vey! {member.mention} has been banned!\n"
                f"Reason: {reason if reason else 'No reason given'}"
            )
        except Exception as e:
            await ctx.send(f"Nu? I couldn't ban them. Error: {e}")

    @commands.hybrid_command(name="kick", aliases=["k"])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Kick a member from the server."""
        try:
            await member.kick(reason=reason)
            await ctx.send(f"Yalla bye! {member.mention} has been kicked out.")
        except Exception as e:
            await ctx.send(f"Problem kicking this guy: {e}")

    @commands.hybrid_command(name="mute", aliases=["timeout"])
    @commands.has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member | None = None,
        duration: str | None = None,
    ):
        """Timeout a user for a specified duration."""
        target = member

        # Support replying to a message to mute that author
        if ctx.message.reference and target is None:
            try:
                referenced_message = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
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

        if (
            ctx.guild
            and target.top_role >= ctx.author.top_role
            and ctx.guild.owner_id != ctx.author.id
        ):
            await ctx.send("Their hat is taller than yours—I can't mute them.")
            return

        timeout_until = discord.utils.utcnow() + parsed_duration

        try:
            await target.edit(
                timeout=timeout_until, reason=f"Muted by {ctx.author} for {duration}"
            )
            await ctx.send(f"Shhhh {target.mention} has been muted for {duration}.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to mute this member, bubbeleh.")
        except Exception as e:
            await ctx.send(f"Couldn't apply the mute: {e}")

    @commands.hybrid_command(name="clear", aliases=["c", "purge"])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, amount: int):
        """Bulk delete messages from the channel."""
        await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"Cleaned up the balagan! Removed {amount} messages.")
        await asyncio.sleep(3)
        await msg.delete()

    @commands.hybrid_command(name="role", aliases=["r"])
    @commands.has_permissions(manage_roles=True)
    async def toggle_role(
        self, ctx: commands.Context, member: discord.Member, *, role_input: str
    ):
        """Toggle a role on a member."""
        role = None

        # Check if it's an ID
        if role_input.isdigit():
            role = ctx.guild.get_role(int(role_input))

        # If not found, search by name
        if not role:
            role = discord.utils.get(ctx.guild.roles, name=role_input)

        if not role:
            await ctx.send("Oy, I couldn't find that role!")
            return

        try:
            if role in member.roles:
                await member.remove_roles(role)
                await ctx.send(f"Removed {role.name} from {member.mention}")
            else:
                await member.add_roles(role)
                await ctx.send(f"Added {role.name} to {member.mention}")
        except discord.Forbidden:
            await ctx.send("Oy vey! I don't have permission to manage that role, chaver!")
        except Exception as e:
            await ctx.send(f"Nu? Something went wrong: {e}")

    @commands.hybrid_command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int | None = None):
        """Set or view channel slowmode."""
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


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
