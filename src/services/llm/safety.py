"""Content safety classification using Llama Guard."""

from __future__ import annotations

import asyncio
import json
from typing import Optional, Dict, Any

from .client import get_client


def _parse_guard_response(raw: str) -> Optional[Dict[str, Any]]:
    """Parse the safety classifier response into a structured dict."""
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
    """Synchronous safety classification call."""
    client = get_client()
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
    """Classify message content for safety violations."""
    return await asyncio.to_thread(_call_guard_sync, content)
