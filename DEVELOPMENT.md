# Development & Troubleshooting Guide

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'playwright'"

**Solution:**
```bash
pip install -r requirements.txt
playwright install chromium
```

### Issue: "Streamlit won't start / port already in use"

**Solution:**
```bash
# Use a different port
streamlit run app.py --server.port 8502

# Or kill the existing process
lsof -ti:8501 | xargs kill -9
```

### Issue: "Database is locked"

**Solution:**
```bash
# Close all connections to the database
# Then restart the application

# If persistent, back up and recreate:
cp flow_data.db flow_data.db.backup
rm flow_data.db
python database.py
```

### Issue: "No data showing in dashboard"

**Checklist:**
1. ✅ Run `python ingest.py` at least once
2. ✅ Check database: `python -c "from database import FlowDatabase; db = FlowDatabase(); print(db.get_measurement_count())"`
3. ✅ Verify website is accessible: `curl https://mp.usriot.com/draw/show.html`
4. ✅ Check browser logs: Add verbose logging in `scraper.py`

### Issue: "Playwright browser fails to launch"

**Solution:**
```bash
# Install system dependencies (Ubuntu/Debian)
apt-get install libatk-1.0-0 libatk-bridge-2.0-0 libnspr4 libnss3

# Reinstall Playwright
playwright install chromium --with-deps
```

### Issue: "Timeout waiting for page to load"

**Solution:**
Increase timeout in `config.py`:
```python
SCRAPER_TIMEOUT = 30000  # 30 seconds
```

## Development Tips

### Debugging Data Extraction

Add debug output to `scraper.py`:
```python
# In extract_data_from_page()
logger.debug(f"Page title: {title}")
logger.debug(f"HTML content length: {len(html)}")

# Save HTML for inspection
with open("debug_page.html", "w") as f:
    f.write(await page.content())
```

### Testing Database Operations

```python
from database import FlowDatabase
from datetime import datetime
import pytz

db = FlowDatabase()

# Add test device
db.add_device("TEST001", "Test Device", "Test Location")

# Add test measurements
for i in range(5):
    db.add_measurement(
        device_id="TEST001",
        timestamp=datetime.now(pytz.timezone("Australia/Brisbane")),
        depth_mm=100.0 + i,
        velocity_mps=1.5 + (i * 0.1),
        flow_lps=50.0 + (i * 5)
    )

# Verify
measurements = db.get_measurements("TEST001")
print(f"Created {len(measurements)} test measurements")
```

### Running Tests

Create a `test_database.py` file:
```python
import unittest
from database import FlowDatabase
from datetime import datetime
import pytz
import os

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_flow_data.db"
        self.db = FlowDatabase(self.db_path)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_add_device(self):
        self.db.add_device("TEST", "Test Device")
        devices = self.db.get_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["device_id"], "TEST")

if __name__ == "__main__":
    unittest.main()
```

Run with:
```bash
python -m unittest test_database.py -v
```

### Profiling & Performance

Monitor database performance:
```python
from database import FlowDatabase
import time

db = FlowDatabase()

start = time.time()
measurements = db.get_measurements(limit=10000)
duration = time.time() - start

print(f"Retrieved {len(measurements)} records in {duration:.2f}s")
print(f"Rate: {len(measurements)/duration:.0f} records/second")
```

## Code Examples

### Adding a New Device Type

1. Update `config.py`:
```python
DEVICES = {
    "FIT100": {"name": "FIT100 Main Inflow", "location": "Lismore"},
    "FIT101": {"name": "FIT101 Secondary", "location": "Brisbane"}  # New device
}
```

2. Update `scraper.py` to handle multiple URLs if needed
3. Run `python ingest.py` to collect data

### Custom Data Processing

Create a `analytics.py` file:
```python
import pandas as pd
from database import FlowDatabase

def get_statistics(device_id, hours=24):
    db = FlowDatabase()
    measurements = db.get_measurements(device_id=device_id)
    df = pd.DataFrame(measurements)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    return {
        "depth_mean": df["depth_mm"].mean(),
        "depth_max": df["depth_mm"].max(),
        "depth_min": df["depth_mm"].min(),
        "velocity_mean": df["velocity_mps"].mean(),
        "flow_mean": df["flow_lps"].mean(),
    }

if __name__ == "__main__":
    stats = get_statistics("FIT100")
    for key, value in stats.items():
        print(f"{key}: {value:.2f}")
```

### Exporting to External Database

```python
import sqlite3
import pandas as pd
from database import FlowDatabase

def export_to_postgres(device_id):
    """Export data to PostgreSQL"""
    import psycopg2
    
    db = FlowDatabase()
    measurements = db.get_measurements(device_id=device_id)
    df = pd.DataFrame(measurements)
    
    conn = psycopg2.connect("dbname=monitoring user=postgres")
    df.to_sql("flow_measurements", conn, if_exists="append", index=False)
    conn.close()
```

## Logging Configuration

Customize logging in `ingest.py`:
```python
import logging
import logging.handlers

# File logging
handler = logging.handlers.RotatingFileHandler(
    "e-flow.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        handler
    ]
)
```

## Performance Optimization

### Database Indexing
The database already has an index on (device_id, timestamp). For other queries, add:
```python
import sqlite3

conn = sqlite3.connect("flow_data.db")
cursor = conn.cursor()

# Add index for timestamp searches
cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_timestamp 
    ON measurements (timestamp DESC)
""")

conn.commit()
conn.close()
```

### Batch Inserts
For large data imports:
```python
def bulk_insert(measurements_list):
    db = FlowDatabase()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    cursor.executemany("""
        INSERT INTO measurements 
        (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
        VALUES (?, ?, ?, ?, ?)
    """, measurements_list)
    
    conn.commit()
    conn.close()
```

## Integration Points

### Webhook Integration (Future)
```python
# Incoming webhooks from other systems
from flask import Flask, request

app = Flask(__name__)

@app.route("/webhook/measurement", methods=["POST"])
def receive_measurement():
    data = request.json
    db = FlowDatabase()
    db.add_device(data["device_id"], data["device_name"])
    db.add_measurement(
        device_id=data["device_id"],
        timestamp=data["timestamp"],
        depth_mm=data.get("depth_mm"),
        velocity_mps=data.get("velocity_mps"),
        flow_lps=data.get("flow_lps")
    )
    return {"status": "ok"}
```

## Monitoring Health

Create a `health_check.py`:
```python
from database import FlowDatabase
from datetime import datetime, timedelta
import pytz

db = FlowDatabase()

# Check for recent data
measurements = db.get_measurements(limit=1)
if measurements:
    latest = measurements[0]
    age = datetime.now(pytz.timezone("Australia/Brisbane")) - datetime.fromisoformat(latest["timestamp"])
    
    if age > timedelta(hours=1):
        print("⚠️  WARNING: Data is stale (>1 hour old)")
    else:
        print("✅ Data is current")
else:
    print("❌ ERROR: No measurements found")

print(f"Database size: {len(measurements)} records")
print(f"Devices: {db.get_device_count()}")
```
