# Use slim-buster for smaller size but still Debian-based
FROM python:3.9-slim-buster

# Install system dependencies and Chrome
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg \
    xvfb \
    libmagic1 \
    libgconf-2-4 \
    libxss1 \
    libnss3 \
    libgbm1 \
    libasound2 \
    libxrandr2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/logs

# Set up Chrome options for running in container
ENV CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/lib/chromium/ \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DEBUG=false \
    LOG_LEVEL=INFO \
    PORT=8000 \
    WORKERS=4

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . /app/

# Create non-root user for security
RUN useradd -m -u 1000 scraper \
    && chown -R scraper:scraper /app

# Switch to non-root user
USER scraper

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["python", "main.py"]
