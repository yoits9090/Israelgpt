"""High-frequency activity tracking.

This module handles anti-spam and chat activity detection.
Uses Rust acceleration when available for performance.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Tuple

import discord

# Try to import Rust-accelerated tracker
try:
    from guildest_core import ActivityTrackerRust
    _USE_RUST = True
except ImportError:
    _USE_RUST = False


class ActivityTracker:
    """Tracks message activity for anti-spam and chat engagement detection.
    
    This is called on every message, so performance is critical.
    The Rust implementation provides ~10x speedup for these operations.
    """

    def __init__(self, bot_prefix: str = ","):
        self.bot_prefix = bot_prefix
        
        if _USE_RUST:
            self._rust_tracker = ActivityTrackerRust()
        else:
            # Python fallback
            self._message_timestamps: Dict[int, list[datetime]] = defaultdict(list)
            self._chat_activity: Dict[int, deque[Tuple[datetime, int]]] = defaultdict(deque)
            self._chat_cooldowns: Dict[int, datetime] = {}

    def check_spam(self, user_id: int, now: datetime | None = None) -> Tuple[bool, int]:
        """Check if a user is spamming.
        
        Returns (is_spam, message_count_in_window).
        Spam threshold: >20 messages in 10 seconds.
        """
        if now is None:
            now = datetime.now()

        if _USE_RUST:
            return self._rust_tracker.check_spam(user_id, now.timestamp())

        # Python fallback
        timestamps = self._message_timestamps[user_id]
        
        # Clean old timestamps (older than 10 seconds)
        cutoff = now - timedelta(seconds=10)
        timestamps[:] = [ts for ts in timestamps if ts > cutoff]
        
        # Add current timestamp
        timestamps.append(now)
        
        count = len(timestamps)
        is_spam = count > 20
        
        return is_spam, count

    def record_chat_activity(
        self,
        guild_id: int,
        user_id: int,
        is_bot: bool,
        content: str | None,
        now: datetime | None = None,
    ) -> bool:
        """Record chat activity and determine if bot should jump into conversation.
        
        Returns True if the bot should send a reply (active conversation detected).
        
        Criteria:
        - At least 6 messages in 20 seconds
        - At least 3 unique users
        - 45 second cooldown between triggers
        - 35% random chance when criteria met
        """
        if now is None:
            now = datetime.utcnow()

        # Skip bots and commands
        if is_bot:
            return False
        if content and content.startswith(self.bot_prefix):
            return False

        if _USE_RUST:
            return self._rust_tracker.record_chat_activity(
                guild_id, user_id, now.timestamp()
            )

        # Python fallback
        window = self._chat_activity[guild_id]
        window.append((now, user_id))

        # Clean messages older than 30 seconds
        while window and (now - window[0][0]) > timedelta(seconds=30):
            window.popleft()

        # Check activity in last 20 seconds
        active_window = [(ts, uid) for ts, uid in window if (now - ts) <= timedelta(seconds=20)]
        unique_users = {uid for _, uid in active_window}

        if len(active_window) < 6 or len(unique_users) < 3:
            return False

        # Check cooldown
        last_trigger = self._chat_cooldowns.get(guild_id)
        if last_trigger and (now - last_trigger) < timedelta(seconds=45):
            return False

        # Random chance to trigger
        if random.random() < 0.35:
            self._chat_cooldowns[guild_id] = now
            return True

        return False

    def clear_user(self, user_id: int) -> None:
        """Clear tracking data for a user."""
        if _USE_RUST:
            self._rust_tracker.clear_user(user_id)
        else:
            self._message_timestamps.pop(user_id, None)

    def clear_guild(self, guild_id: int) -> None:
        """Clear tracking data for a guild."""
        if _USE_RUST:
            self._rust_tracker.clear_guild(guild_id)
        else:
            self._chat_activity.pop(guild_id, None)
            self._chat_cooldowns.pop(guild_id, None)
