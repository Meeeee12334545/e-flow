# Quick Start Guide

## First Time Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Initialize the database:**
   ```bash
   python database.py
   ```

3. **Test data collection:**
   ```bash
   python ingest.py
   ```

4. **Start the dashboard:**
   ```bash
   streamlit run app.py
   ```

## Workflow

### Manual Data Collection
```bash
python ingest.py
```

### View Data
```bash
streamlit run app.py
```

Then open your browser to `http://localhost:8501`

### Scheduled Collection (with cron)
Add to your crontab:
```bash
# Collect data every 15 minutes
*/15 * * * * cd /path/to/e-flow && python ingest.py
```

### Export Data
Use the Streamlit dashboard sidebar to:
1. Select a device
2. Choose your time range
3. Click "Download as CSV" or "Download as JSON"

## Troubleshooting

### "No data showing in dashboard"
1. Make sure you've run `python ingest.py` at least once
2. Check the database file exists: `ls -la flow_data.db`
3. Check database contents:
   ```bash
   python -c "from database import FlowDatabase; db = FlowDatabase(); print(f'Devices: {db.get_device_count()}, Measurements: {db.get_measurement_count()}')"
   ```

### "Streamlit won't start"
1. Make sure all dependencies are installed: `pip install -r requirements.txt`
2. Make sure Playwright is installed: `playwright install chromium`

### "Data not updating"
1. Check the monitor URL in `scraper.py` is correct
2. Verify the website is accessible from your network
3. Check logs from `ingest.py` for errors

## Database Inspection

To manually check the database:
```python
from database import FlowDatabase

db = FlowDatabase()

# Get all devices
devices = db.get_devices()
print("Devices:", devices)

# Get measurements for a device
measurements = db.get_measurements(device_id="FIT100")
print(f"Found {len(measurements)} measurements")

# Get summary stats
print(f"Total devices: {db.get_device_count()}")
print(f"Total measurements: {db.get_measurement_count()}")
```

## Reset Database

To start fresh and delete all data:
```python
from database import FlowDatabase

db = FlowDatabase()
db.delete_all_data()
print("Database cleared")
```
