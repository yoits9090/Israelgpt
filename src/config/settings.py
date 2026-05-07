"""Environment variables and constants for the Israel GPT chatbot."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API")
CHATBOT_MODEL = os.getenv("CHATBOT_MODEL", "llama-3.1-8b-instant")
CHATBOT_MAX_TOKENS = int(os.getenv("CHATBOT_MAX_TOKENS", "512"))
CHATBOT_TEMPERATURE = float(os.getenv("CHATBOT_TEMPERATURE", "0.7"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{Path('data') / 'israelgpt.db'}")
