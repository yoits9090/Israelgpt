"""Bot event handlers."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import discord
from discord.ext import commands

from config import get_auto_role_id, get_gem_trigger_phrase
from db.levels import increment_activity
from db.users import record_message
from db.audit import log_message as log_audit_message, get_message as get_logged_message, record_deletion
from services import send_audit_log, grant_gem_role, mentions_gem_phrase
from services.audit import send_flagged_message_report
from services.llm import fetch_channel_context
from taskqueue import get_task_queue
from utils import truncate
from observability import count_message, count_command, count_error, count_spam, observe_command_duration

from .activity import ActivityTracker


task_queue = get_task_queue()


async def _find_message_deleter(message: discord.Message) -> discord.abc.User | None:
    """Try to find who deleted a message via audit logs."""
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


async def _queue_message_safety(message: discord.Message) -> None:
    """Scan a message for safety violations via the worker queue."""
    if not message.content:
        return

    job = None
    try:
        job = await task_queue.enqueue(
            "safety_scan",
            {
                "content": message.content,
                "guild_id": message.guild.id if message.guild else None,
                "channel_id": message.channel.id if message.channel else None,
                "author_id": message.author.id if message.author else None,
            },
            requested_by=getattr(message.author, "id", None),
            result_ttl=90,
        )
        verdict = await task_queue.wait_for_result(job.job_id, timeout=30)
        if verdict is None:
            return
        if str(verdict.get("verdict", "safe")).lower() != "safe":
            await send_flagged_message_report(message, verdict)
    except asyncio.TimeoutError:
        job_id = job.job_id if job else "unknown"
        print(f"Safety scan timed out for job {job_id}")
    except Exception as exc:
        print(f"Safety scan failed: {exc}")


async def _queue_llm_reply(
    message: discord.Message,
    prompt: str,
    channel_context,
    active_user_ids,
    *,
    reply_to_message: bool = False,
) -> None:
    """Request an LLM reply via the worker queue and send it back to Discord."""
    if not prompt:
        return

    job = None
    try:
        job = await task_queue.enqueue(
            "llm_reply",
            {
                "prompt": prompt,
                "username": message.author.display_name,
                "guild_name": message.guild.name if message.guild else None,
                "guild_id": message.guild.id if message.guild else None,
                "user_id": message.author.id,
                "channel_id": message.channel.id,
                "channel_context": channel_context,
                "active_user_ids": active_user_ids,
            },
            requested_by=getattr(message.author, "id", None),
            result_ttl=180,
        )
        result = await task_queue.wait_for_result(job.job_id, timeout=75)
        reply_text = (result or {}).get("reply")
        if not reply_text:
            return
        if reply_to_message:
            await message.reply(reply_text)
        else:
            await message.channel.send(reply_text)
    except asyncio.TimeoutError:
        job_id = job.job_id if job else "unknown"
        print(f"LLM reply timed out for job {job_id}")
    except Exception as exc:
        print(f"LLM reply failed: {exc}")


def setup_events(bot: commands.Bot) -> None:
    """Register all event handlers on the bot."""
    
    activity_tracker = ActivityTracker(bot_prefix=str(bot.command_prefix))
    bot._slash_synced = False  # Lazy sync flag to avoid repeated global syncs

    @bot.event
    async def on_ready():
        print(f"{bot.user} is online.")
        await bot.change_presence(activity=discord.Game(name="Supporting the guild"))

        # Sync hybrid commands -> application commands once on startup
        if not getattr(bot, "_slash_synced", False):
            try:
                await bot.tree.sync()
                bot._slash_synced = True
                print("Slash commands synced with Discord.")
            except Exception as e:
                print(f"Failed to sync application commands: {e}")

    @bot.event
    async def on_member_join(member: discord.Member):
        # Auto Role
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
            await channel.send(f"Welcome to the server, {member.mention}!")

    @bot.event
    async def on_presence_update(before: discord.Member, after: discord.Member):
        if after.bot or after.guild is None:
            return

        if await mentions_gem_phrase(after):
            trigger_phrase = get_gem_trigger_phrase(after.guild)
            await grant_gem_role(after, trigger=f"displaying {trigger_phrase} in profile")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        try:
            count_message(message.guild.id if message.guild else None)
            # Log message for audit
            if message.guild is not None:
                log_audit_message(
                    message_id=message.id,
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    author_id=message.author.id,
                    content=message.content or "",
                    created_at=message.created_at,
                )

            # Anti-spam check (high frequency - uses Rust when available)
            user_id = message.author.id
            now = datetime.now()
            is_spam, count = activity_tracker.check_spam(user_id, now)

            spam_handled = False
            if is_spam:
                spam_handled = True
                count_spam(message.guild.id if message.guild else None)
                try:
                    await message.delete()
                    if count == 21:  # Only warn once
                        await message.channel.send(
                            f"Please slow down {message.author.mention}; anti-spam triggered.",
                            delete_after=5,
                        )
                except Exception as e:
                    print(f"Anti-spam handling failed: {e}")

            # Safety scan (async background task)
            if message.guild is not None:
                bot.loop.create_task(_queue_message_safety(message))

            # Leveling and XP
            if not spam_handled and message.guild is not None:
                record_message(message.guild.id, user_id, now)
                messages, xp, level, leveled_up = increment_activity(
                    message.guild.id,
                    user_id,
                    xp_gain=5,
                )

                if leveled_up:
                    await message.channel.send(
                        f"Great job {message.author.mention}! You leveled up to level {level}! 🎉"
                    )

                if messages == 150:
                    await grant_gem_role(message.author, trigger="reaching 150 messages")
                    await message.channel.send(
                        f"{message.author.mention} reached 150 messages and earned the Gem role! 💎"
                    )

            # Active chat detection (high frequency - uses Rust when available)
            if message.guild is not None:
                should_reply = activity_tracker.record_chat_activity(
                    guild_id=message.guild.id,
                    user_id=message.author.id,
                    is_bot=message.author.bot,
                    content=message.content,
                )
                if should_reply:
                    prompt = message.content or "Join the conversation with something helpful and welcoming."
                    try:
                        # Fetch channel context (last 30 messages, truncate links)
                        channel_context = await fetch_channel_context(message.channel, limit=30)
                        active_user_ids = list(
                            set(int(uid) for _, uid, _ in channel_context)
                        )[:10]

                        bot.loop.create_task(
                            _queue_llm_reply(
                                message,
                                prompt,
                                channel_context,
                                active_user_ids,
                            )
                        )
                    except Exception as e:
                        print(f"Active chat reply failed: {e}")

            # Bot mention response
            try:
                mentioned_bot = bot.user is not None and bot.user in message.mentions
            except Exception:
                mentioned_bot = False

            if mentioned_bot and (
                not message.content or not message.content.startswith(str(bot.command_prefix))
            ):
                content = message.content
                if message.guild is not None and message.guild.me is not None:
                    content = content.replace(message.guild.me.mention, "").strip()
                if not content:
                    content = "Say something helpful and friendly."

                try:
                    channel_context = await fetch_channel_context(message.channel, limit=25)
                    bot.loop.create_task(
                        _queue_llm_reply(
                            message,
                            content,
                            channel_context,
                            [message.author.id],
                            reply_to_message=True,
                        )
                    )
                except Exception as e:
                    print(f"Mention reply failed: {e}")

        except Exception as e:
            print(f"on_message pipeline failed: {e}")
            count_error("on_message")

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

            content_block = truncate(content or "[no content captured]", 1500)
            await send_audit_log(
                message.guild,
                description + f"\nContent:\n```{content_block}```",
                user=message.author,
            )

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Chaver, you don't have permissions for this!")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Nu? You forgot something in the command.")
        else:
            print(f"Error: {error}")

        count_error("command_error")

    @bot.event
    async def on_command(ctx: commands.Context):
        ctx._cmd_start_time = time.perf_counter()

    @bot.event
    async def on_command_completion(ctx: commands.Context):
        guild_id = ctx.guild.id if ctx.guild else None
        command_name = ctx.command.qualified_name if ctx.command else "unknown"
        count_command(guild_id, command_name)

        start = getattr(ctx, "_cmd_start_time", None)
        if start is not None:
            duration = time.perf_counter() - start
            observe_command_duration(guild_id, command_name, duration)
