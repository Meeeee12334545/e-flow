# Quick Start: Running e-flow Monitor

The e-flow system has two components:

## 1. Monitor Service (always-on data collection)
Collects data every 60 seconds and stores to the database.

```bash
# Terminal 1: Run the monitor
cd /workspaces/e-flow
export SCRAPER_FORCE_REQUESTS=1
export MONITOR_ENABLED=true
export TIMEZONE="Australia/Brisbane"
python monitor.py
```

You'll see logs like:
```
🚀 CONTINUOUS MONITOR STARTED (PRODUCTION MODE)
⏱️  Interval: Every 60 seconds
✅ Monitoring will detect changes and store only new data
```

The monitor will:
- Fetch data from the USRIOT website every 60 seconds
- Compare with the last stored value
- Store to database only if the reading changed
- Run continuously until you press Ctrl+C

## 2. Dashboard (read-only visualization)
Displays stored data in a web interface.

```bash
# Terminal 2: Run the dashboard
cd /workspaces/e-flow
streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## Typical Workflow

1. **Start Monitor in Terminal 1** (keeps collecting)
2. **Start Dashboard in Terminal 2** (view the data)
3. **Leave Monitor running** while you use the dashboard
4. **Refresh dashboard** to see new measurements

---

## Verification

Check if monitor is writing data:

```bash
# In another terminal
sqlite3 flow_data.db "SELECT COUNT(*) as measurements, MAX(timestamp) as latest FROM measurements;"
```

Expected output after monitor has run for 60+ seconds:
```
1|2026-01-17 14:17:10.123456+10:00
```

---

## Docker (Synology/Always-on)

For production on a NAS:

```bash
docker compose -f docker-compose.synology.yml up -d
docker logs -f e-flow-monitor
```

This keeps the monitor running 24/7 with auto-restart on failure.
