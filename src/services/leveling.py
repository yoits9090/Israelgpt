"""Leveling and gem role management service."""

from __future__ import annotations

import discord

from config import get_gem_role_id, get_gem_trigger_phrase
from utils import text_contains_phrase
from .audit import send_audit_log


async def grant_gem_role(member: discord.Member, *, trigger: str) -> None:
    """Grant the gem role to a member if they don't already have it."""
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


async def mentions_gem_phrase(member: discord.Member) -> bool:
    """Check if a member's profile/status contains the gem trigger phrase."""
    trigger_phrase = get_gem_trigger_phrase(member.guild).lower()

    # Check rich presence and custom status
    for activity in member.activities or []:
        if isinstance(activity, discord.CustomActivity):
            if text_contains_phrase(
                str(activity.name or activity.state or ""), trigger_phrase
            ):
                return True
        elif text_contains_phrase(getattr(activity, "name", None), trigger_phrase):
            return True

    # Check profile/about me when available
    profile_method = getattr(member, "profile", None)
    if callable(profile_method):
        try:
            profile = await profile_method()
            if text_contains_phrase(getattr(profile, "bio", None), trigger_phrase):
                return True
        except Exception as e:
            print(f"Failed to check member profile for gem phrase: {e}")

    return False
