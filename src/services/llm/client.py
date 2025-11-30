"""Groq API client management."""

from __future__ import annotations

import os
from typing import Optional

from groq import Groq

_client: Optional[Groq] = None


def get_client() -> Optional[Groq]:
    """Get or create the Groq client singleton."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API")
    if not api_key:
        print("GROQ_API environment variable is not set; LLM replies are disabled.")
        return None

    _client = Groq(api_key=api_key)
    return _client
