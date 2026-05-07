#!/usr/bin/env python3
"""Israel GPT Discord chatbot entry point."""

import asyncio
import sys

from config import TOKEN
from core import bot, setup_events


async def main() -> None:
    """Initialize and run the chatbot."""
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in the environment")
        sys.exit(1)

    setup_events(bot)

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
