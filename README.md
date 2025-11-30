# Israeli Discord Bot 🇮🇱

A discord bot with a dash of chutzpah! This bot features basic moderation, auto-roles, and server management, all with an Israeli theme.

## Features

- **Moderation**:
  - `,ban [user] [reason]` (alias: `,b`): Bans a user ("Oy vey, you've been banned").
  - `,kick [user] [reason]` (alias: `,k`): Kicks a user ("Yalla bye").
  - `,clear [amount]` (aliases: `,c`, `,purge`): Clears messages ("Cleaning up the balagan").
  - `,role [@user] [role_id/name]` (alias: `,r`): Toggle role on/off for a user.

- **Auto Roles**: 
  - Automatically assigns "Unpolished" role when new users join.
  - Grants "Gem" role (image perms) at 150 messages.

- **Leveling & Leaderboard**:
  - `,rank [@user]` (aliases: `,level`, `,stats`): View user stats and level.
  - `,leaderboard` (aliases: `,lb`, `,top`): Top 10 users by message count.
  - 5 XP per message, 100 XP per level.

- **Anti-Nuke Protection**: 
  - Automatically deletes messages from users spamming >20 messages in 10 seconds.

- **Server Info**: `,info` command to show server stats.

- **Avatars & Banners**:
  - `,avatar [@user]` (aliases: `,av`, `,pfp`): Shows user's avatar.
  - `,banner [@user]`: Shows user's banner (if they have one).
  - `,servericon` (alias: `,guildicon`): Shows server icon.
  - `,serverbanner` (alias: `,guildbanner`): Shows server banner.

- **Music Streaming** (yt-dlp powered):
  - `,play [url/search]` (alias: `,p`): Play audio from YouTube or search.
  - `,pause`: Pause current track.
  - `,resume`: Resume playback.
  - `,skip`: Skip current track.
  - `,stop`: Stop playback and clear queue.
  - `,leave` (aliases: `,disconnect`, `,dc`): Leave voice channel.

- **Events**:
  - Welcome message: "Shalom [user]!"
  - Activity status: Playing "Shesh Besh".

## Setup

### Prerequisite\
- Python 3.8+
- A Discord Bot Token (from the [Discord Developer Portal](https://discord.com/developers/applications))

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd Israelgpt
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your `DISCORD_TOKEN`.
   - Add `AUTO_ROLE_ID` with the role ID you want assigned on join.

5. **Run the bot**:
   ```bash
   python src/bot.py
   ```

## Docker

To run the bot using Docker:

1. **Build the image**:
   ```bash
   docker build -t israelgpt-bot .
   ```

2. **Run the container**:
   ```bash
   docker run -d --env-file .env israelgpt-bot
   ```

## Deployment

The bot is deployed to an EC2 instance using GitHub Actions.

### GitHub Actions Setup
1. Go to your repository **Settings** > **Secrets and variables** > **Actions**.
2. Add the following repository secrets:
   - `DISCORD_TOKEN`: Your Discord bot token.
   - `AUTO_ROLE_ID`: Role ID to assign on member join.
   - `EC2_HOST`: Public IP or hostname of your EC2 instance.
   - `EC2_USERNAME`: SSH username (e.g., `ubuntu`).
   - `EC2_SSH_KEY`: Private SSH key (PEM format) for the instance.

### EC2 Setup
1. Install Docker on your EC2 instance:
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io
   sudo systemctl start docker
   sudo systemctl enable docker
   ```
2. Create the directory `/home/ubuntu/israelgpt`.

The workflow (`.github/workflows/deploy.yml`) will automatically:
1. Copy the repository files to the EC2 instance.
2. Create the `.env` file from GitHub Secrets.
3. Build the Docker image on the server.
4. Restart the bot container.
