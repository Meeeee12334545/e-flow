# Architecture & System Design

## Project Overview

e-flow is a complete data management system for monitoring flow, depth, and velocity metrics from remote sensors. It provides:
- Automated data collection from web-based monitors
- Local SQLite database storage
- Interactive web dashboard for visualization and analysis
- Data export capabilities (CSV/JSON)

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Remote Monitor Website (USRIOT)                 │
│         https://mp.usriot.com/draw/show.html           │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ HTTP/Playwright
                         ▼
┌─────────────────────────────────────────────────────────┐
│             Data Scraper (scraper.py)                   │
│  - Automated browser automation with Playwright         │
│  - Extracts depth, velocity, flow data                 │
│  - Handles dynamic content loading                      │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ Python API
                         ▼
┌─────────────────────────────────────────────────────────┐
│         SQLite Database (flow_data.db)                  │
│  ┌──────────────────┐      ┌──────────────────┐        │
│  │    devices       │      │  measurements    │        │
│  │  - device_id    │      │  - id            │        │
│  │  - device_name  │◄─────┤  - device_id     │        │
│  │  - location     │      │  - timestamp     │        │
│  │  - created_at   │      │  - depth_mm      │        │
│  └──────────────────┘      │  - velocity_mps  │        │
│                            │  - flow_lps      │        │
│                            │  - created_at    │        │
│                            └──────────────────┘        │
└────────────┬───────────────────────────────┬───────────┘
             │                               │
             │ database.py API             │
             │                               │
┌────────────▼──────────┐    ┌──────────────▼────────┐
│  Data Ingestion       │    │  Streamlit Dashboard   │
│  (ingest.py)          │    │  (app.py)              │
│  - Manual script      │    │  - View measurements   │
│  - Cron scheduling    │    │  - Interactive charts  │
│  - Error handling     │    │  - Export data         │
└───────────────────────┘    └────────────────────────┘
```

## Data Flow

### Collection Pipeline
```
1. ingest.py runs (manual or scheduled)
   ↓
2. scraper.py launches browser & navigates to monitor URL
   ↓
3. Extracts JSON/HTML data from the page
   ↓
4. Parses measurements (depth, velocity, flow)
   ↓
5. database.py stores in SQLite
   ↓
6. Data available in dashboard
```

### Dashboard Pipeline
```
1. User opens Streamlit app (app.py)
   ↓
2. Sidebar device selector filters data
   ↓
3. Time range filter applied (1-720 hours)
   ↓
4. database.py retrieves matching records
   ↓
5. Pandas processes data
   ↓
6. Plotly generates interactive charts
   ↓
7. Export options (CSV/JSON) available
```

## File Descriptions

| File | Purpose | Type |
|------|---------|------|
| `database.py` | SQLite database management | Module |
| `scraper.py` | Web scraper for monitor data | Module |
| `ingest.py` | Data collection entry point | Script |
| `app.py` | Streamlit web interface | Script |
| `config.py` | Configuration settings | Config |
| `setup.py` | Environment initialization | Script |
| `requirements.txt` | Python dependencies | Config |
| `flow_data.db` | SQLite database file | Database |

## Technology Stack

- **Backend**: Python 3.10+
- **Web Scraping**: Playwright (headless browser automation)
- **Database**: SQLite3
- **Web Interface**: Streamlit
- **Data Processing**: Pandas
- **Visualization**: Plotly
- **Timezone**: pytz

## Database Schema

### devices table
```sql
CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    device_name TEXT NOT NULL,
    location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### measurements table
```sql
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    depth_mm REAL,
    velocity_mps REAL,
    flow_lps REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices (device_id),
    UNIQUE(device_id, timestamp)
);
```

## Configuration Management

All settings are in `config.py`:
- `TIMEZONE`: Timestamp timezone
- `MONITOR_URL`: Target website URL
- `DEVICES`: Device registry
- `DATABASE_PATH`: Database file location
- `SCRAPER_TIMEOUT`: Page load timeout
- `STREAMLIT_*`: Dashboard settings
- `LOG_LEVEL`: Debug level

## Deployment Options

### Local Development
```bash
python ingest.py  # Single collection
streamlit run app.py  # Dashboard
```

### Scheduled Collection (cron)
```bash
# Every 15 minutes
*/15 * * * * cd /path/to/e-flow && /path/to/.venv/bin/python ingest.py >> /var/log/e-flow.log 2>&1
```

### Cloud Deployment (Streamlit Cloud)
1. Push to GitHub
2. Deploy on Streamlit Cloud
3. Configure environment variables
4. Optional: Add GitHub Actions for scheduled scraping

## Error Handling

- Network errors: Logged with retry capability
- Parsing errors: Graceful fallback with warnings
- Database locks: Automatic retry with timeout
- Browser timeout: Clear error messages in logs

## Performance Considerations

- Database indexes on (device_id, timestamp) for fast queries
- UNIQUE constraint prevents duplicate measurements
- Lazy loading in dashboard (loads as scrolled)
- Batch operations for bulk inserts
- Connection pooling via SQLite

## Security Considerations

- No credentials in code (use environment variables)
- No SQL injection (parameterized queries throughout)
- Database file permissions (user-only access)
- No sensitive data in logs
