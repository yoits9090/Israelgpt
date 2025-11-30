"""Discord bot instance and intents configuration."""

import discord
from discord.ext import commands


# Intents configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Bot instance
bot = commands.Bot(command_prefix=",", intents=intents)
bot.remove_command("help")  # We provide our own help command
