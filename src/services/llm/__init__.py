"""LLM service module for AI-powered features."""

from .client import get_client
from .chat import generate_israeli_reply
from .safety import classify_message_safety

__all__ = ["get_client", "generate_israeli_reply", "classify_message_safety"]
