# Guildest

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-5865F2.svg)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A professional Discord bot for moderation, music, economy simulation, leveling, and more.

## Architecture
- **Gateway** (`src/main.py`) handles Discord events, spam protection, leveling, and pushes heavy work (LLM replies, safety scans) onto Redis.
- **Queue** (`taskqueue/`) uses Redis lists plus per-job result keys (`<namespace>:tasks`, `<namespace>:results:<job>`).
- **Worker** (`microservices/worker/main.py`) consumes queued jobs and returns results to the gateway.
- **Command sync / status** microservices remain available for slash-command sync and deployment notifications.

## Requirements
- Python 3.11+, Redis reachable at `REDIS_URL`
- ffmpeg for voice features (already installed in the Docker image)
- Optional: `psycopg` if/when moving to Postgres (see migration prep below)

## Quick Start
```bash
# Clone & configure
git clone https://github.com/yoits9090/Guildest.git
cd Guildest
cp .env.example .env  # fill in DISCORD_TOKEN and other IDs

# Start Redis (example)
docker run -d --name guildest-redis -p 6379:6379 redis:7

# Run gateway and worker locally
python src/main.py
python microservices/worker/main.py
```

### Docker
```bash
docker build -t guildest .
# Gateway
docker run -d --env-file .env -e SERVICE=gateway --name guildest-gateway guildest
# Worker
docker run -d --env-file .env -e SERVICE=worker --name guildest-worker --link guildest-redis guildest
```

## Configuration
Key environment variables:
- `DISCORD_TOKEN` – Bot token
- `AUTO_ROLE_ID` – Default role on join
- `PRIMARY_GUILD_ID` – Main guild ID (optional)
- `METRICS_PORT` – Prometheus port (default `8000`)
- `REDIS_URL` / `TASK_NAMESPACE` – Queue backend settings
- `DATABASE_URL` – Defaults to SQLite path; set to `postgres://...` only after migrating SQL
- `ALLOW_EXPERIMENTAL_POSTGRES` – Guard flag for opting into the Postgres path

## Postgres migration prep
- DB connections now route through `src/db/engine.py` to centralize backend choice.
- Queries still use SQLite-style `?` placeholders; switching to Postgres requires converting them to `%s` (or using a query builder) and enabling `ALLOW_EXPERIMENTAL_POSTGRES=true`.
- Plan: introduce migrations, consolidate per-feature SQLite files into a single Postgres schema, and keep worker-friendly async access for high-traffic paths.

## Contributing
PRs welcome. Please open an issue first to discuss major changes.

## License
MIT
