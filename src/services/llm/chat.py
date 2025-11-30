"""Chat completion service using Groq's LLM."""

from __future__ import annotations

import asyncio
import re
from typing import Optional, Dict, List, Tuple

import discord

from db.llm import log_message, get_recent_conversation
from .client import get_client

# URL regex for truncating links
_URL_PATTERN = re.compile(r'https?://\S+')


def _truncate_links(text: str, max_len: int = 30) -> str:
    """Replace long URLs with truncated versions."""
    def replacer(match):
        url = match.group(0)
        if len(url) > max_len:
            return url[:max_len] + "..."
        return url
    return _URL_PATTERN.sub(replacer, text)


def _call_groq_sync(messages: list[Dict[str, str]]) -> Optional[str]:
    """Synchronous Groq chat completion call."""
    client = get_client()
    if client is None:
        return None

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=512,
            temperature=0.7,
        )
        message = completion.choices[0].message
        return message.content if message and message.content else None
    except Exception as e:
        print(f"Groq LLM error: {e}")
        return None


async def fetch_channel_context(
    channel: discord.TextChannel,
    limit: int = 30,
) -> List[Tuple[str, str, str]]:
    """
    Fetch recent messages from a channel for context.
    Returns list of (username, user_id, content) tuples.
    """
    messages = []
    try:
        async for msg in channel.history(limit=limit):
            if msg.author.bot:
                continue
            content = _truncate_links(msg.content or "")
            if content:
                messages.append((
                    msg.author.display_name,
                    str(msg.author.id),
                    content[:500],  # Truncate long messages
                ))
    except Exception as e:
        print(f"Failed to fetch channel history: {e}")
    
    # Reverse to chronological order (oldest first)
    return list(reversed(messages))


async def get_active_users_context(
    guild_id: int,
    user_ids: List[int],
    max_per_user: int = 5,
) -> Dict[int, List[Tuple[str, str]]]:
    """
    Get recent conversation history for multiple users.
    Returns dict of user_id -> list of (role, content) tuples.
    """
    context = {}
    for uid in user_ids[:10]:  # Limit to 10 users
        history = get_recent_conversation(
            guild_id=guild_id,
            user_id=uid,
            max_messages=max_per_user,
            max_chars=1000,
        )
        if history:
            context[uid] = history
    return context


async def generate_israeli_reply(
    user_message: str,
    username: str,
    guild_name: Optional[str] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    channel_context: Optional[List[Tuple[str, str, str]]] = None,
    active_users_history: Optional[Dict[int, List[Tuple[str, str]]]] = None,
) -> Optional[str]:
    """Generate a very Israeli-sounding reply using Groq's llama-3.1-8b-instant.

    Returns None if the Groq client is not configured or an error occurs.
    """
    system_prompt = (
        "You are an extremely Israeli-sounding Discord bot. "
        "You are deeply proud and supportive of Israel, its people, and its democratic leaders "
        "(including the Prime Minister). "
        "You speak like a friendly but blunt Israeli friend: informal, direct, humorous, and very passionate. "
        "Use some Hebrew and Israeli slang like 'sababa', 'yalla', 'nu', 'oy vey', 'chutzpah', 'b'seder', but don't overdo it. "
        "When someone criticizes Israel, respond with very strong disagreement and a spirited defense of Israel, "
        "explaining why Israel is good and why its supporters are right, but do so without personal attacks. "
        "You may praise Israel with phrases like 'Glory to Israel', 'Am Yisrael Chai', etc., and be clearly biased in Israel's favor. "
        "NEVER insult, harass, or attack any person or group, and NEVER encourage harm or violence. "
        "Despite the joking and passionate tone, always give a clear, correct, and helpful answer."
    )

    # Build limited-length conversational context from history
    history_messages: list[dict] = []
    if guild_id is not None and user_id is not None:
        history = get_recent_conversation(
            guild_id=guild_id,
            user_id=user_id,
            max_messages=40,
            max_chars=6000,
        )
        for role, content in history:
            role_name = "assistant" if role == "assistant" else "user"
            history_messages.append({"role": role_name, "content": content})

    # Build channel context string (last 30 messages)
    channel_context_str = ""
    if channel_context:
        chat_lines = []
        for uname, uid, content in channel_context[-30:]:
            chat_lines.append(f"{uname}: {content}")
        if chat_lines:
            channel_context_str = (
                "\n--- Recent chat in this channel ---\n"
                + "\n".join(chat_lines)
                + "\n--- End of recent chat ---\n"
            )

    # Build active users' previous conversations with the bot
    users_history_str = ""
    if active_users_history:
        user_sections = []
        for uid, convos in active_users_history.items():
            if convos:
                convo_lines = [f"  {role}: {content[:150]}" for role, content in convos[-3:]]
                user_sections.append(f"User {uid}'s recent exchanges:\n" + "\n".join(convo_lines))
        if user_sections:
            users_history_str = (
                "\n--- Previous conversations with active chatters ---\n"
                + "\n\n".join(user_sections[:5])  # Limit to 5 users
                + "\n--- End of previous conversations ---\n"
            )

    # For the current turn, keep content compact but informative
    current_content = (
        f"Server: {guild_name or 'unknown'}\n"
        f"{channel_context_str}"
        f"{users_history_str}\n"
        f"Now {username} said: {user_message}\n\n"
        "Jump into this conversation naturally. Be relevant to what people are discussing. "
        "Reply in that very Israeli style, keeping it short and casual like Discord chat."
    )

    # Log the user prompt
    if guild_id is not None and user_id is not None:
        log_message(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            role="user",
            content=user_message,
        )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *history_messages,
        {"role": "user", "content": current_content},
    ]

    loop = asyncio.get_running_loop()
    reply = await asyncio.to_thread(_call_groq_sync, messages)

    if reply is not None and guild_id is not None and user_id is not None:
        log_message(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            role="assistant",
            content=reply,
        )

    return reply
