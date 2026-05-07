"""Minimal Discord chatbot event handlers."""

from __future__ import annotations

import discord
from discord.ext import commands

from services.llm import fetch_channel_context, generate_chatbot_reply


async def _send_chatbot_reply(
    message: discord.Message,
    prompt: str,
    *,
    reply_to_message: bool = True,
) -> None:
    """Generate and send a chatbot reply for a Discord message."""
    if not prompt.strip():
        prompt = "Say hello and offer to help."

    try:
        async with message.channel.typing():
            channel_context = await fetch_channel_context(message.channel, limit=20)
            reply_text = await generate_chatbot_reply(
                user_message=prompt,
                username=message.author.display_name,
                guild_name=message.guild.name if message.guild else None,
                guild_id=message.guild.id if message.guild else None,
                user_id=message.author.id,
                channel_id=message.channel.id,
                channel_context=channel_context,
            )
    except Exception as exc:
        print(f"Chatbot reply failed: {exc}")
        return

    if not reply_text:
        return

    if reply_to_message:
        await message.reply(reply_text, mention_author=False)
    else:
        await message.channel.send(reply_text)


def setup_events(bot: commands.Bot) -> None:
    """Register the small set of events needed for a chatbot-only bot."""

    @bot.event
    async def on_ready() -> None:
        print(f"{bot.user} is online as a chatbot.")
        await bot.change_presence(activity=discord.Game(name="Chat with Israel GPT"))

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        # DMs are always chatbot conversations. In servers, reply only when mentioned
        # so the bot stays a simple assistant instead of moderating or automating the guild.
        is_dm = message.guild is None
        mentioned_bot = bot.user is not None and bot.user in message.mentions
        if not is_dm and not mentioned_bot:
            return

        prompt = message.content or ""
        if mentioned_bot and message.guild is not None and message.guild.me is not None:
            prompt = prompt.replace(message.guild.me.mention, "").strip()

        await _send_chatbot_reply(message, prompt, reply_to_message=not is_dm)
