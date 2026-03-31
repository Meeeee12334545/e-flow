import asyncio
import os
import sys
import subprocess
import threading
import time as _time_module
from datetime import datetime, timedelta
from pathlib import Path
import logging
import json

import streamlit as st
import pandas as pd
import pytz
import plotly.express as px
import plotly.graph_objects as go

from database import FlowDatabase
from scraper import DataScraper
from config import DEVICES, MONITOR_URL, MONITOR_ENABLED

from streamlit_auth import init_auth_state, is_authenticated, is_admin, login_page, render_auth_header, filter_devices_for_user

# Setup logging before anything else
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background data collection – runs every 60 s, always stores readings
# ---------------------------------------------------------------------------

def _bg_collect_once():
    """Run one data-collection pass for every configured device."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _db = FlowDatabase()
        _scraper = DataScraper(_db)
        for device_id, device_info in DEVICES.items():
            try:
                # For background collection, force the lightweight API/requests path
                # by not passing selectors (which would trigger Playwright).
                data = loop.run_until_complete(
                    _scraper.fetch_monitor_data(
                        device_info.get("url", MONITOR_URL),
                        None,
                    )
                )
                if data and data.get("data"):
                    payload = data["data"]
                    stored = _scraper.store_measurement(
                        device_id=device_id,
                        device_name=device_info.get("name", device_id),
                        depth_mm=payload.get("depth_mm"),
                        velocity_mps=payload.get("velocity_mps"),
                        flow_lps=payload.get("flow_lps"),
                        allow_storage=True,
                    )
                    logger.info(
                        f"BG collect {device_id}: stored={stored} "
                        f"D={payload.get('depth_mm')} V={payload.get('velocity_mps')} F={payload.get('flow_lps')}"
                    )
                else:
                    logger.warning(f"BG collect {device_id}: no data returned")
            except Exception as exc:
                logger.error(f"BG collect error for {device_id}: {exc}")
    finally:
        loop.close()


def _bg_collection_worker():
    """Daemon thread: install Playwright if needed, then collect data every 60 s."""
    # Install Playwright browsers in the background so the UI is never blocked
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            capture_output=True, timeout=120
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, timeout=120
        )
    except Exception:
        pass
    logger.info("Background collection thread started – interval 60 s")
    while True:
        try:
            _bg_collect_once()
        except Exception as exc:
            logger.error(f"BG collection worker error: {exc}")
        _time_module.sleep(60)


@st.cache_resource
def start_background_collection():
    """Start the background collection thread exactly once per app instance.
    Returns immediately so the UI is never blocked by browser installation."""
    t = threading.Thread(target=_bg_collection_worker, daemon=True, name="eflow-bg-collector")
    t.start()
    logger.info("✅ Background data collection thread launched")
    return {"started_at": datetime.now().isoformat(), "interval_s": 60}


# Page config MUST be the first Streamlit command
st.set_page_config(
    page_title="e-flow | EDS Hydrological Analytics",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Launch background collection (cached – only runs once per Streamlit worker)
_bg_status = start_background_collection()

# Initialize authentication state
init_auth_state()

# Check if user is authenticated - if not, show login page
if not is_authenticated():
    login_page()
    st.stop()

# ── EDS professional styling ────────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Font imports (more reliable than <link> tags in Streamlit) ── */
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Global UI font (excludes icon elements) ── */
    body, p, div, input, select, textarea, button,
    h1, h2, h3, h4, h5, h6, li, td, th, label {
        font-family: 'Inter', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* ── Material Symbols: all icon elements get the icon font ──
       Placed AFTER the global font rule; attribute selector (0,1,0)
       beats tag/universal selectors, so this always wins. ── */
    .material-symbols-rounded,
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded' !important;
        font-weight: normal !important;
        font-style: normal !important;
        font-size: 20px !important;
        line-height: 1 !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        font-feature-settings: 'liga' 1;
        -webkit-font-smoothing: antialiased;
    }

    /* ── Clip Streamlit's sidebar collapse/nav icon to prevent text overflow ── */
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarNavCollapseButton"] [data-testid="stIconMaterial"] {
        overflow: hidden;
        max-width: 24px;
        max-height: 24px;
        display: inline-block;
    }

    /* ── EDS top header bar ── */
    .eds-header {
        background: linear-gradient(135deg, #002f6c 0%, #01408f 100%);
        color: #ffffff;
        padding: 18px 28px;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 4px 20px rgba(0,47,108,0.25);
    }
    .eds-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff !important;
        letter-spacing: -0.3px;
    }
    .eds-header .eds-subtitle {
        color: rgba(255,255,255,0.8);
        font-size: 0.9rem;
        margin-top: 4px;
        font-weight: 400;
    }
    .eds-header .eds-live-badge {
        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,194,14,0.6);
        border-radius: 20px;
        padding: 6px 16px;
        display: flex;
        align-items: center;
        gap: 8px;
        color: #ffc20e;
        font-weight: 600;
        font-size: 0.9rem;
        white-space: nowrap;
    }
    .eds-live-dot {
        width: 8px;
        height: 8px;
        background: #ffc20e;
        border-radius: 50%;
        animation: pulse-gold 1.5s infinite;
        display: inline-block;
    }
    @keyframes pulse-gold {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.3); }
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #e8ecf4;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 0 !important;
    }
    .sidebar-logo {
        background: linear-gradient(135deg, #002f6c 0%, #01408f 100%);
        padding: 18px 16px;
        margin-bottom: 1rem;
        text-align: center;
    }
    .sidebar-logo h2 {
        color: #ffffff !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        letter-spacing: 1px;
    }
    .sidebar-logo .sidebar-tagline {
        color: #ffc20e;
        font-size: 0.7rem;
        font-weight: 500;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-top: 3px;
    }

    /* ── Sidebar section labels ── */
    .sidebar-section-label {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: #002f6c;
        padding: 0 4px;
        margin: 1.2rem 0 0.4rem 0;
        border-left: 3px solid #ffc20e;
        padding-left: 8px;
    }

    /* ── Station info card in sidebar ── */
    .station-info-card {
        background: #f4f7fc;
        border: 1px solid #dce5f0;
        border-radius: 8px;
        padding: 10px 12px;
        margin: 0.5rem 0 1rem 0;
        font-size: 0.82rem;
        line-height: 1.7;
        color: #333;
    }
    .station-info-card strong {
        color: #002f6c;
        font-weight: 600;
    }

    /* ── Auto-collect status pill ── */
    .collect-status-active {
        background: #e8f5e9;
        border: 1px solid #81c784;
        border-radius: 20px;
        padding: 5px 12px;
        font-size: 0.78rem;
        color: #2e7d32;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.5rem;
    }

    /* ── KPI metric cards ── */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #dce5f0;
        border-top: 4px solid #002f6c;
        border-radius: 10px;
        padding: 18px 20px;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0,47,108,0.07);
        transition: box-shadow 0.2s, transform 0.2s;
    }
    .kpi-card:hover {
        box-shadow: 0 6px 18px rgba(0,47,108,0.14);
        transform: translateY(-2px);
    }
    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #6b7a99;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 700;
        color: #002f6c;
        line-height: 1.1;
    }
    .kpi-unit {
        font-size: 0.85rem;
        font-weight: 400;
        color: #8892a4;
        margin-left: 3px;
    }

    /* ── Section headings ── */
    h1, h2, h3, h4, h5, h6 {
        color: #002f6c;
        font-weight: 600;
    }
    h2 { font-size: 1.5rem; margin: 1.4rem 0 0.8rem 0; }
    h3 { font-size: 1.2rem; margin: 1.2rem 0 0.6rem 0; }

    /* ── Download button ── */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #002f6c 0%, #01408f 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.2rem !important;
        letter-spacing: 0.3px;
        box-shadow: 0 2px 8px rgba(0,47,108,0.2);
    }
    .stDownloadButton > button:hover {
        box-shadow: 0 4px 14px rgba(0,47,108,0.35) !important;
        transform: translateY(-1px);
    }

    /* ── Primary button ── */
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #002f6c 0%, #01408f 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 2px solid #e8ecf4;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 500 !important;
        font-size: 0.88rem !important;
        padding: 8px 18px !important;
        border-radius: 6px 6px 0 0 !important;
        color: #6b7a99 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #002f6c !important;
        background: #f4f7fc !important;
        border-bottom: 2px solid #002f6c !important;
    }

    /* ── Alert boxes ── */
    .stAlert {
        border-radius: 8px !important;
        font-size: 0.88rem;
    }

    /* ── Metrics (native Streamlit) ── */
    [data-testid="metric-container"] {
        background: #f4f7fc;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 3px solid #002f6c;
    }

    /* ── Divider ── */
    hr {
        border: none !important;
        border-top: 1px solid #e8ecf4 !important;
        margin: 1.5rem 0 !important;
    }

    /* ── Footer ── */
    .eds-footer {
        text-align: center;
        color: #9aa0b0;
        font-size: 0.78rem;
        padding: 1rem 0 0.5rem 0;
        border-top: 1px solid #e8ecf4;
        margin-top: 2rem;
    }
    .eds-footer a { color: #002f6c; text-decoration: none; font-weight: 500; }

    /* ── Live real-time sidebar card ── */
    .rt-card {
        background: #f4f7fc;
        border: 1px solid #dce5f0;
        border-radius: 8px;
        padding: 10px 12px;
        margin-bottom: 0.8rem;
    }
    .rt-card-header {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #6b7a99;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .rt-value-row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 4px;
        text-align: center;
    }
    .rt-val-label { font-size: 0.68rem; color: #9aa0b0; }
    .rt-val-num { font-size: 1.1rem; font-weight: 700; color: #002f6c; }
    .rt-val-unit { font-size: 0.65rem; color: #b0b8cc; }
</style>
""", unsafe_allow_html=True)

