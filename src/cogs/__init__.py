"""Discord.py Cogs for Guildest commands."""

from .moderation import ModerationCog
from .community import CommunityCog
from .music import MusicCog
from .voice import VoiceCog
from .admin import AdminCog
from .tickets import TicketsCog
from .voice_record import VoiceRecordCog
from .economy import EconomyCog
from .government import GovernmentCog

__all__ = [
    "ModerationCog",
    "CommunityCog",
    "MusicCog",
    "VoiceCog",
    "AdminCog",
    "TicketsCog",
    "VoiceRecordCog",
    "EconomyCog",
    "GovernmentCog",
]


async def setup_all_cogs(bot):
    """Load all cogs into the bot."""
    await bot.add_cog(ModerationCog(bot))
    await bot.add_cog(CommunityCog(bot))
    await bot.add_cog(MusicCog(bot))
    await bot.add_cog(VoiceCog(bot))
    await bot.add_cog(AdminCog(bot))
    await bot.add_cog(TicketsCog(bot))
    await bot.add_cog(VoiceRecordCog(bot))
    await bot.add_cog(EconomyCog(bot))
    await bot.add_cog(GovernmentCog(bot))
