"""Voice transcription service using Groq Whisper Turbo."""

import asyncio
import io
from typing import Optional
from dataclasses import dataclass

from config import GROQ_API_KEY
from db.transcriptions import save_transcription, start_voice_session, end_voice_session

# Try to use Rust database writer if available
try:
    from israelgpt_core import DatabaseWriter
    _db_writer: Optional["DatabaseWriter"] = DatabaseWriter()
    _USE_RUST_DB = True
except ImportError:
    _db_writer = None
    _USE_RUST_DB = False

# Groq client for Whisper
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


@dataclass
class TranscriptionResult:
    text: str
    duration_secs: float
    user_id: int
    username: str


async def transcribe_audio(audio_data: bytes, filename: str = "audio.wav") -> Optional[str]:
    """
    Transcribe audio bytes using Groq Whisper Turbo.
    Returns the transcribed text or None if failed.
    """
    client = _get_groq_client()
    if not client:
        return None

    try:
        # Run in thread to avoid blocking
        def _transcribe():
            audio_file = io.BytesIO(audio_data)
            audio_file.name = filename
            
            response = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                response_format="text",
            )
            return response

        result = await asyncio.to_thread(_transcribe)
        return result.strip() if result else None

    except Exception as e:
        print(f"Transcription failed: {e}")
        return None


def queue_transcription_save(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
    username: Optional[str] = None,
    duration_secs: Optional[float] = None,
):
    """
    Queue a transcription to be saved to the database.
    Uses Rust async writer if available, otherwise saves directly.
    """
    if _USE_RUST_DB and _db_writer:
        # Queue for async write via Rust
        _db_writer.queue_transcription(
            guild_id,
            channel_id,
            user_id,
            content,
            username or "",
            duration_secs or 0.0,
        )
    else:
        # Direct Python write (blocks briefly)
        save_transcription(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            content=content,
            username=username,
            duration_secs=duration_secs,
        )


class VoiceRecordingSession:
    """Manages a voice recording session in a channel."""

    def __init__(self, guild_id: int, channel_id: int):
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.session_id: Optional[int] = None
        self.transcription_count = 0
        self.is_active = False

    def start(self):
        """Start the recording session."""
        self.session_id = start_voice_session(self.guild_id, self.channel_id)
        self.is_active = True
        self.transcription_count = 0

    def stop(self):
        """Stop the recording session."""
        if self.session_id:
            end_voice_session(self.session_id, self.transcription_count)
        self.is_active = False

    async def process_audio(self, audio_data: bytes, user_id: int, username: str) -> Optional[str]:
        """
        Process audio from a user: transcribe and save.
        Returns the transcribed text or None.
        """
        if not self.is_active:
            return None

        # Transcribe the audio
        text = await transcribe_audio(audio_data)
        if not text or len(text.strip()) < 2:
            return None

        # Queue the save (non-blocking with Rust)
        queue_transcription_save(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            user_id=user_id,
            content=text,
            username=username,
            duration_secs=len(audio_data) / 48000,  # Rough estimate
        )

        self.transcription_count += 1
        return text


# Global session manager
_active_sessions: dict[int, VoiceRecordingSession] = {}


def get_or_create_session(guild_id: int, channel_id: int) -> VoiceRecordingSession:
    """Get or create a recording session for a channel."""
    key = (guild_id, channel_id)
    if key not in _active_sessions:
        session = VoiceRecordingSession(guild_id, channel_id)
        _active_sessions[key] = session
    return _active_sessions[key]


def end_session(guild_id: int, channel_id: int):
    """End and remove a recording session."""
    key = (guild_id, channel_id)
    if key in _active_sessions:
        _active_sessions[key].stop()
        del _active_sessions[key]
