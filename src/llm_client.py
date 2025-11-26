import json
import os
import asyncio
from typing import Optional, List, Dict, Any

from groq import Groq

from db.llm import log_message, get_recent_conversation


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


def _parse_guard_response(raw: str) -> Optional[Dict[str, Any]]:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "verdict" in parsed:
            return parsed
    except Exception:
        pass

    lowered = raw.lower()
    if lowered.startswith("safe"):
        return {"verdict": "safe", "categories": [], "details": raw}
    if "unsafe" in lowered or "flag" in lowered:
        return {"verdict": "unsafe", "categories": [], "details": raw}
    return None


def _call_guard_sync(content: str) -> Optional[Dict[str, Any]]:
    client = _get_client()
    if client is None:
        return None

    system_prompt = (
        "You are a strict safety classifier. Analyze the provided Discord message content. "
        "Respond with compact JSON using the following shape: "
        '{"verdict":"safe"|"unsafe","categories":["..."],"details":"..."}. '
        "Mark any harassment, hate, self-harm, sexual, or violent content as unsafe."
    )

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-guard-4-12b",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Message:\n{content}\nReturn only the JSON verdict.",
                },
            ],
            temperature=0,
            max_tokens=300,
        )
        message = completion.choices[0].message
        if message and message.content:
            return _parse_guard_response(message.content)
        return None
    except Exception as e:
        print(f"Groq moderation error: {e}")
        return None


async def classify_message_safety(content: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(_call_guard_sync, content)


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
