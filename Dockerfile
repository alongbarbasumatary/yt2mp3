FROM python:3.11-slim

# Install system deps: ffmpeg for yt-dlp merging, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY app.py .

# Persistent volume for downloads + session
VOLUME ["/app/downloads", "/app/session"]

# Render sets PORT env var — bot uses long-polling so we just expose a
# tiny healthcheck HTTP server on that port (see app.py entrypoint)
ENV PORT=10000

CMD ["python", "-u", "app.py"]
