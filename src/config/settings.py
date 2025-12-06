"""Environment variables and constants for IsraelGPT."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Discord bot token
TOKEN = os.getenv("DISCORD_TOKEN")

# Role IDs
AUTO_ROLE_ID = int(os.getenv("AUTO_ROLE_ID", "0"))
GEM_ROLE_ID = 1441889921102118963

# Gem system
GEM_TRIGGER_PHRASE = "/wearegems"

# Audit logging
AUDIT_LOG_CHANNEL_ID = 1442833351307300874

# Voice channels
DEFAULT_VOICE_CHANNEL_IDS = {1441899961225576458, 1441877144413278228}
DEFAULT_PRIVATE_VOICE_LOBBY_ID = 1444420249264066591
VOICE_TRANSCRIBE_INTERVAL = 5

# Guild configuration
GUILD_CONFIG_PATH = Path("guild_configs.json")
PRIMARY_GUILD_ID = int(os.getenv("PRIMARY_GUILD_ID", "0"))

# Marketplace/Tickets
MARKETPLACE_CHANNEL_ID = 1441901428800229376
MARKETPLACE_STAFF_ROLE_IDS = [1441882323938316379, 1441878991370850335]

# LLM API
GROQ_API_KEY = os.getenv("GROQ_API")

# Observability
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
