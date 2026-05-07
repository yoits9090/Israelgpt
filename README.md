# Israel GPT

Israel GPT is a minimal Discord chatbot. It does one thing: replies conversationally when users DM it or mention it in a server.

## What it does
- Responds to direct messages.
- Responds when mentioned in a server channel.
- Uses recent visible channel context to keep replies relevant.
- Keeps lightweight per-user chat memory in SQLite.

## What it does not do
- No moderation.
- No music or voice features.
- No tickets, economy, levels, roles, audits, metrics, queues, or server automation.
- No slash commands or custom command suite.

## Requirements
- Python 3.11+
- A Discord bot token
- A Groq API key

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_TOKEN="your-discord-token"
export GROQ_API="your-groq-api-key"
python src/main.py
```

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `DISCORD_TOKEN` | Discord bot token | Required |
| `GROQ_API` | Groq API key | Required for replies |
| `CHATBOT_MODEL` | Groq chat model | `llama-3.1-8b-instant` |
| `CHATBOT_MAX_TOKENS` | Maximum reply tokens | `512` |
| `CHATBOT_TEMPERATURE` | Reply creativity | `0.7` |
| `DATABASE_URL` | SQLite memory database URL | `sqlite:///data/israelgpt.db` |

## Running

```bash
python src/main.py
```

Invite the bot to a server, mention it in a channel, or send it a DM. It will only chat back; it will not manage the server.
