# Israeli Discord Bot 🇮🇱

A discord bot with a dash of chutzpah! This bot features basic moderation, auto-roles, and server management, all with an Israeli theme.

## Features

- **Moderation**:
  - `!ban [user] [reason]`: Bans a user ("Oy vey, you've been banned").
  - `!kick [user] [reason]`: Kicks a user ("Yalla bye").
  - `!clear [amount]`: Clears messages ("Cleaning up the balagan").
- **Auto Roles**: Automatically assigns a role (default: "Member") when a new user joins.
- **Server Info**: `!info` command to show server stats.
- **Events**:
  - Welcome message: "Shalom [user]!"
  - Activity status: Playing "Shesh Besh".

## Setup

### Prerequisites
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
   - Optionally change `AUTO_ROLE_NAME` to the role you want assigned on join.

5. **Run the bot**:
   ```bash
   python bot.py
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
   - `EC2_HOST`: Public IP or hostname of your EC2 instance.
   - `EC2_USERNAME`: SSH username (e.g., `ubuntu`).
   - `EC2_SSH_KEY`: Private SSH key (PEM format) for the instance.

### EC2 Setup
1. Ensure Docker is installed on your EC2 instance.
2. Create the directory `/home/ubuntu/israelgpt`.
3. **Important**: Create a `.env` file in `/home/ubuntu/israelgpt/.env` with your `DISCORD_TOKEN` (since it's not in the repo).

The workflow (`.github/workflows/deploy.yml`) will automatically:
1. Copy the repository files to the EC2 instance.
2. Build the Docker image on the server.
3. Restart the bot container.
