# Configuration file for e-flow

# Timezone for all timestamps
TIMEZONE = "Australia/Brisbane"

# Monitor website URL
MONITOR_URL = "https://mp.usriot.com/draw/show.html?lang=en&lightbox=1&highlight=0000ff&layers=1&nav=1&title=FIT100%20Main%20Inflow%20Lismore%20STP&id=97811&link=Lpu7Q2CM3osZ&model=1&cusdeviceNo=0000088831000010&share=48731ec89bf8108b2a451fbffa590da4f0cf419a5623beb7d48c1060e3f0dbe177e28054c26be49bbabca1da5b977e7c16a47891d94f70a08a876d24c55416854700de7cc51a06f8e102798d6ecc39478ef1394a246efa109e6c6358e30a259010a5c403c71756173c90cf1e10ced6fdf54d90881c05559f2c8c5717ee8109210672fa3574a9c04a465bc0df8b9c354da487a7bcb6679a7ec32276ba3610301be80d8c7588ef1797ca01fb6b87e74a8b6e5cd0ac668918d02ae99a7966f57ecf603b63a12d4b0a160d3ac0920254d6836f1e26d244412f82859f7f7b0df7b8406e95ef97a7cb2302a07826d3b8cba81721c5bce1d7e9bf0b01f32d1d0330a44301a1ab0f"

# Device configuration
# Format: device_id: {"name": "Device Name", "location": "Location", "selectors": {...}}
DEVICES = {
    "FIT100": {
        "name": "FIT100 Main Inflow Lismore STP",
        "location": "Lismore",
        "selectors": {
            "depth_mm": "#div_varvalue_10",
            "velocity_mps": "#div_varvalue_6",
            "flow_lps": "#div_varvalue_42"
        }
    }
}

# Database settings
DATABASE_PATH = "flow_data.db"
DATABASE_TIMEOUT = 30  # seconds

# Scraper settings
SCRAPER_TIMEOUT = 15000  # milliseconds
SCRAPER_HEADLESS = True
SCRAPER_WAIT_AFTER_LOAD = 3000  # milliseconds - increased for better loading

# Monitor settings
MONITOR_INTERVAL = 60  # seconds (1 minute for continuous monitoring)
MONITOR_ENABLED = False  # DISABLED - Streamlit Cloud causes duplicate monitors. Use standalone monitor instead.
STORE_ALL_READINGS = False  # If True, stores every reading. If False, only stores when values change

# Streamlit settings
STREAMLIT_DEFAULT_TIME_RANGE = 24  # hours
STREAMLIT_MAX_TIME_RANGE = 720  # hours (30 days)

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
