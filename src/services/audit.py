"""Audit logging service for tracking server events."""

from __future__ import annotations

from datetime import datetime

import discord

from config import get_audit_log_channel_id
from utils import truncate


async def send_audit_log(
    guild: discord.Guild | None,
    description: str,
    *,
    user: discord.abc.User | None = None,
) -> None:
    """Send an embed to the configured audit log channel."""
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


async def send_flagged_message_report(
    message: discord.Message,
    verdict: dict[str, object],
) -> None:
    """Report a message flagged by the safety classifier."""
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
        value=f"```{truncate(content, 900)}```",
        inline=False,
    )
    embed.set_footer(text=f"Message ID: {message.id}")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send flagged message report: {e}")
