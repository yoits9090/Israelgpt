"""Voice recording cog (auto-join disabled, database support retained)."""

import asyncio
import io
import wave
from typing import Optional, Dict, Set

import discord
from discord.ext import commands
from discord.ext import voice_recv

from services.transcription import (
    VoiceRecordingSession,
    get_or_create_session,
    end_session,
)


class AudioSink(voice_recv.AudioSink):
    """Custom audio sink that collects audio per user."""

    def __init__(self):
        super().__init__()
        self.audio_data: Dict[int, io.BytesIO] = {}

    def wants_opus(self) -> bool:
        """We want decoded PCM data, not opus."""
        return False

    def write(self, user, data: voice_recv.VoiceData):
        """Called when audio data is received."""
        if user is None:
            return
        user_id = user.id if hasattr(user, 'id') else user
        
        if user_id not in self.audio_data:
            self.audio_data[user_id] = io.BytesIO()
        # data.pcm contains the decoded PCM audio
        if data.pcm:
            self.audio_data[user_id].write(data.pcm)

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
    """Automatic voice recording (joining disabled; database hooks intact)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_sinks: Dict[int, AudioSink] = {}  # channel_id -> sink
        self.recording_tasks: Dict[int, asyncio.Task] = {}  # channel_id -> task
        self.voice_clients: Dict[int, voice_recv.VoiceRecvClient] = {}  # channel_id -> vc
        self.user_names: Dict[int, str] = {}
        self.ignored_channels: Set[int] = set()  # Channels to not auto-join
        self.enabled = False

    async def _start_recording(self, channel: discord.VoiceChannel):
        """Silently join a voice channel and start recording."""
        if not self.enabled:
            return
        channel_id = channel.id
        guild_id = channel.guild.id

        # Already recording this channel
        if channel_id in self.active_sinks:
            return

        try:
            # Connect using VoiceRecvClient for receiving audio
            voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
            self.voice_clients[channel_id] = voice_client

            # Start session
            session = get_or_create_session(guild_id, channel_id)
            session.start()

            # Create sink and start listening
            sink = AudioSink()
            self.active_sinks[channel_id] = sink

            # Cache user names
            for member in channel.members:
                if not member.bot:
                    self.user_names[member.id] = member.display_name

            # Start listening (voice_recv API)
            voice_client.listen(sink, after=self._on_listen_error)

            # Start periodic transcription
            self.recording_tasks[channel_id] = asyncio.create_task(
                self._periodic_transcription(channel_id, guild_id, sink, session)
            )

        except Exception as e:
            print(f"Failed to start recording in {channel.name}: {e}")

    async def _stop_recording(self, channel_id: int, guild_id: int):
        """Stop recording and leave the channel."""
        if not self.enabled:
            return
        # Cancel transcription task
        if channel_id in self.recording_tasks:
            self.recording_tasks[channel_id].cancel()
            del self.recording_tasks[channel_id]

        # Stop listening and disconnect
        if channel_id in self.voice_clients:
            vc = self.voice_clients[channel_id]
            try:
                vc.stop_listening()
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

    def _on_listen_error(self, error: Optional[Exception]):
        """Callback when listening stops or errors."""
        if error:
            print(f"Voice receive error: {error}")

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
        """Voice recording is disabled; ignore events."""
        return


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceRecordCog(bot))
