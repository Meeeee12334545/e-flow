# e-flow
Data platform for EDS range of Metalog 4G data loggers and range of monitoring instrumentation.

## M2M Downloader

Automation lives under [m2m-downloader](m2m-downloader). The GitHub workflow in [m2m-downloader/.github/workflows/run.yml](m2m-downloader/.github/workflows/run.yml) runs the script hourly and uploads [m2m_outputs](m2m_outputs) as an artifact.

### Local Prerequisites
- Python 3.10 or newer
- Firefox or Chrome installed locally (for the Selenium script)
- Playwright chromium bundle (for the Streamlit app)

### Local Setup
1. `cd m2m-downloader`
2. `python -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`

### Required Environment
Set environment variables before running:
- `M2M_USERNAME`
- `M2M_PASSWORD`
Optional overrides:
- `M2M_BROWSER` (`firefox` or `chrome`, default `firefox`)
- `M2M_HEADLESS` (`true` hides the browser)

### Run Locally
Execute `python m2m.py`. Screenshots and HTML snapshots land in [m2m_outputs](m2m_outputs).

### GitHub Secrets
Configure repository secrets so the scheduled workflow succeeds:
- `M2M_USERNAME`
- `M2M_PASSWORD`

## Streamlit App

The Playwright-powered Streamlit interface lives in [m2m-downloader/streamlit_app.py](m2m-downloader/streamlit_app.py). It captures live Depth, Velocity, and Flow readings and offers an on-demand CSV download.

### Streamlit Usage
- Ensure dependencies are installed: `pip install -r requirements.txt`
- Install the Playwright browser bundle once: `playwright install chromium`
- Run the UI: `streamlit run streamlit_app.py`

### Credentials and Settings
- Supply `M2M_USERNAME` and `M2M_PASSWORD` via Streamlit Secrets or environment variables. You can also override them within the UI.
- The default group filter targets "Toowoomba Regional Council"; adjust it in the sidebar if needed.
- CSV exports include Timestamp (Australia/Brisbane by default), Device ID, Device Name, Depth (mm), Velocity (mps), and Flow (lps).

### Streamlit Cloud Deployment
1. Add the credentials to Streamlit Cloud secrets.
2. Deploy the repo and point it at `m2m-downloader/streamlit_app.py`.
3. The app will install Chromium on first launch; subsequent runs reuse the cached bundle.
4. Trigger downloads via the "Fetch latest readings" button whenever fresh data is required.
