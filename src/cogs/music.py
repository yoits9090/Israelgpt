"""Music playback commands cog."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Tuple

import discord
from discord.ext import commands
import yt_dlp


def _get_ytdl_options() -> dict:
    """Build yt-dlp options with cookie support if available."""
    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "auto",
        "source_address": "0.0.0.0",
        # Use mobile client to avoid some bot detection
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }
    
    # Check for cookies file (place cookies.txt in /app/data/)
    cookie_paths = [
        Path("/app/data/cookies.txt"),
        Path("data/cookies.txt"),
        Path(os.getenv("YT_COOKIES_PATH", "")),
    ]
    
    for cookie_path in cookie_paths:
        if cookie_path and cookie_path.exists():
            options["cookiefile"] = str(cookie_path)
            break
    
    # Check for OAuth cache
    cache_dir = Path("/app/data/.yt-dlp-cache")
    if cache_dir.exists():
        options["cachedir"] = str(cache_dir)
    
    return options


YTDL_OPTIONS = _get_ytdl_options()

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicCog(commands.Cog, name="Music"):
    """Music playback commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.music_queue: Dict[int, List[Tuple[str, str]]] = {}

    def _play_next(self, ctx: commands.Context):
        """Play the next song in the queue."""
        if ctx.guild.id in self.music_queue and self.music_queue[ctx.guild.id]:
            url, title = self.music_queue[ctx.guild.id].pop(0)
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"Now playing: **{title}** 🎵"),
                self.bot.loop,
            )

    @commands.hybrid_command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, url: str):
        """Play audio from YouTube."""
        if not ctx.author.voice:
            await ctx.send("Chaver, you need to be in a voice channel!")
            return

        channel = ctx.author.voice.channel

        if ctx.voice_client is None:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)

        await ctx.send(f"Nu, searching for: {url}...")

        try:
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    info = info["entries"][0]

                audio_url = info["url"]
                title = info.get("title", "Unknown")

                source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)

                if ctx.voice_client.is_playing():
                    if ctx.guild.id not in self.music_queue:
                        self.music_queue[ctx.guild.id] = []
                    self.music_queue[ctx.guild.id].append((audio_url, title))
                    await ctx.send(f"Added to queue: **{title}**")
                else:
                    ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
                    await ctx.send(f"Now playing: **{title}** 🎵")
        except Exception as e:
            await ctx.send(f"Unable to play audio: {e}")

    @commands.hybrid_command(name="pause")
    async def pause(self, ctx: commands.Context):
        """Pause the current track."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused the music, hold on...")
        else:
            await ctx.send("Nothing is playing right now.")

    @commands.hybrid_command(name="resume")
    async def resume(self, ctx: commands.Context):
        """Resume paused playback."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Yalla, resuming!")
        else:
            await ctx.send("Nothing is paused!")

    @commands.hybrid_command(name="skip")
    async def skip(self, ctx: commands.Context):
        """Skip the current track."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipping this one...")
        else:
            await ctx.send("Nothing is playing!")

    @commands.hybrid_command(name="stop")
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue."""
        if ctx.voice_client:
            if ctx.guild.id in self.music_queue:
                self.music_queue[ctx.guild.id].clear()
            ctx.voice_client.stop()
            await ctx.send("Stopped the music.")
        else:
            await ctx.send("I'm not in a voice channel!")

    @commands.hybrid_command(name="leave", aliases=["disconnect", "dc"])
    async def leave(self, ctx: commands.Context):
        """Disconnect from voice channel."""
        if ctx.voice_client:
            if ctx.guild.id in self.music_queue:
                self.music_queue[ctx.guild.id].clear()
            await ctx.voice_client.disconnect()
            await ctx.send("Leaving the voice channel.")
        else:
            await ctx.send("I'm not in a voice channel, bubbeleh!")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
