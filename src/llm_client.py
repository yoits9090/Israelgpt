import os
import asyncio
from typing import Optional

from groq import Groq


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


def _call_groq_sync(prompt: str, system_prompt: str) -> Optional[str]:
    client = _get_client()
    if client is None:
        return None

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
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

    full_prompt = (
        f"User ({username}) in server {guild_name or 'unknown'} said:\n"
        f"{user_message}\n\n"
        "Reply in that very Israeli style, as if chatting in a Discord channel."
    )

    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(_call_groq_sync, full_prompt, system_prompt)
