#!/usr/bin/env python3
"""Guildest Discord Bot - Entry Point.

This is the main entry point for the bot. It sets up the bot instance,
loads all cogs, and starts the event loop.

Directory Structure:
    src/
    ├── main.py              # This file - entry point
    ├── config/              # Configuration and settings
    ├── core/                # Bot instance and event handlers
    ├── cogs/                # Command modules (Discord.py Cogs)
    ├── services/            # Business logic services
    ├── utils/               # Helper utilities
    ├── db/                  # Database modules
    └── rust_core/           # Rust-accelerated functions (optional)
"""

import asyncio
import sys

from config import TOKEN, METRICS_PORT
from core import bot, setup_events
from cogs import setup_all_cogs
from observability import start_metrics_server
from taskqueue import get_task_queue


async def main():
    """Initialize and run the bot."""
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env")
        sys.exit(1)

    # Ensure the queue backend is reachable before starting the gateway
    try:
        await get_task_queue().redis.ping()
    except Exception as exc:
        print(f"Error: Redis queue is unreachable ({exc}). Start Redis before running the gateway.")
        sys.exit(1)

    # Start Prometheus metrics server (runs in background thread)
    start_metrics_server(METRICS_PORT)

    # Setup event handlers
    setup_events(bot)

    # Load all cogs
    async with bot:
        await setup_all_cogs(bot)
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
