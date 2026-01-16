# Running e-flow

## Setup

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

## Running the System

The system has two components that run separately:

### 1. **Continuous Monitor** (Records data every 1 minute)

In one terminal, start the monitor service:

```bash
python monitor.py
```

This will:
- ✅ Connect to the USRIOT dashboard website
- ✅ Extract depth, velocity, and flow data every 1 minute
- ✅ **Store EVERY reading** (configurable in config.py)
- ✅ **Automatically retry on failures** (3 attempts with 5s delay)
- ✅ **Auto-restart on crashes** (up to 5 times)
- ✅ **Health monitoring** (status checks every 5 minutes)
- ✅ Run continuously until you press Ctrl+C

**Storage Configuration:**
By default, `STORE_ALL_READINGS = True` in config.py, which stores every reading.
- Set to `True`: Stores data every 60 seconds (shows actual check frequency)
- Set to `False`: Only stores when values change (saves database space)

**Production Features:**
- Maximum 10 consecutive failures before alert
- Comprehensive logging to monitor.log
- Graceful shutdown on signals
- Success rate tracking

**For 24/7 production use, see:** [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
- Systemd service (Linux)
- Docker deployment (cross-platform)
- Health monitoring and alerting

### 2. **Web Dashboard** (View the data)

In another terminal, start the Streamlit dashboard:

```bash
streamlit run app.py
```

Then:
- Open your browser to `http://localhost:8501`
- Select the device "FIT100 Main Inflow Lismore STP" from the sidebar
- View real-time depth, velocity, and flow measurements
- Export data as CSV or JSON

## Testing

To test if the data extraction is working without starting the monitor:

```bash
python test_extraction.py
```

This will:
- Fetch data from the website once
- Show you what was extracted
- Try to store one measurement
- Display the results

## Troubleshooting

### No devices showing in dashboard
- Ensure `monitor.py` has run at least once
- Check that the database file `flow_data.db` was created
- Devices are auto-initialized from the dashboard now

### No data values extracted
- Check that the website is accessible
- The website may have changed its structure
- Look at `monitor.log` for detailed error messages

### Monitor stops after starting
- Check `monitor.log` for errors
- Ensure you have internet connection to reach the website
- Verify Playwright chromium is installed: `playwright install chromium`

## Files Overview

- **`monitor.py`** - Runs every 1 minute to fetch and store data
- **`app.py`** - Streamlit web dashboard for viewing data
- **`scraper.py`** - Handles website data extraction
- **`database.py`** - SQLite database management
- **`config.py`** - Configuration (URLs, intervals, device names)
- **`flow_data.db`** - The actual database file (created automatically)
- **`monitor.log`** - Monitor service logs

## Features

✅ Extracts depth, velocity, flow every 1 minute
✅ Automatically detects and stores only changed values
✅ SQLite database for persistent storage
✅ Web dashboard with interactive charts
✅ CSV/JSON export functionality
✅ Device selection and time-range filtering
