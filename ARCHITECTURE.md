# Israel GPT Architecture

Israel GPT is intentionally small: the Discord gateway is the chatbot, and there are no background workers, queues, command suites, or server automation features in the runtime path.

## Runtime flow
1. `src/main.py` validates `DISCORD_TOKEN`, registers chatbot events, and starts Discord.
2. `src/core/events.py` listens for direct messages and server mentions only.
3. `src/services/llm/chat.py` fetches recent visible Discord context, builds a compact prompt, calls Groq, and stores lightweight conversation memory in SQLite.
4. The bot sends the generated answer back to the DM or mentioned server message.

## Active components
- **Discord bot**: `src/core/bot.py` configures the minimal message-content intent required for chat.
- **Chat events**: `src/core/events.py` contains the chatbot-only event pipeline.
- **LLM service**: `src/services/llm/` wraps Groq chat completions.
- **Chat memory**: `src/db/llm.py` stores user/assistant turns in SQLite.

## Explicitly out of scope
- Moderation and audit logging.
- Economy, levels, roles, tickets, music, voice, and government features.
- Redis queues, workers, metrics, slash-command sync, and status notifiers.
- Rust acceleration and Node services.
