# e-flow

Online database for monitoring and analyzing flow data from remote sensors. Captures depth, velocity, and flow measurements and provides a web interface for viewing, analyzing, and exporting data.

## Features

- 📊 Real-time data collection from remote monitoring websites
- 💾 SQLite database for persistent data storage
- 🌐 Streamlit web interface for viewing and analyzing data
- 📈 Interactive charts and visualizations
- 📥 Export data as CSV or JSON
- 🔄 Automatic data refresh capabilities
- 📱 Responsive dashboard design

## Project Structure

```
e-flow/
├── database.py          # SQLite database management
├── scraper.py           # Data scraper for the monitor website
├── app.py              # Streamlit web interface
├── requirements.txt    # Python dependencies
├── flow_data.db        # SQLite database (auto-created)
└── README.md          # This file
```

## Setup

### Prerequisites

- Python 3.10 or newer
- pip package manager

### Installation

1. Clone the repository
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
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
