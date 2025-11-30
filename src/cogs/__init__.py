"""Discord.py Cogs for IsraelGPT commands."""

from .moderation import ModerationCog
from .community import CommunityCog
from .music import MusicCog
from .voice import VoiceCog
from .admin import AdminCog
from .tickets import TicketsCog

__all__ = [
    "ModerationCog",
    "CommunityCog",
    "MusicCog",
    "VoiceCog",
    "AdminCog",
    "TicketsCog",
]


async def setup_all_cogs(bot):
    """Load all cogs into the bot."""
    await bot.add_cog(ModerationCog(bot))
    await bot.add_cog(CommunityCog(bot))
    await bot.add_cog(MusicCog(bot))
    await bot.add_cog(VoiceCog(bot))
    await bot.add_cog(AdminCog(bot))
    await bot.add_cog(TicketsCog(bot))
