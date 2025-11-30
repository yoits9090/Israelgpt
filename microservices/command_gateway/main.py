"""Command Gateway microservice.

This service loads all hybrid commands and syncs them as Discord application
commands without running the full bot event stack. It can be invoked as a
one-shot job (e.g., in CI/CD) to keep slash commands in sync with the latest
cog implementations while preserving the legacy prefix behaviour.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands


# Ensure repo src/ is importable when running from repo root or packaged image
REPO_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cogs import setup_all_cogs  # noqa: E402
from config import TOKEN  # noqa: E402


class CommandGateway(commands.Bot):
    """Minimal bot instance dedicated to application-command sync."""

    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(command_prefix=",", intents=intents)
        self._synced = False

    async def setup_hook(self) -> None:
        await setup_all_cogs(self)

    async def on_ready(self) -> None:
        if self._synced:
            return

        try:
            synced = await self.tree.sync()
            print(f"Command gateway synced {len(synced)} application commands.")
        except Exception as e:
            print(f"Command gateway failed to sync: {e}")
        finally:
            self._synced = True
            await self.close()


async def _run_gateway(token: str) -> None:
    bot = CommandGateway()
    await bot.start(token)


def main() -> None:
    token = TOKEN or os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required to sync application commands")

    asyncio.run(_run_gateway(token))


if __name__ == "__main__":
    main()
