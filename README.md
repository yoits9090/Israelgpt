# IsraelGPT 🇮🇱

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-5865F2.svg)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Discord](https://img.shields.io/discord/YOUR_SERVER_ID?color=5865F2&label=Discord&logo=discord&logoColor=white)](https://discord.gg/xXwfcZ6DT9)

A Discord bot with a dash of chutzpah. Moderation, music, economy simulation, leveling, and more.

## Features

- **Moderation** — Ban, kick, mute, role management, anti-spam
- **Music** — YouTube playback via yt-dlp
- **Economy** — Jobs, businesses, properties, class system, nation simulation
- **Leveling** — XP tracking, leaderboards, auto-roles
- **Government** — Elections, taxes, laws, political parties

## Quick Start

```bash
# Clone & setup
git clone https://github.com/yoits9090/Israelgpt.git
cd Israelgpt
cp .env.example .env  # Add your DISCORD_TOKEN

# Run with Docker
docker build -t israelgpt-bot .
docker run -d --env-file .env israelgpt-bot
```

## Configuration

Set these in `.env`:
- `DISCORD_TOKEN` — Bot token from [Discord Developer Portal](https://discord.com/developers/applications)
- `AUTO_ROLE_ID` — Role assigned on member join
- `PRIMARY_GUILD_ID` — Main server ID
- `METRICS_PORT` — Port for Prometheus `/metrics` endpoint (default `8000`)

## Monitoring

- Prometheus metrics are exposed on `http://<host>:METRICS_PORT/metrics`.
- Default port is `8000`; change via `METRICS_PORT` env var.
- In Docker, port `8000` is exposed (map it with `-p 8000:8000` or your chosen port).
- Counters include messages, commands, spam detections, errors, and LLM requests.

## Contributing

PRs welcome. Please open an issue first to discuss major changes.

## License

MIT
