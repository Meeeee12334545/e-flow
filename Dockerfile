# Dockerfile for e-flow production deployment
FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
# WeasyPrint needs Pango/Cairo for PDF rendering.
# Playwright's "--with-deps" flag handles Chromium's own system dependencies
# (libnss, libatk, etc.) in a separate step below, so we only list libs that
# Playwright's script does NOT cover.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint / Cairo PDF stack
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Fonts for PDF and chart rendering
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies (cached layer) ───────────────────────────────────────
# Copy only requirements first so this expensive layer is cached until
# requirements.txt changes — not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # Install Playwright-managed Chromium + its own system deps in one step.
    # This is the ONLY Chromium installation; no separate apt chromium needed.
    && playwright install chromium --with-deps

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Runtime directories ───────────────────────────────────────────────────────
RUN mkdir -p /app/data /app/reports

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
# Prevent .pyc files from being written (saves ~10MB on a busy app)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── Port ─────────────────────────────────────────────────────────────────────
EXPOSE 8501

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=5m --timeout=30s --start-period=60s --retries=3 \
    CMD python health.py || exit 1

# ── Default entrypoint ────────────────────────────────────────────────────────
# supervisord manages both the background monitor and the Streamlit dashboard.
# Override CMD in docker-compose for single-purpose containers:
#   monitor service:   command: python monitor.py
#   dashboard service: command: streamlit run app.py --server.port=8501 --server.address=0.0.0.0
CMD ["supervisord", "-c", "/app/supervisord.conf"]
