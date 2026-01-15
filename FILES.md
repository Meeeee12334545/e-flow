# File Reference Guide

## Project Files Overview

### 📊 Core Application Files

#### `database.py` (150+ lines)
- **Purpose**: SQLite database management
- **Key Classes**: `FlowDatabase`
- **Methods**: 
  - `init_db()` - Initialize tables
  - `add_device()` - Register device
  - `add_measurement()` - Store reading
  - `get_measurements()` - Query data
  - `get_devices()` - List devices
- **Database**: Creates `flow_data.db`

#### `scraper.py` (200+ lines)
- **Purpose**: Web scraper for monitor website
- **Key Classes**: `DataScraper`
- **Methods**:
  - `fetch_monitor_data()` - Get data from website
  - `extract_data_from_page()` - Parse HTML/JSON
  - `store_measurement()` - Save to database
- **Browser**: Uses Playwright for automation
- **Target**: USRIOT monitor dashboard

#### `ingest.py` (100+ lines)
- **Purpose**: Data collection entry point
- **When to Use**: Manual or scheduled scraping
- **How to Run**: `python ingest.py`
- **Logging**: Detailed collection logs

#### `app.py` (300+ lines)
- **Purpose**: Streamlit web dashboard
- **Features**:
  - Real-time data visualization
  - Interactive charts (Plotly)
  - Data export (CSV/JSON)
  - Device selection & time filtering
- **How to Run**: `streamlit run app.py`
- **Port**: `http://localhost:8501`

### ⚙️ Configuration Files

#### `config.py` (45+ lines)
- **Purpose**: Centralized settings
- **Contains**:
  - `TIMEZONE` - Default timezone
  - `MONITOR_URL` - Target website
  - `DEVICES` - Device registry
  - `DATABASE_PATH` - Database location
  - Scraper and dashboard settings

#### `requirements.txt` (10 lines)
- **Purpose**: Python dependencies
- **Key Packages**:
  - `selenium` - Web automation
  - `playwright` - Browser control
  - `streamlit` - Web framework
  - `pandas` - Data processing
  - `plotly` - Visualization
- **Installation**: `pip install -r requirements.txt`

#### `setup.py` (150+ lines)
- **Purpose**: Automated environment setup
- **Features**:
  - Python version check
  - Virtual environment creation
  - Dependency installation
  - Database initialization
- **How to Run**: `python setup.py`

### 📚 Documentation Files

#### `README.md` (120+ lines)
- **Overview**: Project description and features
- **Sections**:
  - Feature list
  - Project structure
  - Installation steps
  - Usage guide
  - Configuration
  - Troubleshooting
  - Future enhancements

#### `QUICKSTART.md` (90+ lines)
- **Purpose**: Quick reference guide
- **Sections**:
  - First-time setup
  - Workflow (collect, view, export)
  - Scheduled collection
  - Troubleshooting
  - Database inspection

#### `ARCHITECTURE.md` (200+ lines)
- **Purpose**: System design documentation
- **Sections**:
  - Architecture diagram
  - Data flow diagrams
  - File descriptions
  - Technology stack
  - Database schema
  - Deployment options
  - Performance considerations

#### `DEVELOPMENT.md` (300+ lines)
- **Purpose**: Development and troubleshooting guide
- **Sections**:
  - Common issues & solutions
  - Development tips
  - Code examples
  - Testing guide
  - Performance optimization
  - Integration examples

#### `PROJECT_SUMMARY.md` (200+ lines)
- **Purpose**: High-level project overview
- **Sections**:
  - What was done
  - Current structure
  - Features list
  - Tech stack
  - Quick start
  - Deployment options
  - Next steps

#### `FILES.md` (This file)
- **Purpose**: File reference guide
- **Contents**: Description of all files in project

### 💾 Data Files

#### `flow_data.db` (28 KB)
- **Type**: SQLite database
- **Tables**:
  - `devices` - Device registry
  - `measurements` - Time-series data
- **Status**: Auto-created, ready for data
- **Indices**: Optimized for device_id + timestamp queries

### 📝 Configuration Files

#### `.gitignore` (35+ lines)
- **Purpose**: Git ignore patterns
- **Excludes**:
  - Virtual environment
  - Python cache
  - IDE files
  - Database backups
  - Logs and temporary files

---

## File Usage Guide

### To Get Started
1. Read: `README.md`
2. Run: `setup.py`
3. Execute: `ingest.py`
4. Start: `streamlit run app.py`

### For Quick Tasks
- See: `QUICKSTART.md`

### For Troubleshooting
- See: `DEVELOPMENT.md`

### For System Understanding
- See: `ARCHITECTURE.md`

### For Code Development
- See: `DEVELOPMENT.md` (examples)
- Modify: `config.py` (settings)
- Extend: `database.py` (new queries)
- Enhance: `scraper.py` (data extraction)
- Customize: `app.py` (UI)

---

## Code Statistics

| File | Purpose | Lines |
|------|---------|-------|
| `database.py` | Database management | ~150 |
| `scraper.py` | Web scraping | ~200 |
| `app.py` | Dashboard UI | ~300 |
| `ingest.py` | Data collection | ~100 |
| `setup.py` | Setup automation | ~150 |
| `config.py` | Configuration | ~45 |
| **Total Python** | | ~945 |
| | | |
| `README.md` | Main documentation | ~120 |
| `QUICKSTART.md` | Quick reference | ~90 |
| `ARCHITECTURE.md` | Design docs | ~200 |
| `DEVELOPMENT.md` | Dev guide | ~300 |
| `PROJECT_SUMMARY.md` | Overview | ~200 |
| `FILES.md` | File guide | ~150 |
| **Total Documentation** | | ~1060 |
| | | |
| **Project Total** | | ~2000+ |

---

## Dependency Files

```
requirements.txt
├── selenium>=4.20           (Legacy - may be removed)
├── playwright>=1.47.0       (Web scraping ✓)
├── streamlit>=1.38.0        (Dashboard ✓)
├── pandas>=2.1.0            (Data processing ✓)
├── pytz>=2024.1             (Timezone ✓)
├── plotly>=5.22.0           (Visualization ✓)
├── sqlite3-python>=0.0.1    (Database - built-in)
├── requests>=2.31.0         (HTTP - optional)
└── beautifulsoup4>=4.12.0   (HTML parsing - optional)
```

---

## Installation Checklist

- [ ] Python 3.10+
- [ ] Virtual environment created
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Playwright installed: `playwright install chromium`
- [ ] Database initialized: `python database.py`
- [ ] Configuration reviewed: `config.py`
- [ ] First data collection: `python ingest.py`
- [ ] Dashboard tested: `streamlit run app.py`

---

## Next Steps

1. **Review**: Start with `README.md`
2. **Setup**: Run `setup.py`
3. **Collect**: Execute `python ingest.py`
4. **Visualize**: Start `streamlit run app.py`
5. **Customize**: Modify `config.py` as needed
6. **Schedule**: Set up cron job for automation
7. **Extend**: Add features using `DEVELOPMENT.md` guide

---

**Last Updated**: January 15, 2026
**Project Status**: ✅ Ready for deployment