# Initialize database only (scraper runs separately as monitor.py)
db = FlowDatabase()

# Initialize devices from config on startup
@st.cache_resource
def init_devices():
    """Initialize devices from config into database."""
    for device_id, device_info in DEVICES.items():
        db.add_device(
            device_id=device_id,
            device_name=device_info.get("name", device_id),
            location=device_info.get("location", "")
        )
    return True

# Initialize devices (runs once per session)
init_devices()

DEFAULT_TZ = "Australia/Brisbane"


def format_measurement(value, unit):
    """Format measurement value with unit."""
    if value is None:
        return "N/A"
    return f"{value:.2f} {unit}"


def get_collection_stats(device_id):
    """Calculate data collection statistics."""
    # Get all measurements for the device
    measurements = db.get_measurements(device_id, limit=2000)
    if not measurements:
        return {}
    
    df = pd.DataFrame(measurements)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return {
        'total_points': len(df),
        'time_span': (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600,
        'collection_rate': len(df) / max(1, (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60),
    }


def fetch_latest_reading(device_id: str):
    """
    Fetch and return the latest reading (display-only, not stored) as fast as possible.
    
    Returns: (success: bool, message: str, timestamp: datetime, payload: dict)
    """
    device_config = DEVICES.get(device_id)
    if not device_config:
        return False, "Device is not configured", None, None

    scraper = DataScraper(db)
    # Force requests/API path to avoid Playwright overhead for speed
    scraper.force_requests = True
    url = device_config.get("url") or MONITOR_URL
    selectors = device_config.get("selectors") or {}

    try:
        data = asyncio.run(scraper.fetch_monitor_data(url, selectors))
    except RuntimeError:
        # Fallback if an event loop is already running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        data = loop.run_until_complete(scraper.fetch_monitor_data(url, selectors or {}))
        loop.close()

    if not data or not data.get("data"):
        return False, "Device communication error", None, None

    payload = data.get("data", {})
    depth_mm = payload.get("depth_mm")
    velocity_mps = payload.get("velocity_mps")
    flow_lps = payload.get("flow_lps")

    if all(v is None for v in (depth_mm, velocity_mps, flow_lps)):
        return False, "No sensor data received", None, None

    # Display-only; never stored
    timestamp = data.get("timestamp") or datetime.now(pytz.timezone(DEFAULT_TZ))
    message = "✓ Real-time data retrieved (display only, not saved to database)"
    return True, message, timestamp, payload


# ── EDS Header Banner ───────────────────────────────────────────────────────
st.markdown("""
<div class="eds-header">
    <div>
        <h1>💧 e-flow</h1>
        <div class="eds-subtitle">by EDS — Environmental Data Services &nbsp;|&nbsp;
            <a href="https://www.e-d-s.com.au" target="_blank"
               style="color:#ffc20e; text-decoration:none; font-weight:500;">www.e-d-s.com.au</a>
        </div>
        <div style="color:rgba(255,255,255,0.65); font-size:0.8rem; margin-top:4px;">
            Sewer Flow Monitoring &nbsp;·&nbsp; Depth &nbsp;·&nbsp; Velocity &nbsp;·&nbsp; Flow Rate
        </div>
    </div>
    <div class="eds-live-badge">
        <span class="eds-live-dot"></span>
        AUTO-COLLECT ACTIVE
    </div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # EDS logo strip
    st.markdown("""
    <div class="sidebar-logo">
        <h2>e-flow</h2>
        <div class="sidebar-tagline">by EDS — e-d-s.com.au</div>
    </div>
    """, unsafe_allow_html=True)

    # Auth header (logout / admin links)
    render_auth_header()

    # ── View mode ──
    st.markdown('<div class="sidebar-section-label">View Mode</div>', unsafe_allow_html=True)
    page_mode = st.selectbox(
        "Interface Mode",
        options=["Simplified View", "Full Dashboard", "EDS Product Overview"],
        index=0,
        help="Simplified View for standard users, Full Dashboard for power users, EDS Product Overview for sales demos.",
        label_visibility="collapsed",
    )
    st.session_state['page_mode'] = page_mode

    # ── Device selector ──
    st.markdown('<div class="sidebar-section-label">Device</div>', unsafe_allow_html=True)

    devices = db.get_devices()
    devices = filter_devices_for_user(devices)
    device_names = {d['device_name']: d['device_id'] for d in devices}

    if not device_names:
        st.warning("⚠️ No devices assigned to your account")
        if is_admin():
            st.info("Go to Admin Panel to assign devices")
        st.stop()

    selected_device_name: str = st.selectbox(
        "Select Device",
        options=sorted(device_names.keys()),
        key="device_selector",
        label_visibility="collapsed",
    )
    selected_device_id = device_names[selected_device_name]

    # Station details (plain card, no expander to avoid icon artefacts)
    device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)
    if device_info:
        st.markdown(f"""
        <div class="station-info-card">
            <strong>Station ID:</strong> {device_info['device_id']}<br>
            <strong>Location:</strong> {device_info['location'] or 'Not specified'}<br>
            <strong>Since:</strong> {str(device_info['created_at'])[:10]}
        </div>
        """, unsafe_allow_html=True)

    # ── Auto-collect status ──
    st.markdown(
        '<div class="collect-status-active">✔ Auto-collecting every 60 s</div>',
        unsafe_allow_html=True,
    )

    # ── Live data refresh ──
    refresh_clicked = st.button("🔄 Show Real-Time Data", type="primary", key="refresh_button",
                                use_container_width=True)
    if refresh_clicked:
        success, message, ts, payload = fetch_latest_reading(selected_device_id)
        if success and payload:
            st.session_state['realtime_data'] = {
                'depth_mm': payload.get("depth_mm"),
                'velocity_mps': payload.get("velocity_mps"),
                'flow_lps': payload.get("flow_lps"),
                'timestamp': ts,
            }
            ts_str = ts.astimezone(pytz.timezone(DEFAULT_TZ)).strftime('%H:%M:%S %Z') if ts else ""
            st.success(f"Live data retrieved at {ts_str}")
        else:
            st.error(message)

    if 'realtime_data' in st.session_state:
        rtd = st.session_state['realtime_data']
        depth_rt = rtd.get('depth_mm')
        vel_rt = rtd.get('velocity_mps')
        flow_rt = rtd.get('flow_lps')
        ts_rt = rtd.get('timestamp')
        has_rt = depth_rt is not None or vel_rt is not None or flow_rt is not None
        status_col = "#2e7d32" if has_rt else "#c62828"
        st.markdown(f"""
        <div class="rt-card">
            <div class="rt-card-header">
                <span style="color:{status_col};">{'● LIVE' if has_rt else '● NO DATA'}</span>
                <span>{ts_rt.strftime('%H:%M:%S') if ts_rt else ''}</span>
            </div>
            <div class="rt-value-row">
                <div>
                    <div class="rt-val-label">Depth</div>
                    <div class="rt-val-num">{f'{depth_rt:.1f}' if depth_rt is not None else '—'}</div>
                    <div class="rt-val-unit">mm</div>
                </div>
                <div>
                    <div class="rt-val-label">Velocity</div>
                    <div class="rt-val-num">{f'{vel_rt:.3f}' if vel_rt is not None else '—'}</div>
                    <div class="rt-val-unit">m/s</div>
                </div>
                <div>
                    <div class="rt-val-label">Flow</div>
                    <div class="rt-val-num">{f'{flow_rt:.1f}' if flow_rt is not None else '—'}</div>
                    <div class="rt-val-unit">L/s</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Time range ──
    st.markdown('<div class="sidebar-section-label">Time Window</div>', unsafe_allow_html=True)
    time_options = [
        (24, "24 hours"),
        (48, "2 days"),
        (72, "3 days"),
        (168, "7 days"),
        (720, "30 days"),
        (2160, "3 months"),
        (4320, "6 months"),
        (8760, "12 months"),
    ]
    time_range = st.selectbox(
        "Time Window",
        options=time_options,
        format_func=lambda x: x[1],
        index=0,
        key="time_range",
        label_visibility="collapsed",
    )[0]

    # ── System metrics ──
    st.markdown('<div class="sidebar-section-label">System</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    total_measurements = db.get_measurement_count()
    with col1:
        st.metric("Stations", db.get_device_count())
    with col2:
        st.metric("Records", total_measurements)
    # Show last record for the currently selected device (not global)
    device_latest = db.get_measurements(device_id=selected_device_id, limit=1) if selected_device_id else []
    if device_latest:
        try:
            ts_raw = device_latest[0]["timestamp"]
            latest_ts = pd.to_datetime(ts_raw)
            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.tz_localize(pytz.utc)
            local_ts = latest_ts.astimezone(pytz.timezone(DEFAULT_TZ))
            st.caption(f"Last record: {local_ts.strftime('%d/%m/%Y %H:%M')} AEST")
        except Exception:
            st.caption(f"Last record: {device_latest[0]['timestamp']}")
    else:
        st.caption("No data yet for this device")

    if selected_device_id:
        stats = get_collection_stats(selected_device_id)
        if stats:
            st.metric("Rate", f"{stats.get('collection_rate', 0):.1f}/min")

# Main content area
page_mode = st.session_state.get('page_mode', 'Simplified View')

if page_mode == 'EDS Product Overview':
    st.markdown('''
        <div style="background: linear-gradient(135deg, #002f6c 0%, #003f8f 90%); color: #fff; padding: 25px; border-radius: 14px;">
            <h2 style="margin-bottom: 0.4rem;">e-flow™ by EDS</h2>
            <p style="margin-bottom: 1.2rem; color: #f8f8f8; font-size: 1.1rem;">A premium sewer flow monitoring solution for depth, velocity, and flow data visualization, export, and reporting.</p>
            <ul style="margin: 0 0 1rem 1.2rem;">
                <li>🏆 Professional UI for water utilities</li>
                <li>📊 Real-time metrics and configurable dashboards</li>
                <li>📥 Data export (CSV/JSON/PDF) included</li>
                <li>🔒 Team roles + admin controls</li>
                <li>🌐 Deployable via Docker & Streamlit</li>
            </ul>
            <p style="margin-bottom:0;">Learn more at <a href='https://www.e-d-s.com.au' style='color:#ffc20e; font-weight:700;' target='_blank'>www.e-d-s.com.au</a></p>
        </div>
    ''', unsafe_allow_html=True)
    st.stop()

if page_mode == 'Simplified View':
    if selected_device_id:
        measurements = db.get_measurements(device_id=selected_device_id, limit=100000)
        if measurements:
            df_all = pd.DataFrame(measurements)
            df_all['timestamp'] = pd.to_datetime(df_all['timestamp'])
            latest = df_all.iloc[-1]

            # KPI row
            st.markdown(f"""
            <h2 style="margin-bottom:1rem;">📍 {selected_device_name}</h2>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-bottom:1.5rem;">
                <div class="kpi-card">
                    <div class="kpi-label">💧 Water Depth</div>
                    <div class="kpi-value">{f"{latest['depth_mm']:.1f}" if pd.notna(latest['depth_mm']) else '—'}<span class="kpi-unit">mm</span></div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">⚡ Flow Velocity</div>
                    <div class="kpi-value">{f"{latest['velocity_mps']:.3f}" if pd.notna(latest['velocity_mps']) else '—'}<span class="kpi-unit">m/s</span></div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">🌊 Flow Rate</div>
                    <div class="kpi-value">{f"{latest['flow_lps']:.1f}" if pd.notna(latest['flow_lps']) else '—'}<span class="kpi-unit">L/s</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("### 📊 Flow — Last 24 Hours")
            cutoff = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=24)
            df24 = df_all[df_all['timestamp'] >= cutoff]
            if not df24.empty:
                chart = px.line(df24, x='timestamp', y=['depth_mm', 'velocity_mps', 'flow_lps'],
                                labels={'value': 'Reading', 'variable': 'Metric', 'timestamp': 'Time'},
                                markers=False, template='plotly_white')
                chart.update_layout(
                    legend_title_text='Metric',
                    hovermode='x unified',
                    height=380,
                    font=dict(family='Inter, sans-serif'),
                )
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info('No data for last 24 hours. Showing all available data below.')

            # Download ALL data as CSV
            export_df = df_all[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
            export_df.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
            st.download_button(
                f'⬇️ Download ALL Data as CSV ({len(df_all)} records)',
                data=export_df.to_csv(index=False),
                file_name=f'{selected_device_id}_all_data.csv',
                mime='text/csv',
                use_container_width=True,
            )
        else:
            st.info('⏳ Waiting for first data collection. The background service collects every 60 seconds — refresh shortly.')
    else:
        st.warning('No device selected. Choose a device in the sidebar.')
    st.stop()

if selected_device_id:
    # Get measurements for selected device
    measurements = db.get_measurements(device_id=selected_device_id)
    
    if measurements:
        df = pd.DataFrame(measurements)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Filter by time range
        cutoff_time = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=time_range)
        df_filtered = df[df["timestamp"] >= cutoff_time].sort_values("timestamp")
        
        # Debug: show total vs filtered
        if df_filtered.empty and not df.empty:
            st.warning(f"⚠️ Found {len(df)} measurements, but none in the last {time_range} hours. Try selecting a longer time range.")
            st.info(f"Oldest data: {df['timestamp'].min()}, Latest data: {df['timestamp'].max()}")
        
        df = df_filtered
        
        if not df.empty:
            # ── Latest KPI cards ──────────────────────────────────────────
            latest = df.iloc[-1]
            last_update = latest["timestamp"]
            depth = latest["depth_mm"]
            velocity = latest["velocity_mps"]
            flow = latest["flow_lps"]

            st.markdown(f"""
            <h2 style="margin-bottom:1rem;">📍 {selected_device_name}</h2>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-bottom:1.5rem;">
                <div class="kpi-card">
                    <div class="kpi-label">💧 Water Depth</div>
                    <div class="kpi-value">{f'{depth:.1f}' if depth is not None else '—'}<span class="kpi-unit">mm</span></div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">⚡ Flow Velocity</div>
                    <div class="kpi-value">{f'{velocity:.3f}' if velocity is not None else '—'}<span class="kpi-unit">m/s</span></div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">🌊 Flow Rate</div>
                    <div class="kpi-value">{f'{flow:.1f}' if flow is not None else '—'}<span class="kpi-unit">L/s</span></div>
                </div>
            </div>
            <div style="font-size:0.78rem; color:#9aa0b0; margin-bottom:1.5rem;">
                Last reading: {last_update.strftime('%d/%m/%Y %H:%M:%S')}
                &nbsp;·&nbsp; {len(df)} data points in window
                &nbsp;·&nbsp; Auto-saving every 60 s
            </div>
            """, unsafe_allow_html=True)

            # ── Download ALL data (single CSV) ───────────────────────────
            all_measurements = db.get_measurements(device_id=selected_device_id, limit=100000)
            if all_measurements:
                all_df = pd.DataFrame(all_measurements)
                all_df_display = all_df[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
                all_df_display.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
                st.download_button(
                    label=f"⬇️ Download ALL data as CSV ({len(all_df)} records)",
                    data=all_df_display.to_csv(index=False),
                    file_name=f"eflow_{selected_device_id}_all_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Flow Rate chart ──────────────────────────────────────────
            st.markdown("## 📊 Flow Rate Analysis")

            col_range1, col_range2 = st.columns([1, 2])
            with col_range1:
                range_mode = st.radio(
                    "Date Range Mode",
                    options=["Quick Select", "Custom Range"],
                    index=0,
                    horizontal=True,
                )

            default_start = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=24)
            default_end = datetime.now(pytz.timezone(DEFAULT_TZ))
            
            if range_mode == "Quick Select":
                with col_range2:
                    # Quick select options
                    quick_options = [
                        (24, "24 hours"),
                        (48, "2 days"),
                        (72, "3 days"),
                        (168, "7 days"),
                        (720, "30 days"),
                    ]
                    selected_hours = st.selectbox(
                        "Select Time Window",
                        options=quick_options,
                        format_func=lambda x: x[1],
                        index=0,  # Default to 24 hours
                        key="quick_select_graph"
                    )[0]
                    
                    graph_start = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=selected_hours)
                    graph_end = datetime.now(pytz.timezone(DEFAULT_TZ))
            else:
                # Custom range with date/time pickers
                col_custom1, col_custom2 = st.columns(2)
                with col_custom1:
                    start_date = st.date_input(
                        "Start Date",
                        value=default_start.date(),
                        key="custom_start_date"
                    )
                    start_time = st.time_input(
                        "Start Time",
                        value=default_start.time(),
                        key="custom_start_time"
                    )
                    graph_start = datetime.combine(start_date, start_time)
                    graph_start = pytz.timezone(DEFAULT_TZ).localize(graph_start)
                
                with col_custom2:
                    end_date = st.date_input(
                        "End Date",
                        value=default_end.date(),
                        key="custom_end_date"
                    )
                    end_time = st.time_input(
                        "End Time",
                        value=default_end.time(),
                        key="custom_end_time"
                    )
                    graph_end = datetime.combine(end_date, end_time)
                    graph_end = pytz.timezone(DEFAULT_TZ).localize(graph_end)
            
            # Filter data for the graph
            df_graph = df[(df["timestamp"] >= graph_start) & (df["timestamp"] <= graph_end)].sort_values("timestamp")
            
            if not df_graph.empty:
                # Create prominent flow chart
                fig_main_flow = go.Figure()
                
                fig_main_flow.add_trace(go.Scatter(
                    x=df_graph["timestamp"],
                    y=df_graph["flow_lps"],
                    mode='lines+markers',
                    name='Flow Rate',
                    line=dict(color='#0066cc', width=3),
                    marker=dict(size=6, color='#0066cc'),
                    fill='tozeroy',
                    fillcolor='rgba(0, 102, 204, 0.1)',
                    hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>Flow: %{y:.2f} L/s<extra></extra>'
                ))
                
                fig_main_flow.update_layout(
                    title=dict(
                        text=f"Flow Rate Over Time - {selected_device_name}",
                        font=dict(size=20, family="Helvetica Neue, sans-serif", weight=500)
                    ),
                    xaxis_title="Time",
                    yaxis_title="Flow Rate (L/s)",
                    hovermode="x unified",
                    height=500,
                    template="plotly_white",
                    font=dict(family="Helvetica Neue, sans-serif"),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor='rgba(0,0,0,0.05)',
                        showline=True,
                        linecolor='rgba(0,0,0,0.2)'
                    ),
                    yaxis=dict(
                        showgrid=True,
                        gridcolor='rgba(0,0,0,0.05)',
                        showline=True,
                        linecolor='rgba(0,0,0,0.2)'
                    )
                )
                
                st.plotly_chart(fig_main_flow, use_container_width=True)
                
                # Show statistics for the selected range
                col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                with col_stat1:
                    st.metric("Average Flow", f"{df_graph['flow_lps'].mean():.2f} L/s")
                with col_stat2:
                    st.metric("Peak Flow", f"{df_graph['flow_lps'].max():.2f} L/s")
                with col_stat3:
                    st.metric("Minimum Flow", f"{df_graph['flow_lps'].min():.2f} L/s")
                with col_stat4:
                    total_volume = df_graph['flow_lps'].sum() * 60 / 1000  # Approximate total volume in m³
                    st.metric("Est. Total Volume", f"{total_volume:.2f} m³")
            else:
                st.info(f"📊 No data available for the selected date range ({graph_start.strftime('%Y-%m-%d %H:%M')} to {graph_end.strftime('%Y-%m-%d %H:%M')})")
            
            st.markdown("---")
            
            # ── Info row ─────────────────────────────────────────────────
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("🕒 Last Update", last_update.strftime('%d/%m %H:%M:%S'))
            with col_info2:
                st.metric("📊 Data Points", f"{len(df)} in {time_range}h")
            with col_info3:
                st.metric("⏱️ Rate", f"{len(df)/(time_range if time_range > 0 else 1):.1f} pts/hr")
            
            st.markdown("---")
            
            # Advanced analytics
            st.markdown("### 📈 Time Series Analysis")
            
            if len(df) >= 1:
                # Create tabs for different views - show even with 1 data point
                tab1, tab2, tab3, tab4 = st.tabs(["Depth", "Velocity", "Flow", "Summary Statistics"])
                
                with tab1:
                    fig_depth = px.line(
                        df, x="timestamp", y="depth_mm",
                        title="Water Depth Over Time",
                        labels={"depth_mm": "Depth (mm)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_depth.update_traces(
                        line=dict(color="#0066cc", width=2.5),
                        marker=dict(size=5, color="#0066cc")
                    )
                    fig_depth.update_layout(
                        hovermode="x unified",
                        height=500,
                        font=dict(family="Helvetica Neue Light, sans-serif", size=12, color="#333"),
                        plot_bgcolor="#f8f9fa",
                        paper_bgcolor="#ffffff",
                        margin=dict(l=60, r=40, t=60, b=60),
                        title_font=dict(size=18, family="Helvetica Neue Light, sans-serif", color="#002f6c"),
                    )
                    fig_depth.update_xaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    fig_depth.update_yaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    st.plotly_chart(fig_depth, use_container_width=True)
                    
                    if len(df) > 0:
                        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
                        with col_stats1:
                            st.metric("Mean", f"{df['depth_mm'].mean():.1f} mm")
                        with col_stats2:
                            st.metric("Max", f"{df['depth_mm'].max():.1f} mm")
                        with col_stats3:
                            st.metric("Min", f"{df['depth_mm'].min():.1f} mm")
                        with col_stats4:
                            st.metric("Std Dev", f"{df['depth_mm'].std():.1f} mm")
                

                with tab2:
                    fig_velocity = px.line(
                        df, x="timestamp", y="velocity_mps",
                        title="Flow Velocity Over Time",
                        labels={"velocity_mps": "Velocity (m/s)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_velocity.update_traces(
                        line=dict(color="#10b981", width=2.5),
                        marker=dict(size=5, color="#10b981")
                    )
                    fig_velocity.update_layout(
                        hovermode="x unified",
                        height=500,
                        font=dict(family="Helvetica Neue Light, sans-serif", size=12, color="#333"),
                        plot_bgcolor="#f8f9fa",
                        paper_bgcolor="#ffffff",
                        margin=dict(l=60, r=40, t=60, b=60),
                        title_font=dict(size=18, family="Helvetica Neue Light, sans-serif", color="#002f6c"),
                    )
                    fig_velocity.update_xaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    fig_velocity.update_yaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    st.plotly_chart(fig_velocity, use_container_width=True)
                    
                    if len(df) > 0:
                        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
                        with col_stats1:
                            st.metric("Mean", f"{df['velocity_mps'].mean():.2f} m/s")
                        with col_stats2:
                            st.metric("Max", f"{df['velocity_mps'].max():.2f} m/s")
                        with col_stats3:
                            st.metric("Min", f"{df['velocity_mps'].min():.2f} m/s")
                        with col_stats4:
                            st.metric("Std Dev", f"{df['velocity_mps'].std():.2f} m/s")
                
                
                with tab3:
                    fig_flow = px.line(
                        df, x="timestamp", y="flow_lps",
                        title="Flow Rate Over Time",
                        labels={"flow_lps": "Flow (L/s)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_flow.update_traces(
                        line=dict(color="#f59e0b", width=2.5),
                        marker=dict(size=5, color="#f59e0b")
                    )
                    fig_flow.update_layout(
                        hovermode="x unified",
                        height=500,
                        font=dict(family="Helvetica Neue Light, sans-serif", size=12, color="#333"),
                        plot_bgcolor="#f8f9fa",
                        paper_bgcolor="#ffffff",
                        margin=dict(l=60, r=40, t=60, b=60),
                        title_font=dict(size=18, family="Helvetica Neue Light, sans-serif", color="#002f6c"),
                    )
                    fig_flow.update_xaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    fig_flow.update_yaxes(
                        showgrid=True,
                        gridwidth=1,
                        gridcolor="#e8eaed",
                        showline=True,
                        linewidth=1,
                        linecolor="#333",
                    )
                    st.plotly_chart(fig_flow, use_container_width=True)
                
                with tab4:
                    st.markdown("""
                    <h4 style="font-weight: 500; letter-spacing: 0.3px; margin-bottom: 1.5rem;">
                        Aggregate Statistics
                    </h4>
                    """, unsafe_allow_html=True)
                    
                    # Create 3 columns for the three metrics
                    col_summary1, col_summary2, col_summary3 = st.columns(3)
                    
                    # DEPTH STATISTICS
                    with col_summary1:
                        st.markdown("<p style='font-weight: 500; color: #0066cc; margin-bottom: 1rem;'>💧 WATER DEPTH</p>", unsafe_allow_html=True)
                        
                        depth_mean = df['depth_mm'].mean()
                        depth_median = df['depth_mm'].median()
                        depth_std = df['depth_mm'].std()
                        depth_min = df['depth_mm'].min()
                        depth_max = df['depth_mm'].max()
                        depth_range = depth_max - depth_min
                        
                        st.metric("Mean", f"{depth_mean:.1f} mm")
                        st.metric("Median", f"{depth_median:.1f} mm")
                        st.metric("Std Dev", f"{depth_std:.1f} mm")
                        st.metric("Min", f"{depth_min:.1f} mm")
                        st.metric("Max", f"{depth_max:.1f} mm")
                        st.metric("Range", f"{depth_range:.1f} mm")
                    
                    # VELOCITY STATISTICS
                    with col_summary2:
                        st.markdown("<p style='font-weight: 500; color: #0066cc; margin-bottom: 1rem;'>⚡ FLOW VELOCITY</p>", unsafe_allow_html=True)
                        
                        vel_mean = df['velocity_mps'].mean()
                        vel_median = df['velocity_mps'].median()
                        vel_std = df['velocity_mps'].std()
                        vel_min = df['velocity_mps'].min()
                        vel_max = df['velocity_mps'].max()
                        vel_range = vel_max - vel_min
                        
                        st.metric("Mean", f"{vel_mean:.3f} m/s")
                        st.metric("Median", f"{vel_median:.3f} m/s")
                        st.metric("Std Dev", f"{vel_std:.3f} m/s")
                        st.metric("Min", f"{vel_min:.3f} m/s")
                        st.metric("Max", f"{vel_max:.3f} m/s")
                        st.metric("Range", f"{vel_range:.3f} m/s")
                    
                    # FLOW STATISTICS
                    with col_summary3:
                        st.markdown("<p style='font-weight: 500; color: #0066cc; margin-bottom: 1rem;'>🌊 FLOW RATE</p>", unsafe_allow_html=True)
                        
                        flow_mean = df['flow_lps'].mean()
                        flow_median = df['flow_lps'].median()
                        flow_std = df['flow_lps'].std()
                        flow_min = df['flow_lps'].min()
                        flow_max = df['flow_lps'].max()
                        flow_range = flow_max - flow_min
                        
                        st.metric("Mean", f"{flow_mean:.1f} L/s")
                        st.metric("Median", f"{flow_median:.1f} L/s")
                        st.metric("Std Dev", f"{flow_std:.1f} L/s")
                        st.metric("Min", f"{flow_min:.1f} L/s")
                        st.metric("Max", f"{flow_max:.1f} L/s")
                        st.metric("Range", f"{flow_range:.1f} L/s")
                    
                    # Distribution charts
                    st.markdown("---")
                    st.markdown("<h4 style='font-weight: 500; letter-spacing: 0.3px; margin-top: 1.5rem; margin-bottom: 1rem;'>Distribution Analysis</h4>", unsafe_allow_html=True)
                    
                    dist_col1, dist_col2 = st.columns(2)
                    
                    with dist_col1:
                        fig_hist_depth = px.histogram(
                            df, x="depth_mm",
                            title="Depth Distribution",
                            nbins=20,
                            labels={"depth_mm": "Depth (mm)", "count": "Frequency"}
                        )
                        fig_hist_depth.update_traces(marker=dict(color="#1f77b4"))
                        st.plotly_chart(fig_hist_depth, width="stretch", use_container_width=True)
                    
                    with dist_col2:
                        fig_hist_flow = px.histogram(
                            df, x="flow_lps",
                            title="Flow Distribution",
                            nbins=20,
                            labels={"flow_lps": "Flow (L/s)", "count": "Frequency"}
                        )
                        fig_hist_flow.update_traces(marker=dict(color="#ff7f0e"))
                        st.plotly_chart(fig_hist_flow, width="stretch", use_container_width=True)
                    
                    # Data collection info
                    st.markdown("---")
                    st.markdown("<h4 style='font-weight: 500; letter-spacing: 0.3px; margin-top: 1.5rem; margin-bottom: 1rem;'>Collection Summary</h4>", unsafe_allow_html=True)
                    
                    collection_col1, collection_col2, collection_col3, collection_col4 = st.columns(4)
                    
                    with collection_col1:
                        st.metric("Total Points", len(df))
                    
                    with collection_col2:
                        time_span_hours = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600
                        st.metric("Time Span", f"{time_span_hours:.1f}h")
                    
                    with collection_col3:
                        collection_rate = len(df) / max(1, time_span_hours)
                        st.metric("Collection Rate", f"{collection_rate:.1f}/hr")
                    
                    with collection_col4:
                        completeness = (len(df) - df[['depth_mm', 'velocity_mps', 'flow_lps']].isna().sum().max()) / max(1, len(df)) * 100
                        st.metric("Data Completeness", f"{completeness:.0f}%")
            
            # Data table
            st.markdown("### 📋 Data Table")
            display_df = df[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
            display_df.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
            display_df["Timestamp"] = display_df["Timestamp"].astype(str)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Export functionality
            st.markdown("### 📥 Export Data")
            col1, col2 = st.columns(2)
            
            with col1:
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download Current View (CSV)",
                    data=csv,
                    file_name=f"flow_data_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            
            with col2:
                json_str = df.to_json(orient="records", date_format="iso")
                st.download_button(
                    label="⬇️ Download Current View (JSON)",
                    data=json_str,
                    file_name=f"flow_data_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.info("No data available for the selected time range. Background collection is running — check back shortly.")
            st.markdown("## 📊 Flow Rate Analysis")
            st.warning("No data in the selected time window. Try selecting a longer time range.")
    else:
        st.info("⏳ **Waiting for first data collection** — the background service is running and will store data within the next 60 seconds. Refresh this page shortly.")
else:
    st.info("👈 Select a device from the sidebar to view data.")

# ── Footer ───────────────────────────────────────────────────────────────────
st.markdown(
    f"""<div class="eds-footer">
        e-flow &copy; {datetime.now().year} &nbsp;·&nbsp;
        <a href="https://www.e-d-s.com.au" target="_blank">EDS — Environmental Data Services</a>
        &nbsp;·&nbsp; {datetime.now(pytz.timezone(DEFAULT_TZ)).strftime('%d/%m/%Y %H:%M %Z')}
        &nbsp;·&nbsp; Auto-collection active
    </div>""",
    unsafe_allow_html=True,
)
