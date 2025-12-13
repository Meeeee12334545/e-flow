# e-flow
Data platform for EDS range of Metalog 4G data loggers and range of monitoring instrumentation.

## M2M Downloader

Automation lives under [m2m-downloader](m2m-downloader). The GitHub workflow in [m2m-downloader/.github/workflows/run.yml](m2m-downloader/.github/workflows/run.yml) runs the script hourly and uploads [m2m_outputs](m2m_outputs) as an artifact.

### Local Prerequisites
- Python 3.10 or newer
- Firefox or Chrome installed locally

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
