"""Voice recording cog - auto-join VCs, silently record and transcribe."""

import asyncio
import io
import wave
from typing import Optional, Dict, Set

import discord
from discord.ext import commands

from services.transcription import (
    VoiceRecordingSession,
    get_or_create_session,
    end_session,
)


class AudioSink(discord.sinks.Sink):
    """Custom audio sink that collects audio per user."""

    def __init__(self):
        super().__init__()
        self.audio_data: Dict[int, io.BytesIO] = {}

    def write(self, data, user):
        if user is None:
            return
        user_id = user.id if hasattr(user, 'id') else user
        
        if user_id not in self.audio_data:
            self.audio_data[user_id] = io.BytesIO()
        self.audio_data[user_id].write(data)

    def get_user_audio(self, user_id: int) -> Optional[bytes]:
        """Get collected audio for a user and clear the buffer."""
        if user_id in self.audio_data:
            data = self.audio_data[user_id].getvalue()
            self.audio_data[user_id] = io.BytesIO()  # Reset
            return data if len(data) > 1000 else None
        return None

    def cleanup(self):
        self.audio_data.clear()


class VoiceRecordCog(commands.Cog):
    """Automatic voice recording - joins VCs silently and transcribes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_sinks: Dict[int, AudioSink] = {}  # channel_id -> sink
        self.recording_tasks: Dict[int, asyncio.Task] = {}  # channel_id -> task
        self.voice_clients: Dict[int, discord.VoiceClient] = {}  # channel_id -> vc
        self.user_names: Dict[int, str] = {}
        self.ignored_channels: Set[int] = set()  # Channels to not auto-join

    async def _start_recording(self, channel: discord.VoiceChannel):
        """Silently join a voice channel and start recording."""
        channel_id = channel.id
        guild_id = channel.guild.id

        # Already recording this channel
        if channel_id in self.active_sinks:
            return

        try:
            # Connect silently
            voice_client = await channel.connect()
            self.voice_clients[channel_id] = voice_client

            # Start session
            session = get_or_create_session(guild_id, channel_id)
            session.start()

            # Create sink and start recording
            sink = AudioSink()
            self.active_sinks[channel_id] = sink

            # Cache user names
            for member in channel.members:
                if not member.bot:
                    self.user_names[member.id] = member.display_name

            # Start recording
            voice_client.start_recording(sink, self._on_recording_done, channel)

            # Start periodic transcription
            self.recording_tasks[channel_id] = asyncio.create_task(
                self._periodic_transcription(channel_id, guild_id, sink, session)
            )

        except Exception as e:
            print(f"Failed to start recording in {channel.name}: {e}")

    async def _stop_recording(self, channel_id: int, guild_id: int):
        """Stop recording and leave the channel."""
        # Cancel transcription task
        if channel_id in self.recording_tasks:
            self.recording_tasks[channel_id].cancel()
            del self.recording_tasks[channel_id]

        # Stop recording
        if channel_id in self.voice_clients:
            vc = self.voice_clients[channel_id]
            try:
                vc.stop_recording()
            except:
                pass
            try:
                await vc.disconnect()
            except:
                pass
            del self.voice_clients[channel_id]

        # End session
        end_session(guild_id, channel_id)

        # Cleanup sink
        if channel_id in self.active_sinks:
            self.active_sinks[channel_id].cleanup()
            del self.active_sinks[channel_id]

    async def _on_recording_done(self, sink: AudioSink, channel: discord.VoiceChannel):
        """Callback when recording stops - final transcription pass."""
        session = get_or_create_session(channel.guild.id, channel.id)
        
        for user_id, audio_buffer in sink.audio_data.items():
            audio_bytes = audio_buffer.getvalue()
            if len(audio_bytes) > 1000:
                username = self.user_names.get(user_id, str(user_id))
                wav_data = self._pcm_to_wav(audio_bytes)
                await session.process_audio(wav_data, user_id, username)

    async def _periodic_transcription(
        self,
        channel_id: int,
        guild_id: int,
        sink: AudioSink,
        session: VoiceRecordingSession,
    ):
        """Periodically transcribe collected audio."""
        try:
            while True:
                await asyncio.sleep(10)

                if channel_id not in self.active_sinks:
                    break

                for user_id in list(sink.audio_data.keys()):
                    audio_bytes = sink.get_user_audio(user_id)
                    if audio_bytes and len(audio_bytes) > 5000:
                        username = self.user_names.get(user_id, str(user_id))
                        wav_data = self._pcm_to_wav(audio_bytes)
                        await session.process_audio(wav_data, user_id, username)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Transcription error: {e}")

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Convert raw PCM audio to WAV format for Whisper."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(48000)
            wav_file.writeframes(pcm_data)
        return wav_buffer.getvalue()

    def _get_human_count(self, channel: discord.VoiceChannel) -> int:
        """Count non-bot members in a voice channel."""
        return sum(1 for m in channel.members if not m.bot)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Auto-join when users join VC, leave when empty."""
        # Ignore bot's own state changes
        if member.bot:
            return

        # User joined a channel
        if after.channel and after.channel.id not in self.ignored_channels:
            self.user_names[member.id] = member.display_name
            
            # If not already recording and has users, join
            if after.channel.id not in self.active_sinks:
                if self._get_human_count(after.channel) >= 1:
                    await asyncio.sleep(2)  # Small delay before joining
                    await self._start_recording(after.channel)

        # User left a channel
        if before.channel:
            channel_id = before.channel.id
            guild_id = before.channel.guild.id

            # If we're recording and no humans left, leave
            if channel_id in self.active_sinks:
                if self._get_human_count(before.channel) == 0:
                    await self._stop_recording(channel_id, guild_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceRecordCog(bot))
