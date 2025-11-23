FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg for audio streaming and Node.js for autobumper
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs npm && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Node dependencies for autobumper
WORKDIR /app/autobumper
RUN npm install --only=production

# Return to app root and create data directory for persistent storage
WORKDIR /app
RUN mkdir -p /app/data

CMD ["python", "src/bot.py"]
