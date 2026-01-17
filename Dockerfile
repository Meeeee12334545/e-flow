# Dockerfile for e-flow production deployment
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps

# Copy application files
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Health check (uses health.py to ensure recent data)
HEALTHCHECK --interval=5m --timeout=30s --start-period=60s --retries=3 \
    CMD python health.py || exit 1

# Run the monitor
CMD ["python", "monitor.py"]
