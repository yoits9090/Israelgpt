FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg for audio streaming
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for persistent storage
RUN mkdir -p /app/data

CMD ["python", "src/bot.py"]
