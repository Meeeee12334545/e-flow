import asyncio
import os
import sys
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
import logging
import json

import streamlit as st
import pandas as pd
import pytz
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from database import FlowDatabase
from scraper import DataScraper
from config import DEVICES, MONITOR_URL, MONITOR_ENABLED

from streamlit_auth import init_auth_state, is_authenticated, is_admin, login_page, render_auth_header, filter_devices_for_user

# Initialize authentication state
init_auth_state()

# Check if user is authenticated - if not, show login page
if not is_authenticated():
    login_page()
    st.stop()

# Ensure Playwright browsers are installed for Streamlit Cloud
@st.cache_resource
def ensure_playwright_installed():
    """Install Playwright browsers if not already installed."""
    try:
        # Ensure system deps (libnspr4, libnss3, etc.) and browser are present
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            capture_output=True,
            timeout=120
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            timeout=120
        )
    except Exception as e:
        pass  # Silent fail - monitoring happens elsewhere
    return True

# Install on startup (cached so only runs once)
ensure_playwright_installed()

# Setup logging before anything else
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data collection runs in a separate monitor service/container.
# This Streamlit app is read-only and visualizes stored data.

st.set_page_config(
    page_title="e-flow | Hydrological Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Professional design system — Inter font, professional blue palette
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --bg: #f4f7fb;
        --surface: #ffffff;
        --surface-soft: #f8fbff;
        --border: #dfe7ef;
        --text: #233047;
        --muted: #6b7280;
        --primary: #0f4c81;
        --primary-light: #1a6bb5;
        --primary-soft: #e7f0ff;
        --accent: #0b76ca;
        --accent-soft: #dbe9ff;
        --success: #047c3d;
        --success-soft: #daf9e6;
        --warning: #b45309;
        --warning-soft: #fef3c7;
        --radius-sm: 12px;
        --radius-md: 18px;
        --radius-lg: 22px;
        --shadow-sm: 0 4px 12px rgba(15, 76, 129, 0.06);
        --shadow-md: 0 14px 32px rgba(15, 76, 129, 0.08);
        --shadow-lg: 0 24px 60px rgba(15, 76, 129, 0.10);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: #f4f7fb !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }

    [data-testid="stAppViewContainer"] > .main {
        background: #f4f7fb !important;
    }

    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
        box-sizing: border-box;
    }

    .block-container {
        padding: 1.5rem 2rem 3rem !important;
        max-width: 1400px !important;
    }

    /* ── Typography ── */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text) !important;
        font-weight: 700 !important;
    }

    h1 { font-size: 2.6rem !important; line-height: 1.15 !important; }
    h2 { font-size: 1.7rem !important; line-height: 1.25 !important; }
    h3 { font-size: 1.25rem !important; }

    p, span, li { line-height: 1.7 !important; }

    /* ── Hero Card ── */
    .hero-card {
        background: linear-gradient(135deg, #0f4c81 0%, #1a6bb5 60%, #0b76ca 100%);
        border-radius: var(--radius-lg);
        padding: 36px 40px;
        box-shadow: var(--shadow-lg);
        color: #ffffff;
    }

    .hero-title {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        margin: 0.5rem 0 !important;
        color: #ffffff !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }

    .hero-subtitle {
        margin: 0.75rem 0 1.5rem 0 !important;
        font-size: 1.05rem !important;
        color: rgba(255,255,255,0.85) !important;
        max-width: 560px;
        line-height: 1.6 !important;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 1rem;
        border-radius: 999px;
        background: rgba(255,255,255,0.18);
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        border: 1px solid rgba(255,255,255,0.3);
    }

    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.55rem 1.1rem;
        border-radius: 999px;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        margin-right: 0.5rem;
        margin-bottom: 0.5rem;
    }

    /* ── Status / Live Card ── */
    .status-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 28px 20px;
        box-shadow: var(--shadow-md);
        text-align: center;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    .status-live-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--success);
        display: inline-block;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.6; transform: scale(0.9); }
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.6rem 1.4rem;
        border-radius: 999px;
        background: var(--success-soft);
        color: var(--success) !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        letter-spacing: 0.06em;
        margin-bottom: 0.75rem;
        border: 1px solid rgba(4, 124, 61, 0.2);
    }

    .status-note {
        font-size: 0.88rem !important;
        color: var(--muted) !important;
        line-height: 1.5 !important;
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 24px;
        box-shadow: var(--shadow-md);
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }

    .metric-card:hover {
        box-shadow: var(--shadow-lg);
        transform: translateY(-2px);
    }

    .metric-label {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0 0 0.6rem 0 !important;
    }

    .metric-value {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        margin: 0 !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }

    .metric-value.green { color: var(--success) !important; }
    .metric-value.amber { color: var(--warning) !important; }

    .metric-unit {
        font-size: 1rem !important;
        font-weight: 400 !important;
        color: var(--muted) !important;
        margin-left: 4px;
    }

    /* ── Section Card ── */
    .section-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 28px 30px;
        box-shadow: var(--shadow-sm);
        margin-bottom: 1.5rem;
    }

    .section-title {
        font-size: 1.35rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        margin: 0 0 0.75rem 0 !important;
        letter-spacing: -0.01em;
    }

    .section-subtitle {
        font-size: 0.9rem !important;
        color: var(--muted) !important;
        margin: 0 0 1.5rem 0 !important;
    }

    /* ── Streamlit native metric override ── */
    div[data-testid="metric-container"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-md) !important;
        padding: 1rem 1.25rem !important;
        box-shadow: var(--shadow-sm) !important;
    }

    div[data-testid="metric-container"] label {
        color: var(--muted) !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }

    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: var(--primary) !important;
        font-weight: 700 !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: var(--radius-sm) !important;
        background: linear-gradient(135deg, #0f4c81 0%, #0a3c67 100%) !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 6px 18px rgba(15, 76, 129, 0.22) !important;
        padding: 0.6rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }

    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 10px 24px rgba(15, 76, 129, 0.3) !important;
    }

    .stButton > button[kind="secondary"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        border: 1.5px solid var(--primary) !important;
        box-shadow: none !important;
    }

    /* Download buttons */
    .stDownloadButton > button {
        border-radius: var(--radius-sm) !important;
        border: 1.5px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.2rem !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid var(--border) !important;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 1.5rem !important;
    }

    section[data-testid="stSidebar"] h2 {
        font-size: 1rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background: var(--primary-soft) !important;
        border-radius: var(--radius-sm) !important;
        padding: 5px !important;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 500 !important;
        color: var(--muted) !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 700 !important;
        box-shadow: var(--shadow-sm) !important;
    }

    /* ── Selectbox & inputs ── */
    .stSelectbox > div > div {
        border-radius: var(--radius-sm) !important;
        border-color: var(--border) !important;
        background: var(--surface) !important;
    }

    /* ── Code ── */
    code {
        background: #f1f5f9 !important;
        padding: 0.2rem 0.45rem !important;
        border-radius: 6px !important;
        font-size: 0.85em !important;
        color: var(--primary) !important;
    }

    /* ── Footer ── */
    .app-footer {
        border-top: 1px solid var(--border);
        padding: 1.25rem 0 0.5rem 0;
        margin-top: 3rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .app-footer-brand {
        font-weight: 700 !important;
        color: var(--primary) !important;
        font-size: 0.95rem !important;
    }

    .app-footer-meta {
        font-size: 0.82rem !important;
        color: var(--muted) !important;
    }

    /* ── Responsive ── */
    @media (max-width: 768px) {
        .block-container { padding: 1rem 1rem 2rem !important; }
        .hero-card { padding: 24px 20px !important; }
        .hero-title { font-size: 2rem !important; }
        .metric-value { font-size: 1.9rem !important; }
        .section-card { padding: 20px !important; }
    }
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
    Fetch and return the latest real-time reading as fast as possible.
    The reading is returned for display; persistence is handled by the monitor service.

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

    # Return for display; persistence is handled by the monitor service
    timestamp = data.get("timestamp") or datetime.now(pytz.timezone(DEFAULT_TZ))
    message = "✓ Live reading retrieved — monitor service stores data automatically"
    return True, message, timestamp, payload


# Page header
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    <div class="hero-card">
        <span class="hero-pill">🌊 Hydrological Intelligence</span>
        <h1 class="hero-title">e-flow™ by EDS</h1>
        <p class="hero-subtitle">Professional sewer flow monitoring, analytics and reporting for depth, velocity and flow performance.</p>
        <div style="display:flex; flex-wrap: wrap; gap: 8px;">
            <span class="hero-badge" style="background: rgba(255,255,255,0.18); color: #ffffff; border: 1px solid rgba(255,255,255,0.3);">📡 Live data overview</span>
            <span class="hero-badge" style="background: rgba(255,255,255,0.18); color: #ffffff; border: 1px solid rgba(255,255,255,0.3);">📈 Historical analytics</span>
            <span class="hero-badge" style="background: rgba(255,255,255,0.18); color: #ffffff; border: 1px solid rgba(255,255,255,0.3);">⚙️ Operational insights</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div class="status-card">
        <div class="status-pill"><span class="status-live-dot"></span>LIVE</div>
        <div class="status-note">Auto-sync enabled<br>Data saved automatically<br>by monitor service</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)


