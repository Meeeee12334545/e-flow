#!/bin/bash
# Start the e-flow monitor service
# Usage: ./start.sh

set -e

cd "$(dirname "$0")"

echo "🚀 Starting e-flow monitor service..."
echo ""

# Check if Python environment exists
if [ ! -f .venv/bin/python ]; then
    echo "❌ Virtual environment not found. Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Ensure database is initialized
echo "📊 Initializing database..."
.venv/bin/python -c "from database import FlowDatabase; db = FlowDatabase(); print(f'✅ Database ready - {db.get_device_count()} devices, {db.get_measurement_count()} measurements')"

# Start monitor with env vars
echo ""
echo "🔄 Starting monitor (interval: 60s, API mode, change detection enabled)..."
echo ""

export SCRAPER_FORCE_REQUESTS=1
export MONITOR_ENABLED=true
export MONITOR_INTERVAL=60
export STORE_ALL_READINGS=false
export EXIT_ON_UNHEALTHY=true
export TIMEZONE="Australia/Brisbane"

.venv/bin/python monitor.py
