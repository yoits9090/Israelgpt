"""Chat completion service for the Israel GPT chatbot."""

from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional, Tuple

import discord

from config import CHATBOT_MAX_TOKENS, CHATBOT_MODEL, CHATBOT_TEMPERATURE
from db.llm import get_recent_conversation, log_message

from .client import get_client

_URL_PATTERN = re.compile(r"https?://\S+")


def _truncate_links(text: str, max_len: int = 30) -> str:
    """Replace long URLs with compact placeholders for channel context."""

    def replacer(match: re.Match[str]) -> str:
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
            model=CHATBOT_MODEL,
            messages=messages,
            max_tokens=CHATBOT_MAX_TOKENS,
            temperature=CHATBOT_TEMPERATURE,
        )
        message = completion.choices[0].message
        return message.content if message and message.content else None
    except Exception as e:
        print(f"Groq LLM error: {e}")
        return None


async def fetch_channel_context(
    channel: discord.abc.Messageable,
    limit: int = 20,
) -> List[Tuple[str, str, str]]:
    """Fetch recent non-bot channel messages for lightweight conversation context."""
    messages: list[Tuple[str, str, str]] = []
    try:
        async for msg in channel.history(limit=limit):
            if msg.author.bot:
                continue
            content = _truncate_links(msg.content or "")
            if content:
                messages.append((
                    msg.author.display_name,
                    str(msg.author.id),
                    content[:500],
                ))
    except Exception as e:
        print(f"Failed to fetch channel history: {e}")

    return list(reversed(messages))


async def generate_chatbot_reply(
    user_message: str,
    username: str,
    guild_name: Optional[str] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    channel_id: Optional[int] = None,
    channel_context: Optional[List[Tuple[str, str, str]]] = None,
) -> Optional[str]:
    """Generate a concise Discord chatbot reply."""
    system_prompt = (
        "You are Israel GPT, a focused Discord chatbot. "
        "Your only job is to chat with users who message you directly or mention you. "
        "Be friendly, concise, practical, and conversational. "
        "Do not claim to moderate, manage roles, play music, run tickets, track XP, or perform server automation. "
        "If asked for bot features beyond chatting, explain that you are now just a chatbot and offer to help in chat. "
        "Decline unsafe requests briefly and redirect toward safe, helpful alternatives."
    )

    history_messages: list[dict[str, str]] = []
    if guild_id is not None and user_id is not None:
        history = get_recent_conversation(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            max_messages=20,
            max_chars=4000,
        )
        for role, content in history:
            role_name = "assistant" if role == "assistant" else "user"
            history_messages.append({"role": role_name, "content": content})

    channel_context_str = ""
    if channel_context:
        chat_lines = [f"{uname}: {content}" for uname, _uid, content in channel_context[-20:]]
        if chat_lines:
            channel_context_str = (
                "\n--- Recent visible chat context ---\n"
                + "\n".join(chat_lines)
                + "\n--- End context ---\n"
            )

    current_content = (
        f"Server: {guild_name or 'direct message'}\n"
        f"{channel_context_str}"
        f"{username}: {user_message}\n\n"
        "Reply as Israel GPT. Keep the answer helpful and suitable for Discord."
    )

    if guild_id is not None and user_id is not None:
        log_message(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            role="user",
            content=user_message,
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *history_messages,
        {"role": "user", "content": current_content},
    ]

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


# Backwards-compatible alias for microservices or older imports that still call the old name.
generate_professional_reply = generate_chatbot_reply
