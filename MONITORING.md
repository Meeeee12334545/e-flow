# Continuous Monitoring Guide

## What's New

Your system now has **continuous monitoring** that:
- ✅ Checks the USRIOT monitor **every 1 minute**
- ✅ Detects **changes** in depth, velocity, and flow data
- ✅ Only adds data to the database **when values change**
- ✅ Prevents duplicate/unchanged entries
- ✅ Logs all activity and statistics

## How to Use

### Start Monitoring

```bash
python monitor.py
```

The monitor will:
1. Check the website every 60 seconds (configurable)
2. Compare new data with the last known values
3. Only store data if something changed
4. Log all activity to `monitor.log`
5. Show real-time statistics

### Example Output

```
2026-01-15 12:00:00,000 - monitor - INFO - [Check #1] Checking for data updates...
2026-01-15 12:00:15,234 - scraper - INFO - ✅ Stored measurement: D=150.2mm, V=2.5mps, F=75.3lps
2026-01-15 12:01:00,000 - monitor - INFO - [Check #2] Checking for data updates...
2026-01-15 12:01:12,456 - scraper - INFO - No change detected
2026-01-15 12:02:00,000 - monitor - INFO - [Check #3] Checking for data updates...
2026-01-15 12:02:18,789 - scraper - INFO - Change detected: D=150.5mm, V=2.6mps, F=76.1lps
```

### Stop Monitoring

Press **Ctrl+C** to stop. The monitor will display:
- Total checks performed
- Number of data updates
- Number of errors

## Configuration

Edit `config.py` to customize:

```python
# Check interval in seconds (default: 60 = 1 minute)
MONITOR_INTERVAL = 60

# Enable/disable monitoring
MONITOR_ENABLED = True

# Monitor URL (target website)
MONITOR_URL = "https://mp.usriot.com/..."
```

### Adjust Checking Frequency

```python
# Check every 30 seconds
MONITOR_INTERVAL = 30

# Check every 5 minutes
MONITOR_INTERVAL = 300

# Check every 1 minute
MONITOR_INTERVAL = 60
```

## Features

### ✅ Smart Change Detection
- Compares depth, velocity, and flow values
- Only stores when ANY value changes
- Prevents database bloat from duplicate entries

### ✅ Robust Error Handling
- Continues running even if one check fails
- Logs all errors with timestamps
- Tracks error count

### ✅ Real-Time Monitoring
- Non-blocking scheduler
- Independent of dashboard
- Can run in background

### ✅ Detailed Logging
- All checks logged to console
- Full logs saved to `monitor.log`
- Easy troubleshooting

## What Gets Stored

Only new or changed data:
```
device_id    : FIT100
timestamp    : Current time (Australia/Brisbane)
depth_mm     : Water depth
velocity_mps : Flow velocity
flow_lps     : Flow rate
```

## Deployment Options

### Local Development
```bash
python monitor.py
```

### Background Service (Linux)
```bash
nohup python monitor.py > monitor.log 2>&1 &
```

### Systemd Service
Create `/etc/systemd/system/e-flow-monitor.service`:
```ini
[Unit]
Description=E-Flow Continuous Monitor
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/e-flow
ExecStart=/path/to/.venv/bin/python monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl start e-flow-monitor
sudo systemctl enable e-flow-monitor
```

### Docker
Create a simple docker container that runs `python monitor.py`

### Kubernetes
Deploy as a long-running pod

## Viewing Collected Data

While monitoring runs, view data in the dashboard:

```bash
# In another terminal
streamlit run app.py
```

The dashboard will show:
- Real-time measurements as they're added
- Historical trends
- Export options (CSV/JSON)

## Troubleshooting

### Monitor not collecting data

1. Check if it's running:
   ```bash
   ps aux | grep monitor.py
   ```

2. Check logs:
   ```bash
   tail -f monitor.log
   ```

3. Verify config settings:
   ```bash
   python -c "from config import MONITOR_ENABLED, MONITOR_INTERVAL; print(f'Enabled: {MONITOR_ENABLED}, Interval: {MONITOR_INTERVAL}s')"
   ```

### High CPU usage

- Increase `MONITOR_INTERVAL` to reduce frequency
- Make sure only one monitor process is running

### No changes detected

- Verify website is accessible: Open URL in browser
- Check if data is actually changing on the website
- Review logs: `tail -f monitor.log`

### Database locked error

- Close the Streamlit dashboard temporarily
- Only one process should write to the database at a time

## Advanced Monitoring

### Multiple Devices

Edit `config.py` to add more devices:
```python
DEVICES = {
    "FIT100": {"name": "Main Inflow", "location": "Lismore"},
    "FIT101": {"name": "Secondary", "location": "Brisbane"},
}
```

Then update `monitor.py` to handle each device.

### Custom Data Parsing

Modify the data extraction in `monitor.py`:
```python
# Extract from JSON API
depth_mm = page_data.get("depth", 0)
velocity_mps = page_data.get("velocity", 0)
flow_lps = page_data.get("flow", 0)
```

### Change Sensitivity

To track more granular changes, modify `scraper.py`:
```python
# Only store if change > 0.1
MIN_CHANGE = {
    "depth_mm": 0.1,
    "velocity_mps": 0.01,
    "flow_lps": 0.1
}
```

## Statistics & Reporting

Check monitoring statistics:
```python
from database import FlowDatabase
from datetime import datetime, timedelta
import pytz

db = FlowDatabase()

# Recent measurements
last_hour = db.get_measurements(limit=100)
print(f"Measurements in last hour: {len(last_hour)}")

# Count by device
for device in db.get_devices():
    count = len(db.get_measurements(device["device_id"]))
    print(f"{device['device_name']}: {count} measurements")
```

## Performance Notes

- Each check takes 10-15 seconds (website loading)
- Memory usage: ~200-300 MB
- Database grows ~10-50 KB per day (depending on change frequency)
- No impact on dashboard performance

---

**Status**: ✅ Ready to monitor continuously
