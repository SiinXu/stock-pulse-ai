# syntax=docker/dockerfile:1.7

# ===================================
# A-shares Watchlist Analysis System - Docker image
# ===================================
# Multi-stage build: frontend packaging + backend running

FROM node:22-slim AS web-builder

WORKDIR /app/apps/dsa-web

COPY apps/dsa-web/package.json apps/dsa-web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY apps/dsa-web/ ./
RUN npm run build

# Pin to bookworm: wkhtmltopdf was removed from Debian testing (2025)
FROM python:3.11-slim-bookworm

# Set the working directory
WORKDIR /app

# Set the time zone to Shanghai
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies (wkhtmltopdf includes wkhtmltoimage, for Markdown to image conversion Issue #289).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    git \
    gosu \
    wkhtmltopdf \
    fontconfig \
    libjpeg62-turbo \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID 1000)
RUN groupadd -g 1000 dsa && \
    useradd -u 1000 -g dsa -m dsa

# Copy dependency files
COPY requirements.txt .

# Install Python dependencies.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# Copy application code
COPY *.py ./
COPY api/ ./api/
COPY data_provider/ ./data_provider/
COPY bot/ ./bot/
COPY src/ ./src/
COPY strategies/ ./strategies/
COPY --from=web-builder /app/static ./static/
COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Verify the bundled AlphaSift adapter from requirements.
RUN python -c "import alphasift.dsa_adapter"

# Ensure the data directory exists and is authorized for non-root users
RUN mkdir -p /app/data /app/logs /app/reports && \
    chown -R dsa:dsa /app && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# Efinance will write the search cache (search-cache.json) into its internal data directory within the installation package.
# This directory defaults to root ownership; the container writes as user 'dsa' will cause a PermissionError.
# Causes efinance data source to fail each time when scraping A-shares data and downgrade. Pre-set directory owner for dsa to fix this issue.
# Dynamically parse paths to avoid hardcoding the Python version directory.
RUN EF_DATA_DIR="$(python -c 'import efinance, pathlib; print(pathlib.Path(efinance.__file__).parent / "data")')" && \
    mkdir -p "$EF_DATA_DIR" && \
    chown -R dsa:dsa "$EF_DATA_DIR"

# Set default values for environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_DIR=/app/logs
ENV DATABASE_PATH=/app/data/stock_analysis.db
# Web/API service
ENV WEBUI_HOST=0.0.0.0
ENV API_PORT=8000

# Expose API port
EXPOSE 8000

# Data volume (persistent data)
VOLUME ["/app/data", "/app/logs", "/app/reports"]

# Health check (FastAPI mode)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || curl -f http://localhost:8000/health \
    || python -c "import sys; sys.exit(0)"

# Fix bind mount directory permissions first, then downgrade to dsa execution for the application;
# The documentation docker-compose exec command must explicitly use -u dsa to avoid manually writing process files owned by root.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (overridable)
CMD ["python", "main.py", "--schedule"]