# Sidebar configuration
with st.sidebar:
    # Add authentication header
    render_auth_header()

    st.markdown("## Interface")

    page_mode = st.selectbox(
        "View mode",
        options=["Simplified View", "Full Dashboard", "EDS Product Overview"],
        index=0,
        help="Simplified View for standard users, Full Dashboard for power users, EDS Product Overview for sales demos."
    )
    st.session_state['page_mode'] = page_mode

    st.markdown("## Device")

    st.markdown("""
    <div style="background: #f0f7ff; border-left: 3px solid #0f4c81; padding: 10px 12px; border-radius: 6px; margin-bottom: 1rem;">
        <p style="font-size: 0.82rem; margin: 0; color: #233047; line-height: 1.6;">
            <strong>Status:</strong> Connected &amp; streaming<br>
            <span style="color: #6b7280;">• Interval: 60 s &nbsp;• WAL persistence: on</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Monitor status
    if MONITOR_ENABLED:
        st.success("✔ Monitor service: active")
    else:
        st.info("ℹ️ Monitor service: not running locally. Start monitor.py to collect data.")

    # Build device mapping from database
    devices = db.get_devices()
    
    # Filter devices based on user's access rights
    devices = filter_devices_for_user(devices)
    
    device_names = {d['device_name']: d['device_id'] for d in devices}
    
    if not device_names:
        st.warning("⚠️ No devices assigned to your account")
        if is_admin():
            st.info("As an admin, go to the Admin Panel to manage device assignments")
        st.stop()
    
    selected_device_name: str = st.selectbox(
        "Select Device",
        options=sorted(device_names.keys()),
        key="device_selector",
        label_visibility="collapsed"
    )
    selected_device_id = device_names[selected_device_name]
    
    # Get selected device info
    device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)
    if device_info:
        with st.expander("📋 Station Details", expanded=False):
            st.markdown(f"""
            <div style="font-family: 'Helvetica Neue', sans-serif; font-weight: 300; line-height: 1.8;">
                <p><strong style="font-weight: 500;">Station ID</strong><br><code>{device_info['device_id']}</code></p>
                <p><strong style="font-weight: 500;">Location</strong><br>{device_info['location'] or 'Not specified'}</p>
                <p><strong style="font-weight: 500;">Initialized</strong><br><code>{device_info['created_at']}</code></p>
            </div>
            """, unsafe_allow_html=True)

        # Manual refresh to pull the newest reading into the app (fast API path)
        refresh_clicked = st.button("Show Real-Time Data", type="primary", key="refresh_button")
        
        if refresh_clicked:
            success, message, ts, payload = fetch_latest_reading(selected_device_id)
            if success and payload:
                st.session_state['realtime_data'] = {
                    'depth_mm': payload.get("depth_mm"),
                    'velocity_mps': payload.get("velocity_mps"),
                    'flow_lps': payload.get("flow_lps"),
                    'timestamp': ts
                }
                ts_str = ts.astimezone(pytz.timezone(DEFAULT_TZ)).strftime('%Y-%m-%d %H:%M:%S %Z') if ts else ""
                st.success(f"{message} at {ts_str}")
            else:
                st.error(message)
        
        # Display real-time data if available
        if 'realtime_data' in st.session_state:
            rtd = st.session_state['realtime_data']
            depth = rtd.get('depth_mm')
            velocity = rtd.get('velocity_mps')
            flow = rtd.get('flow_lps')
            ts = rtd.get('timestamp')
            
            # Determine if we have valid data (green) or no data (red)
            has_data = depth is not None or velocity is not None or flow is not None
            bg_color = "linear-gradient(135deg, #e8f5e9 0%, #ffffff 100%)" if has_data else "linear-gradient(135deg, #ffebee 0%, #ffffff 100%)"
            border_color = "#4caf50" if has_data else "#f44336"
            text_color = "#2e7d32" if has_data else "#c62828"
            status_icon = "🟢" if has_data else "🔴"
            
            st.markdown(f"""
            <div style="background: {bg_color}; 
                        padding: 15px; border-radius: 10px; border: 2px solid {border_color};
                        margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <span style="font-size: 0.85rem; color: {text_color}; font-weight: 500;">{status_icon} LIVE DATA</span>
                    <span style="font-size: 0.75rem; color: #666;">{ts.strftime('%H:%M:%S') if ts else 'N/A'}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: #666; margin-bottom: 3px;">Depth</div>
                        <div style="font-size: 1.3rem; font-weight: 500; color: {text_color};">{f'{depth:.1f}' if depth is not None else 'N/A'}</div>
                        <div style="font-size: 0.7rem; color: #888;">mm</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: #666; margin-bottom: 3px;">Velocity</div>
                        <div style="font-size: 1.3rem; font-weight: 500; color: {text_color};">{f'{velocity:.3f}' if velocity is not None else 'N/A'}</div>
                        <div style="font-size: 0.7rem; color: #888;">m/s</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: #666; margin-bottom: 3px;">Flow</div>
                        <div style="font-size: 1.3rem; font-weight: 500; color: {text_color};">{f'{flow:.1f}' if flow is not None else 'N/A'}</div>
                        <div style="font-size: 0.7rem; color: #888;">L/s</div>
                    </div>
                </div>
                <div style="margin-top: 8px; font-size: 0.7rem; color: #999; text-align: center;">
                    ✓ Data is automatically saved to the database by the monitor service
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Optional: allow one-click store from Streamlit or admin override
            allow_streamlit_writes = os.getenv("ALLOW_STREAMLIT_WRITES", "").lower() in ("1", "true", "yes")
            can_store = allow_streamlit_writes or is_admin()
            if can_store and has_data:
                if is_admin() and not allow_streamlit_writes:
                    st.info("Admin override enabled: You can store this current reading directly to the database.")
                col_store, _ = st.columns([1,3])
                with col_store:
                    if st.button("Save current live reading to database", key="store_now_button"):
                        try:
                            writer = DataScraper(db)
                            stored = writer.store_measurement(
                                device_id=selected_device_id,
                                device_name=selected_device_name,
                                depth_mm=depth,
                                velocity_mps=velocity,
                                flow_lps=flow,
                                allow_storage=True
                            )
                            if stored:
                                st.success("✅ Reading stored to database")
                            else:
                                st.info("ℹ️ No change detected — not stored")
                        except Exception as e:
                            st.error(f"❌ Failed to store reading: {e}")
            elif has_data:
                st.caption("Enable ALLOW_STREAMLIT_WRITES or sign in as admin to store the current reading.")
    else:
        st.error("⚠️ No devices configured")
        st.info("Expected devices: " + ", ".join(DEVICES.keys()))
        selected_device_id = None

    st.divider()

    # System stats
    st.markdown("## System")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Stations", db.get_device_count(), help="Connected field devices")
    with col2:
        total_measurements = db.get_measurement_count()
        st.metric("Records", total_measurements, help="Total stored measurements")
    # Last ingest indicator
    latest_rows = db.get_measurements(limit=1)
    if latest_rows:
        try:
            ts_raw = latest_rows[0]["timestamp"]
            latest_ts = pd.to_datetime(ts_raw)
            if latest_ts.tzinfo is None:
                latest_ts = latest_ts.tz_localize(pytz.utc)
            else:
                latest_ts = pd.Timestamp(latest_ts)
            local_ts = latest_ts.astimezone(pytz.timezone(DEFAULT_TZ))
            st.caption(f"Last record: {local_ts.strftime('%Y-%m-%d %H:%M %Z')}")
        except Exception:
            st.caption(f"Last record: {latest_rows[0]['timestamp']}")

    if total_measurements == 0:
        st.warning("⚠️ No measurements yet.")
        st.info("Start the monitor service to collect data automatically.")

    if selected_device_id:
        stats = get_collection_stats(selected_device_id)
        if stats:
            st.metric("Collection Rate", f"{stats.get('collection_rate', 0):.1f}/min", help="Average points per minute")

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
        measurements = db.get_measurements(device_id=selected_device_id)
        if measurements:
            df = pd.DataFrame(measurements)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.sort_values('timestamp', inplace=True)
            latest = df.iloc[-1]
            now_local = datetime.now(pytz.timezone(DEFAULT_TZ))
            latest_depth = f"{latest['depth_mm']:.1f}" if pd.notna(latest['depth_mm']) else 'N/A'
            latest_velocity = f"{latest['velocity_mps']:.3f}" if pd.notna(latest['velocity_mps']) else 'N/A'
            latest_flow = f"{latest['flow_lps']:.1f}" if pd.notna(latest['flow_lps']) else 'N/A'

            # Latest reading timestamp
            try:
                last_ts = pd.to_datetime(latest['timestamp'])
                if last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize(pytz.utc)
                last_ts_local = last_ts.astimezone(pytz.timezone(DEFAULT_TZ))
                last_ts_str = last_ts_local.strftime('%d %b %Y, %H:%M %Z')
            except Exception:
                last_ts_str = str(latest['timestamp'])

            st.markdown(f"""
            <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; margin-bottom: 1.75rem;">
                <div class="metric-card">
                    <p class="metric-label">💧 Water Depth</p>
                    <p class="metric-value">{latest_depth}<span class="metric-unit">mm</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">⚡ Flow Velocity</p>
                    <p class="metric-value green">{latest_velocity}<span class="metric-unit">m/s</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">🌊 Flow Rate</p>
                    <p class="metric-value amber">{latest_flow}<span class="metric-unit">L/s</span></p>
                </div>
            </div>
            <p style="font-size: 0.82rem; color: #6b7280; margin: -0.75rem 0 1.5rem 4px;">
                ✓ Last reading: {last_ts_str} &nbsp;·&nbsp; {len(df)} total records in database
            </p>
            """, unsafe_allow_html=True)

            time_window_options = [
                (24, '24 hours'),
                (48, '2 days'),
                (72, '3 days'),
                (168, '7 days'),
                (720, '30 days')
            ]
            col_title, col_picker = st.columns([2, 1])
            with col_title:
                st.markdown("""
                <h2 style="margin: 0; font-weight: 700; letter-spacing: -0.02em; color: #233047;">Performance trend</h2>
                <p style="margin: 0.25rem 0 0 0; color: #6b7280; font-size: 0.92rem;">Flow rate, depth and velocity over the selected window.</p>
                """, unsafe_allow_html=True)
            with col_picker:
                selected_window, selected_window_label = st.selectbox(
                    'Time window',
                    options=time_window_options,
                    format_func=lambda x: x[1],
                    index=0,
                    key='simplified_view_window'
                )

            cutoff = now_local - timedelta(hours=selected_window)
            df_window = df[df['timestamp'] >= cutoff].sort_values('timestamp')
            show_note = False
            if df_window.empty:
                show_note = True
                df_window = df.sort_values('timestamp')

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(
                    x=df_window['timestamp'],
                    y=df_window['flow_lps'],
                    mode='lines+markers',
                    name='Flow (L/s)',
                    line=dict(color='#0f4c81', width=2.5),
                    marker=dict(size=5),
                    fill='tozeroy',
                    fillcolor='rgba(15, 76, 129, 0.07)',
                ),
                secondary_y=False
            )
            fig.add_trace(
                go.Scatter(
                    x=df_window['timestamp'],
                    y=df_window['depth_mm'],
                    mode='lines+markers',
                    name='Depth (mm)',
                    line=dict(color='#047c3d', width=2, dash='dash'),
                    marker=dict(size=5)
                ),
                secondary_y=False
            )
            fig.add_trace(
                go.Scatter(
                    x=df_window['timestamp'],
                    y=df_window['velocity_mps'],
                    mode='lines+markers',
                    name='Velocity (m/s)',
                    line=dict(color='#b45309', width=2, dash='dot'),
                    marker=dict(size=5)
                ),
                secondary_y=True
            )
            fig.update_layout(
                title=None,
                legend=dict(
                    orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                    font=dict(size=12)
                ),
                hovermode='x unified',
                margin=dict(l=0, r=0, t=40, b=0),
                template='plotly_white',
                height=440,
                paper_bgcolor='#ffffff',
                plot_bgcolor='#ffffff',
                font=dict(family='Inter, -apple-system, sans-serif', color='#233047', size=12),
                xaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef'),
                yaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef'),
            )
            fig.update_xaxes(title_text='Time')
            fig.update_yaxes(title_text='Flow (L/s) / Depth (mm)', secondary_y=False)
            fig.update_yaxes(title_text='Velocity (m/s)', secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

            if show_note:
                st.info(
                    f'ℹ️ No data in the last {selected_window_label}. Showing all available history instead.'
                )

            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
            col_download1, col_download2, _ = st.columns([1, 1, 2])
            csv_data = df.to_csv(index=False)
            json_data = df.to_json(orient='records', date_format='iso')
            with col_download1:
                st.download_button('⬇ Download CSV', data=csv_data,
                                   file_name=f'{selected_device_id}_data.csv', mime='text/csv',
                                   use_container_width=True)
            with col_download2:
                st.download_button('⬇ Download JSON', data=json_data,
                                   file_name=f'{selected_device_id}_data.json',
                                   mime='application/json', use_container_width=True)
        else:
            st.markdown("""
            <div style="background: #ffffff; border: 1px solid #dfe7ef; border-radius: 18px; padding: 40px; text-align: center; margin: 2rem 0;">
                <p style="font-size: 2.5rem; margin: 0 0 1rem;">📡</p>
                <h3 style="color: #233047; margin: 0 0 0.5rem;">Awaiting first reading</h3>
                <p style="color: #6b7280; margin: 0 0 1.5rem;">No measurements have been stored yet for this device.</p>
                <p style="color: #6b7280; font-size: 0.9rem;">Start the <code>monitor.py</code> service to begin collecting data automatically.</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning('No device selected. Choose a device in the sidebar.')
    st.stop()

if selected_device_id:
    # ── Full Dashboard ──────────────────────────────────────────────────────
    # Time range selector for the full dashboard
    _fd_time_opts = [
        (24, "24 hours"),
        (48, "2 days"),
        (72, "3 days"),
        (168, "7 days"),
        (720, "30 days"),
        (2160, "3 months"),
        (4320, "6 months"),
        (8760, "12 months"),
    ]
    col_fd_title, col_fd_range = st.columns([2, 1])
    with col_fd_title:
        st.markdown(f"""
        <h2 style="margin: 0; font-weight: 700; letter-spacing: -0.02em; color: #233047;">
            Full Dashboard — {selected_device_name}
        </h2>
        <p style="margin: 0.25rem 0 1rem; color: #6b7280; font-size: 0.92rem;">
            Detailed time-series analytics and statistics
        </p>
        """, unsafe_allow_html=True)
    with col_fd_range:
        time_range, _time_label = st.selectbox(
            "Time window",
            options=_fd_time_opts,
            format_func=lambda x: x[1],
            index=3,  # Default: 7 days
            key="fd_time_range"
        )

    # Get measurements for selected device
    measurements = db.get_measurements(device_id=selected_device_id)

    if measurements:
        df = pd.DataFrame(measurements)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Filter by time range
        cutoff_time = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=time_range)
        df_filtered = df[df["timestamp"] >= cutoff_time].sort_values("timestamp")

        if df_filtered.empty and not df.empty:
            st.warning(
                f"⚠️ No data in the last {_time_label}. "
                f"Oldest record: {df['timestamp'].min().strftime('%Y-%m-%d %H:%M')}, "
                f"Latest: {df['timestamp'].max().strftime('%Y-%m-%d %H:%M')}. "
                "Try a wider time window."
            )

        df = df_filtered

        if not df.empty:
            latest = df.iloc[-1]
            last_update = latest["timestamp"]

            # ── KPI metric cards ────────────────────────────────────────────
            depth = latest["depth_mm"]
            velocity = latest["velocity_mps"]
            flow = latest["flow_lps"]
            depth_str = f"{depth:.1f}" if depth is not None else "N/A"
            velocity_str = f"{velocity:.3f}" if velocity is not None else "N/A"
            flow_str = f"{flow:.1f}" if flow is not None else "N/A"

            try:
                lu_ts = pd.to_datetime(last_update)
                if lu_ts.tzinfo is None:
                    lu_ts = lu_ts.tz_localize(pytz.utc)
                lu_local = lu_ts.astimezone(pytz.timezone(DEFAULT_TZ))
                lu_str = lu_local.strftime('%d %b %Y, %H:%M %Z')
            except Exception:
                lu_str = str(last_update)

            st.markdown(f"""
            <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; margin-bottom: 0.5rem;">
                <div class="metric-card">
                    <p class="metric-label">💧 Water Depth</p>
                    <p class="metric-value">{depth_str}<span class="metric-unit">mm</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">⚡ Flow Velocity</p>
                    <p class="metric-value green">{velocity_str}<span class="metric-unit">m/s</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">🌊 Flow Rate</p>
                    <p class="metric-value amber">{flow_str}<span class="metric-unit">L/s</span></p>
                </div>
            </div>
            <p style="font-size: 0.82rem; color: #6b7280; margin: 0 0 1.5rem 4px;">
                ✓ Last reading: {lu_str} &nbsp;·&nbsp; {len(df)} records in selected window
            </p>
            """, unsafe_allow_html=True)

            # ── Main flow chart ─────────────────────────────────────────────
            st.markdown("""
            <p class="section-title" style="margin-top: 0.5rem;">📊 Flow Rate Analysis</p>
            """, unsafe_allow_html=True)

            col_range1, col_range2 = st.columns([1, 2])
            with col_range1:
                range_mode = st.radio(
                    "Date Range Mode",
                    options=["Quick Select", "Custom Range"],
                    index=0,
                    horizontal=True
                )

            default_start = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=24)
            default_end = datetime.now(pytz.timezone(DEFAULT_TZ))

            if range_mode == "Quick Select":
                with col_range2:
                    quick_options = [
                        (24, "24 hours"),
                        (48, "2 days"),
                        (72, "3 days"),
                        (168, "7 days"),
                        (720, "30 days"),
                    ]
                    selected_hours, _ = st.selectbox(
                        "Chart window",
                        options=quick_options,
                        format_func=lambda x: x[1],
                        index=0,
                        key="quick_select_graph"
                    )
                    graph_start = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=selected_hours)
                    graph_end = datetime.now(pytz.timezone(DEFAULT_TZ))
            else:
                col_custom1, col_custom2 = st.columns(2)
                with col_custom1:
                    start_date = st.date_input("Start Date", value=default_start.date(), key="custom_start_date")
                    start_time = st.time_input("Start Time", value=default_start.time(), key="custom_start_time")
                    graph_start = pytz.timezone(DEFAULT_TZ).localize(datetime.combine(start_date, start_time))
                with col_custom2:
                    end_date = st.date_input("End Date", value=default_end.date(), key="custom_end_date")
                    end_time = st.time_input("End Time", value=default_end.time(), key="custom_end_time")
                    graph_end = pytz.timezone(DEFAULT_TZ).localize(datetime.combine(end_date, end_time))

            df_graph = df[(df["timestamp"] >= graph_start) & (df["timestamp"] <= graph_end)].sort_values("timestamp")

            if not df_graph.empty:
                fig_main_flow = go.Figure()
                fig_main_flow.add_trace(go.Scatter(
                    x=df_graph["timestamp"],
                    y=df_graph["flow_lps"],
                    mode='lines+markers',
                    name='Flow Rate (L/s)',
                    line=dict(color='#0f4c81', width=2.5),
                    marker=dict(size=5, color='#0f4c81'),
                    fill='tozeroy',
                    fillcolor='rgba(15, 76, 129, 0.07)',
                    hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>Flow: %{y:.2f} L/s<extra></extra>'
                ))
                fig_main_flow.update_layout(
                    xaxis_title="Time",
                    yaxis_title="Flow Rate (L/s)",
                    hovermode="x unified",
                    height=420,
                    template="plotly_white",
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    font=dict(family='Inter, -apple-system, sans-serif', color='#233047', size=12),
                    margin=dict(l=0, r=0, t=20, b=0),
                    xaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef'),
                    yaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef'),
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                )
                st.plotly_chart(fig_main_flow, use_container_width=True)

                col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                with col_stat1:
                    st.metric("Avg Flow", f"{df_graph['flow_lps'].mean():.1f} L/s")
                with col_stat2:
                    st.metric("Peak Flow", f"{df_graph['flow_lps'].max():.1f} L/s")
                with col_stat3:
                    st.metric("Min Flow", f"{df_graph['flow_lps'].min():.1f} L/s")
                with col_stat4:
                    total_vol = df_graph['flow_lps'].sum() * 60 / 1000
                    st.metric("Est. Volume", f"{total_vol:.1f} m³")
            else:
                st.info(
                    f"📊 No data for {graph_start.strftime('%Y-%m-%d %H:%M')} "
                    f"→ {graph_end.strftime('%Y-%m-%d %H:%M')}"
                )

            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

            # ── Time-series tabs ───────────────────────────────────────────
            st.markdown('<p class="section-title">📈 Time Series Analysis</p>', unsafe_allow_html=True)

            _chart_layout = dict(
                hovermode="x unified",
                height=400,
                template="plotly_white",
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
                font=dict(family='Inter, -apple-system, sans-serif', color='#233047', size=12),
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef', title='Time'),
                yaxis=dict(gridcolor='#f0f4f8', linecolor='#dfe7ef'),
            )

            tab1, tab2, tab3, tab4 = st.tabs(["💧 Depth", "⚡ Velocity", "🌊 Flow", "📋 Statistics"])

            with tab1:
                fig_depth = px.line(df, x="timestamp", y="depth_mm",
                                    labels={"depth_mm": "Depth (mm)", "timestamp": "Time"},
                                    markers=True)
                fig_depth.update_traces(line=dict(color="#0f4c81", width=2.5), marker=dict(size=5))
                fig_depth.update_layout(**_chart_layout)
                fig_depth.update_yaxes(title_text="Depth (mm)")
                st.plotly_chart(fig_depth, use_container_width=True)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Mean", f"{df['depth_mm'].mean():.1f} mm")
                col_s2.metric("Max", f"{df['depth_mm'].max():.1f} mm")
                col_s3.metric("Min", f"{df['depth_mm'].min():.1f} mm")
                col_s4.metric("Std Dev", f"{df['depth_mm'].std():.1f} mm")

            with tab2:
                fig_vel = px.line(df, x="timestamp", y="velocity_mps",
                                  labels={"velocity_mps": "Velocity (m/s)", "timestamp": "Time"},
                                  markers=True)
                fig_vel.update_traces(line=dict(color="#047c3d", width=2.5), marker=dict(size=5))
                fig_vel.update_layout(**_chart_layout)
                fig_vel.update_yaxes(title_text="Velocity (m/s)")
                st.plotly_chart(fig_vel, use_container_width=True)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Mean", f"{df['velocity_mps'].mean():.3f} m/s")
                col_s2.metric("Max", f"{df['velocity_mps'].max():.3f} m/s")
                col_s3.metric("Min", f"{df['velocity_mps'].min():.3f} m/s")
                col_s4.metric("Std Dev", f"{df['velocity_mps'].std():.3f} m/s")

            with tab3:
                fig_flow = px.line(df, x="timestamp", y="flow_lps",
                                   labels={"flow_lps": "Flow (L/s)", "timestamp": "Time"},
                                   markers=True)
                fig_flow.update_traces(line=dict(color="#b45309", width=2.5), marker=dict(size=5))
                fig_flow.update_layout(**_chart_layout)
                fig_flow.update_yaxes(title_text="Flow Rate (L/s)")
                st.plotly_chart(fig_flow, use_container_width=True)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Mean", f"{df['flow_lps'].mean():.1f} L/s")
                col_s2.metric("Max", f"{df['flow_lps'].max():.1f} L/s")
                col_s3.metric("Min", f"{df['flow_lps'].min():.1f} L/s")
                col_s4.metric("Std Dev", f"{df['flow_lps'].std():.1f} L/s")

            with tab4:
                st.markdown("#### Aggregate Statistics")
                col_sum1, col_sum2, col_sum3 = st.columns(3)
                with col_sum1:
                    st.markdown("**💧 Water Depth**")
                    st.metric("Mean", f"{df['depth_mm'].mean():.1f} mm")
                    st.metric("Median", f"{df['depth_mm'].median():.1f} mm")
                    st.metric("Range", f"{df['depth_mm'].max() - df['depth_mm'].min():.1f} mm")
                with col_sum2:
                    st.markdown("**⚡ Flow Velocity**")
                    st.metric("Mean", f"{df['velocity_mps'].mean():.3f} m/s")
                    st.metric("Median", f"{df['velocity_mps'].median():.3f} m/s")
                    st.metric("Range", f"{df['velocity_mps'].max() - df['velocity_mps'].min():.3f} m/s")
                with col_sum3:
                    st.markdown("**🌊 Flow Rate**")
                    st.metric("Mean", f"{df['flow_lps'].mean():.1f} L/s")
                    st.metric("Median", f"{df['flow_lps'].median():.1f} L/s")
                    st.metric("Range", f"{df['flow_lps'].max() - df['flow_lps'].min():.1f} L/s")

                st.markdown("---")
                st.markdown("#### Distribution")
                dist_col1, dist_col2 = st.columns(2)
                with dist_col1:
                    fig_hist_d = px.histogram(df, x="depth_mm", nbins=20,
                                              labels={"depth_mm": "Depth (mm)"})
                    fig_hist_d.update_traces(marker_color="#0f4c81")
                    fig_hist_d.update_layout(
                        height=280, template="plotly_white", paper_bgcolor="#ffffff",
                        plot_bgcolor="#ffffff", margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(family='Inter, sans-serif', size=11),
                        xaxis=dict(gridcolor='#f0f4f8'), yaxis=dict(gridcolor='#f0f4f8')
                    )
                    st.plotly_chart(fig_hist_d, use_container_width=True)
                with dist_col2:
                    fig_hist_f = px.histogram(df, x="flow_lps", nbins=20,
                                              labels={"flow_lps": "Flow (L/s)"})
                    fig_hist_f.update_traces(marker_color="#b45309")
                    fig_hist_f.update_layout(
                        height=280, template="plotly_white", paper_bgcolor="#ffffff",
                        plot_bgcolor="#ffffff", margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(family='Inter, sans-serif', size=11),
                        xaxis=dict(gridcolor='#f0f4f8'), yaxis=dict(gridcolor='#f0f4f8')
                    )
                    st.plotly_chart(fig_hist_f, use_container_width=True)

                st.markdown("---")
                st.markdown("#### Collection Summary")
                col_c1, col_c2, col_c3, col_c4 = st.columns(4)
                col_c1.metric("Total Records", len(df))
                time_span_h = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600
                col_c2.metric("Time Span", f"{time_span_h:.1f} h")
                col_c3.metric("Rate", f"{len(df) / max(1, time_span_h):.1f}/hr")
                completeness = (len(df) - df[['depth_mm', 'velocity_mps', 'flow_lps']].isna().sum().max()) / max(1, len(df)) * 100
                col_c4.metric("Completeness", f"{completeness:.0f}%")

            # ── Data table & export ────────────────────────────────────────
            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
            st.markdown('<p class="section-title">📋 Data Table & Export</p>', unsafe_allow_html=True)
            display_df = df[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
            display_df.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
            display_df["Timestamp"] = display_df["Timestamp"].astype(str)
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            col_dl1, col_dl2, _ = st.columns([1, 1, 2])
            with col_dl1:
                st.download_button(
                    "⬇ Download CSV",
                    data=display_df.to_csv(index=False),
                    file_name=f"flow_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_dl2:
                st.download_button(
                    "⬇ Download JSON",
                    data=df.to_json(orient="records", date_format="iso"),
                    file_name=f"flow_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.markdown("""
            <div style="background: #ffffff; border: 1px solid #dfe7ef; border-radius: 18px; padding: 40px; text-align: center; margin: 2rem 0;">
                <p style="font-size: 2.5rem; margin: 0 0 1rem;">📡</p>
                <h3 style="color: #233047; margin: 0 0 0.5rem;">No data in selected window</h3>
                <p style="color: #6b7280; margin: 0;">Try a wider time window, or start the <code>monitor.py</code> service to collect data.</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: #ffffff; border: 1px solid #dfe7ef; border-radius: 18px; padding: 40px; text-align: center; margin: 2rem 0;">
            <p style="font-size: 2.5rem; margin: 0 0 1rem;">📡</p>
            <h3 style="color: #233047; margin: 0 0 0.5rem;">Awaiting first reading</h3>
            <p style="color: #6b7280; margin: 0 0 1.5rem;">No measurements have been stored yet.</p>
            <p style="color: #6b7280; font-size: 0.9rem;">Run <code>python monitor.py</code> or <code>docker-compose up</code> to start collecting data automatically.</p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("👈 Select a device from the sidebar to view data.")

# ── Footer ──────────────────────────────────────────────────────────────────
now_footer = datetime.now(pytz.timezone(DEFAULT_TZ))
st.markdown(f"""
<div class="app-footer">
    <span class="app-footer-brand">e-flow™ by EDS</span>
    <span class="app-footer-meta">
        🕐 {now_footer.strftime('%Y-%m-%d %H:%M %Z')} &nbsp;·&nbsp;
        Timezone: {DEFAULT_TZ} &nbsp;·&nbsp;
        Monitor service: {'enabled' if MONITOR_ENABLED else 'disabled'}
    </span>
</div>
""", unsafe_allow_html=True)
