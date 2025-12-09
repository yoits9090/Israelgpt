"""General helper functions.

This module provides Python fallbacks for functions that may be accelerated
by the Rust extension when available.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

# Try to import Rust-accelerated versions
try:
    from guildest_core import (
        truncate as _rust_truncate,
        parse_duration_secs as _rust_parse_duration_secs,
        text_contains_phrase as _rust_text_contains_phrase,
    )
    _USE_RUST = True
except ImportError:
    _USE_RUST = False


def truncate(text: str, limit: int = 1700) -> str:
    """Truncate text to a maximum length, appending '...' if truncated."""
    if _USE_RUST:
        return _rust_truncate(text, limit)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def parse_duration(duration: str) -> Optional[timedelta]:
    """Parse a duration string like '10m', '2h', '1d' into a timedelta."""
    if _USE_RUST:
        secs = _rust_parse_duration_secs(duration)
        return timedelta(seconds=secs) if secs is not None else None

    match = re.match(r"^(\d+)([smhdw])$", duration)
    if not match:
        return None

    value, unit = match.groups()
    value = int(value)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 60 * 60 * 24,
        "w": 60 * 60 * 24 * 7,
    }

    seconds = value * multipliers[unit]
    return timedelta(seconds=seconds)


def text_contains_phrase(text: str | None, phrase: str) -> bool:
    """Check if text contains phrase (case-insensitive)."""
    if _USE_RUST and text is not None:
        return _rust_text_contains_phrase(text, phrase)
    return text is not None and phrase in text.lower()
