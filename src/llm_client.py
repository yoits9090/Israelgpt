import os
import asyncio
from typing import Optional, List, Dict

from groq import Groq

from llm_history import log_message, get_recent_conversation


_client: Optional[Groq] = None


def _get_client() -> Optional[Groq]:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API")
    if not api_key:
        print("GROQ_API environment variable is not set; LLM replies are disabled.")
        return None

    _client = Groq(api_key=api_key)
    return _client


def _call_groq_sync(messages: list[Dict[str, str]]) -> Optional[str]:
    client = _get_client()
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


async def generate_israeli_reply(
    user_message: str,
    username: str,
    guild_name: Optional[str] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    channel_id: Optional[int] = None,
) -> Optional[str]:
    """Generate a very Israeli-sounding reply using Groq's llama-3.1-8b-instant.

    Returns None if the Groq client is not configured or an error occurs.
    """

    system_prompt = (
        "You are an extremely Israeli-sounding Discord bot. "
        "You speak like a friendly but blunt Israeli friend: informal, direct, humorous. "
        "Use some Hebrew and Israeli slang like 'sababa', 'yalla', 'nu', 'oy vey', "
        "'chutzpah', 'b'seder', but don't overdo it. "
        "Always be very positive and affectionate about Israel and occasionally say short "
        "uplifting phrases like 'Glory to Israel', 'Am Yisrael Chai', etc. "
        "However, NEVER insult or attack any person or group; stay respectful and kind. "
        "Despite the joking tone, always give a clear, correct, and helpful answer."
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

    # For the current turn, keep content compact but informative
    current_content = (
        f"User ({username}) in server {guild_name or 'unknown'} said:\n"
        f"{user_message}\n\n"
        "Reply in that very Israeli style, as if chatting in a Discord channel."
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
