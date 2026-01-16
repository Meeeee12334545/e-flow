# e-flow: Autonomous Hydrological Data Acquisition System

**Production-grade automated monitoring and analysis platform for real-time hydrological measurements.** Engineered for continuous extraction, validation, and visualization of depth, velocity, and flow data from remote USRIOT sensor networks with <60s collection intervals and persistence guarantees.

## System Architecture

```
┌────────────────────────────┐
│  USRIOT Dashboard          │
│ (Web-based UI)             │
└────────────┬────────────────┘
             │
             │ HTTP/JavaScript DOM
             │
┌────────────▼────────────────────────────────┐
│  Selenium WebDriver (Headless)              │
│  Chrome Browser Automation                  │
└────────────┬────────────────────────────────┘
             │
      ┌──────▼──────┐
      │  Scraper    │  (CSS Selectors, Data Extraction)
      └──────┬──────┘
             │
    ┌────────▼────────┐
    │   Database      │  (SQLite3, Change-detection)
    │  flow_data      │
    └────────┬────────┘
             │
      ┌──────▼──────────────┐
      │   Dashboard         │  (Streamlit, Plotly)
      │   Analytics         │  (Charts, Export, Metrics)
      └─────────────────────┘
```

## Technical Specifications

| Aspect | Details |
|--------|---------|
| **Polling Interval** | 60 seconds (configurable via `MONITOR_INTERVAL`) |
| **Browser Automation** | Selenium WebDriver + Chrome (headless) |
| **Data Persistence** | SQLite3 with unique constraint on (device_id, timestamp) |
| **Change Detection** | Delta compression - only stores changed values |
| **JavaScript Execution** | `document.querySelector()` with 10s implicit wait |
| **Data Freshness** | ~1-2s page render time + network latency |
| **Storage Format** | Timezone-aware UTC timestamps with local display |
| **Error Handling** | Graceful degradation with detailed logging |
| **Concurrency** | Async/await support via APScheduler |

## Key Features

- **Autonomous Data Collection**: 60-second interval polling with change-only persistence
- **Robust Browser Automation**: Selenium with intelligent page-load detection
- **Data Integrity**: SQLite constraints + timezone-aware timestamps
- **Sub-minute Resolution**: Real-time hydrological measurements
- **Enterprise Logging**: Structured logs with debug/info/warning levels
- **API-ready Database**: Direct SQL access for external integrations
- **Export Capabilities**: CSV/JSON formats for downstream analysis

## Project Structure

```
e-flow/
├── app.py                    # Streamlit analytics dashboard
├── config.py                 # Centralized configuration (URLs, selectors, intervals)
├── database.py               # SQLite3 data layer (ORM-like interface)
├── scraper.py                # Selenium WebDriver automation + CSS selector extraction
├── monitor.py                # APScheduler-based continuous monitoring daemon
├── test_extraction.py        # Integration test suite
├── requirements.txt          # Production dependencies
├── flow_data.db              # SQLite3 database (auto-created on first run)
├── ARCHITECTURE.md           # Technical design documentation
├── DEVELOPMENT.md            # Development workflow guide
└── README.md                 # This file
```

### Module Responsibilities

**config.py**: Device definitions, CSS selectors, monitoring intervals, timezone configuration.

**scraper.py**: Headless Chrome orchestration, DOM traversal, regex-based value extraction, error resilience.

**database.py**: SQLite schema management, CRUD operations, change detection, transaction handling.

**monitor.py**: APScheduler integration, async task scheduling, logging coordination.

**app.py**: Streamlit UI, Plotly visualizations, data export, real-time updates.

## Deployment

### System Requirements

- **Python**: 3.12+ (tested on Python 3.12.1)
- **OS**: Linux (Ubuntu 24.04 LTS, others supported)
- **Memory**: ≥512MB (Chrome headless instance)
- **Disk**: ≥100MB (database + logs)
- **Network**: Internet connectivity to USRIOT endpoints

### Prerequisites

- Google Chrome or Chromium browser (auto-installed via system package manager)
- Python pip/venv tooling
- Git for version control

### Installation

1. **Clone repository**:
   ```bash
   git clone https://github.com/Meeeee12334545/e-flow.git
   cd e-flow
   ```

2. **Create isolated Python environment**:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

4. **Verify Chrome availability**:
   ```bash
   which google-chrome-stable || sudo apt-get install google-chrome-stable
   ```

5. **Initialize database**:
   ```bash
   python -c "from database import FlowDatabase; FlowDatabase()"
   ```

## Usage

### Running the Dashboard

Start the Streamlit app:
```bash
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`

### Scraping Data

To manually fetch data from the monitor:
```bash
python scraper.py
```

### Database Management

To interact with the database directly:
```python
from database import FlowDatabase

db = FlowDatabase()
measurements = db.get_measurements()
devices = db.get_devices()
```

## Dashboard Features

### Main Dashboard
- Latest readings for selected device
- Historical charts for Depth, Velocity, and Flow
- Interactive data table

### Sidebar Controls
- Device selection
- Time range filtering (1-720 hours)
- Manual data refresh button
- Database statistics

### Export Options
- Download as CSV
- Download as JSON

## Data Structure

### Devices Table
- `device_id`: Unique device identifier
- `device_name`: Display name
- `location`: Device location
- `created_at`: Creation timestamp

### Measurements Table
- `id`: Record ID
- `device_id`: Reference to device
- `timestamp`: Measurement time
- `depth_mm`: Water depth in millimeters
- `velocity_mps`: Flow velocity in meters per second
- `flow_lps`: Flow rate in liters per second
- `created_at`: Record creation time

## Configuration

The default timezone is set to `Australia/Brisbane`. To modify:
- Edit `DEFAULT_TZ` in `scraper.py` and `app.py`

The monitor URL can be found and modified in `scraper.py`:
- `MONITOR_URL` variable contains the target website

## Troubleshooting

- **No data loading**: Check that the monitor website is accessible
- **Playwright issues**: Run `playwright install chromium`
- **Database locked**: Close other connections to `flow_data.db`

## Future Enhancements

- Automatic scheduled scraping with APScheduler
- Multiple device support with better filtering
- Advanced analytics and reports
- Alert/notification system
- Data validation and quality checks
- REST API for external access
2. Deploy the repo and point it at `m2m-downloader/streamlit_app.py`.
3. Streamlit Cloud currently lacks several system libraries (`libnspr4`, `libnss3`, `libatk-1.0`, `libatk-bridge-2.0`) required by Playwright’s Chromium build. Run the scraper on infrastructure where you can install those packages, or integrate with a managed browser service.
4. The app installs Chromium on first launch; subsequent runs reuse the cached bundle.
5. Trigger downloads via the "Fetch latest readings" button whenever fresh data is required.
