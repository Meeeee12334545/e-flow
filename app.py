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

# Professional styling with Helvetica Neue
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * {
        font-family: 'Helvetica Neue', 'Helvetica Neue Light', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    /* Main text styling */
    body, p, span, div {
        font-family: 'Helvetica Neue Light', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        font-weight: 300;
        letter-spacing: 0.3px;
        line-height: 1.6;
        color: #333;
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Helvetica Neue Light', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        font-weight: 300;
        letter-spacing: 0.3px;
        margin-top: 0.8rem;
        margin-bottom: 1rem;
        color: #002f6c;
    }
    
    h1 {
        font-size: 2.8rem;
        font-weight: 300;
        color: #002f6c;
        letter-spacing: 0px;
        margin-bottom: 1.2rem;
    }
    
    h2 {
        font-size: 2rem;
        font-weight: 300;
        color: #1a1a1a;
        margin-top: 1.5rem;
        margin-bottom: 1.2rem;
        letter-spacing: 0.3px;
    }
    
    h3 {
        font-size: 1.4rem;
        font-weight: 300;
        color: #2a2a2a;
        letter-spacing: 0.3px;
        margin-bottom: 0.8rem;
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #f8fbff 0%, #ffffff 100%);
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #ced8e9;
        border-left: 4px solid #002f6c;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        box-shadow: 0 8px 16px rgba(0, 102, 204, 0.12);
        border-left-color: #0052a3;
        transform: translateY(-2px);
    }
    
    .metric-card h4 {
        font-family: 'Helvetica Neue Light', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        font-weight: 300;
        font-size: 0.9rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin: 0 0 0.5rem 0;
    }
    
    /* Status indicators */
    .status-active { 
        color: #10b981; 
        font-weight: 500;
        font-size: 1.1rem;
        letter-spacing: 0.5px;
    }
    .status-idle { 
        color: #f59e0b; 
        font-weight: 500;
        font-size: 1.1rem;
    }
    .status-error { 
        color: #ef4444; 
        font-weight: 500;
        font-size: 1.1rem;
    }
    
    /* Dividers */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(to right, #e0e0e0 0%, transparent);
        margin: 2rem 0;
    }
    
    /* Input styling */
    .stSelectbox, .stSlider, .stNumberInput, .stTextInput {
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
    }
    
    section[data-testid="stSidebar"] h2 {
        font-weight: 500;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        color: #1a1a1a;
        letter-spacing: 0.3px;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] button {
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        font-weight: 500;
        font-size: 0.95rem;
        letter-spacing: 0.3px;
    }
    
    /* Expander styling */
    details > summary {
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        font-weight: 500;
        cursor: pointer;
    }
    
    /* Caption styling */
    .caption {
        font-family: 'Helvetica Neue Light', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        font-weight: 300;
        font-size: 0.9rem;
        color: #666;
        letter-spacing: 0.2px;
    }
    
    /* Button styling */
    button[kind="primary"] {
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif !important;
        font-weight: 500;
        letter-spacing: 0.4px;
        border-radius: 8px;
        background: linear-gradient(135deg, #0066cc 0%, #0052a3 100%) !important;
        color: white !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.3s ease;
        box-shadow: 0 2px 8px rgba(0, 102, 204, 0.2);
    }
    
    button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(0, 102, 204, 0.4) !important;
        transform: translateY(-1px);
    }
    
    /* Secondary buttons */
    button[kind="secondary"] {
        font-family: 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif !important;
        font-weight: 400;
        letter-spacing: 0.3px;
        border-radius: 8px;
        border: 1px solid #ddd !important;
    }
    
    /* Info/Warning boxes */
    .stAlert {
        font-family: 'Helvetica Neue Light', 'Helvetica Neue', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Inter', sans-serif;
        border-radius: 8px;
        padding: 1rem;
        font-weight: 300;
    }
    
    /* Code blocks */
    code {
        font-family: 'Monaco', 'Courier New', monospace;
        font-size: 0.9rem;
        background-color: #f5f5f5;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
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


# Page header
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    <h1 style="margin-bottom: 0; font-weight: 700; letter-spacing: -0.5px; font-size: 3rem; color: #002f6c;">
        e-flow by EDS
    </h1>
    <p style="margin-top: 0.2rem; color: #444; font-size: 1.1rem; font-weight: 400; letter-spacing: 0.5px;">
        Sewer Flow Monitoring | Depth • Velocity • Flow
        <br><small style="color:#666;">www.e-d-s.com.au</small>
    </p>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div style="text-align: right; padding-top: 0.5rem;">
        <span class="status-active" style="font-size: 1.2rem;">●</span>
        <span style="color: #10b981; font-weight: 500; margin-left: 0.5rem;">LIVE</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")


# Sidebar configuration
with st.sidebar:
    # Add authentication header
    render_auth_header()

    st.markdown("""
    <h2 style="font-weight: 500; letter-spacing: 0.3px;">EDS Experience Mode</h2>
    """, unsafe_allow_html=True)

    page_mode = st.selectbox(
        "Interface Mode",
        options=["Simplified View", "Full Dashboard", "EDS Product Overview"],
        index=0,
        help="Simplified View for standard users, Full Dashboard for power users, EDS Product Overview for sales demos."
    )
    st.session_state['page_mode'] = page_mode

    st.markdown("""
    <h2 style="font-weight: 500; letter-spacing: 0.3px;">Configuration & Status</h2>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background: #f0f7ff; border-left: 3px solid #002f6c; padding: 12px; border-radius: 6px; margin-bottom: 1.5rem;">
        <p style="font-size: 0.9rem; margin: 0; color: #1a1a1a; line-height: 1.6;">
            <strong style="font-weight: 500;">Device Status:</strong> Connected & streaming<br>
            <span style="color: #666; font-size: 0.85rem;">• Update interval: 60 seconds</span><br>
            <span style="color: #666; font-size: 0.85rem;">• Protocol: Direct device telemetry</span><br>
            <span style="color: #666; font-size: 0.85rem;">• Storage: Local data repository</span>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Monitor status (app is read-only; collection handled by monitor service)
    if MONITOR_ENABLED:
        st.success("✔ Auto-collect: Enabled (monitor service). Dashboard is read-only.")
    else:
        st.info("ℹ️ Auto-collect: Disabled here. Start the monitor service to collect data.")
    
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
                    ⚠️ Display only - Not stored in database
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Optional: allow one-click store from Streamlit (for Cloud testing)
            allow_streamlit_writes = os.getenv("ALLOW_STREAMLIT_WRITES", "").lower() in ("1", "true", "yes")
            if allow_streamlit_writes and has_data:
                col_store, _ = st.columns([1,3])
                with col_store:
                    if st.button("Store This Reading (admin)", key="store_now_button"):
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
    else:
        st.error("⚠️ No devices configured")
        st.info("Expected devices: " + ", ".join(DEVICES.keys()))
        selected_device_id = None
    
    st.divider()

    # Time range selection

    st.markdown("""
    <p style="font-weight: 500; font-size: 0.95rem; margin-bottom: 0.75rem; letter-spacing: 0.2px;">
        Query Parameters
    </p>
    """, unsafe_allow_html=True)
    # Enhanced time window selection with 24h default and days/months options
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
    default_index = 0  # 24 hours
    time_range = st.selectbox(
        "Time Window",
        options=time_options,
        format_func=lambda x: x[1],
        index=default_index,
        key="time_range",
        label_visibility="collapsed"
    )[0]
    
    st.divider()
    
    # Database stats
    st.markdown("""
    <p style="font-weight: 500; font-size: 0.95rem; margin-bottom: 1rem; letter-spacing: 0.2px;">
        System Metrics
    </p>
    """, unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Stations", db.get_device_count(), help="Number of connected field devices")
    with col2:
        total_measurements = db.get_measurement_count()
        st.metric("Data Points", total_measurements, help="Total measurements recorded")
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
            st.caption(f"Last ingest: {local_ts.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception:
            st.caption(f"Last ingest: {latest_rows[0]['timestamp']}")
    
    # Debug info for troubleshooting
    if total_measurements == 0:
        st.warning("⚠️ No measurements found yet.")
        st.info("If this is a fresh deploy, the monitor service will populate data shortly. You can also click 'Show Real-Time Data' for a live view without storing.")
    
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
            latest = df.iloc[-1]

            st.metric('Latest Depth', f"{latest['depth_mm']:.1f} mm" if pd.notna(latest['depth_mm']) else 'N/A')
            st.metric('Latest Velocity', f"{latest['velocity_mps']:.3f} m/s" if pd.notna(latest['velocity_mps']) else 'N/A')
            st.metric('Latest Flow', f"{latest['flow_lps']:.1f} L/s" if pd.notna(latest['flow_lps']) else 'N/A')

            st.subheader('Time Series (last 24h)')
            cutoff = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=24)
            df24 = df[df['timestamp'] >= cutoff]
            if not df24.empty:
                chart = px.line(df24, x='timestamp', y=['depth_mm', 'velocity_mps', 'flow_lps'], markers=True)
                chart.update_layout(legend_title_text='Metric')
                st.plotly_chart(chart, use_container_width=True)
            else:
                st.info('No data for last 24 hours.')

            csv_data = df.to_csv(index=False)
            json_data = df.to_json(orient='records', date_format='iso')
            st.download_button('Download CSV', data=csv_data, file_name=f'{selected_device_id}_data.csv', mime='text/csv')
            st.download_button('Download JSON', data=json_data, file_name=f'{selected_device_id}_data.json', mime='application/json')
        else:
            st.warning('No measurements available yet. Run the monitor service or store readings from real-time view.')
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
            # Latest values with enhanced metrics
            st.markdown(f"""
            <h2 style="font-weight: 500; letter-spacing: 0.3px; margin-bottom: 1.5rem;">
                Current Status: {selected_device_name}
            </h2>
            """, unsafe_allow_html=True)
            
            latest = df.iloc[-1]
            last_update = latest["timestamp"]
            
            # KPI Metrics
            metric_cols = st.columns(3, gap="medium")
            
            with metric_cols[0]:
                depth = latest["depth_mm"]
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%); 
                            padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0;
                            text-align: center; min-height: 120px; display: flex; flex-direction: column; justify-content: center;">
                    <p style="color: #666; font-size: 0.9rem; font-weight: 300; margin: 0 0 0.5rem 0; letter-spacing: 0.5px;">
                        WATER DEPTH
                    </p>
                    <p style="font-size: 2rem; font-weight: 400; margin: 0; color: #0066cc;">
                        {f'{depth:.1f}' if depth is not None else 'N/A'} <span style="font-size: 1rem;">mm</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with metric_cols[1]:
                velocity = latest["velocity_mps"]
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%); 
                            padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0;
                            text-align: center; min-height: 120px; display: flex; flex-direction: column; justify-content: center;">
                    <p style="color: #666; font-size: 0.9rem; font-weight: 300; margin: 0 0 0.5rem 0; letter-spacing: 0.5px;">
                        FLOW VELOCITY
                    </p>
                    <p style="font-size: 2rem; font-weight: 400; margin: 0; color: #0066cc;">
                        {f'{velocity:.3f}' if velocity is not None else 'N/A'} <span style="font-size: 1rem;">m/s</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            with metric_cols[2]:
                flow = latest["flow_lps"]
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%); 
                            padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0;
                            text-align: center; min-height: 120px; display: flex; flex-direction: column; justify-content: center;">
                    <p style="color: #666; font-size: 0.9rem; font-weight: 300; margin: 0 0 0.5rem 0; letter-spacing: 0.5px;">
                        FLOW RATE
                    </p>
                    <p style="font-size: 2rem; font-weight: 400; margin: 0; color: #0066cc;">
                        {f'{flow:.1f}' if flow is not None else 'N/A'} <span style="font-size: 1rem;">L/s</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Flow Graph Section - Prominent display with date range selection
            st.markdown("""
            <h2 style="font-weight: 500; letter-spacing: 0.3px; margin-top: 1.5rem; margin-bottom: 1rem;">
                📊 Flow Rate Analysis
            </h2>
            """, unsafe_allow_html=True)
            
            # Date range selector
            col_range1, col_range2 = st.columns([1, 2])
            
            with col_range1:
                range_mode = st.radio(
                    "Date Range Mode",
                    options=["Quick Select", "Custom Range"],
                    index=0,
                    horizontal=True
                )
            
            # Initialize default date range (24 hours)
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
            
            # Data quality indicators with enhanced styling
            st.markdown("""
            <div style="margin-top: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;">
            """, unsafe_allow_html=True)

            # CSV Export
            st.markdown("""
            <p style="font-weight: 300; font-size: 0.9rem; margin-bottom: 0.75rem; letter-spacing: 0.2px;">
                Export Data
            </p>
            """, unsafe_allow_html=True)
            export_csv = st.button("📥 Download CSV", type="secondary", use_container_width=True)
            
            if export_csv:
                st.download_button(
                    label="💾 Click to download CSV",
                    data=df.to_csv(index=False),
                    file_name=f"data_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.markdown(f"""
                <p style="font-family: 'Helvetica Neue Light', 'Helvetica Neue', sans-serif; font-size: 0.85rem; color: #666; margin: 0; letter-spacing: 0.2px;">
                    <strong style="color: #333;">🕒 Last Update</strong><br>
                    {last_update.strftime('%Y-%m-%d %H:%M:%S')}
                </p>
                """, unsafe_allow_html=True)
            with col_info2:
                st.markdown(f"""
                <p style="font-family: 'Helvetica Neue Light', 'Helvetica Neue', sans-serif; font-size: 0.85rem; color: #666; margin: 0; letter-spacing: 0.2px;">
                    <strong style="color: #333;">📊 Data Points</strong><br>
                    {len(df)} in {time_range}h window
                </p>
                """, unsafe_allow_html=True)
            with col_info3:
                st.markdown(f"""
                <p style="font-family: 'Helvetica Neue Light', 'Helvetica Neue', sans-serif; font-size: 0.85rem; color: #666; margin: 0; letter-spacing: 0.2px;">
                    <strong style="color: #333;">⏱️ Collection Rate</strong><br>
                    {len(df)/(time_range if time_range > 0 else 1):.1f} pts/hr
                </p>
                """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Advanced analytics
            st.markdown("""
            <h3 style="font-weight: 500; letter-spacing: 0.3px; margin-top: 2rem; margin-bottom: 1rem;">
                Time Series Analysis
            </h3>
            """, unsafe_allow_html=True)
            
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
            st.markdown("""
            <h3 style="font-weight: 500; letter-spacing: 0.3px; margin-top: 2rem; margin-bottom: 1rem;">
                📋 Data Table
            </h3>
            """, unsafe_allow_html=True)
            display_df = df[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
            display_df.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
            display_df["Timestamp"] = display_df["Timestamp"].astype(str)
            st.dataframe(display_df, width="stretch", hide_index=True)
            
            # Export functionality
            st.markdown("""
            <h3 style="font-weight: 500; letter-spacing: 0.3px; margin-top: 2rem; margin-bottom: 1rem;">
                📥 Export Data
            </h3>
            """, unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            
            with col1:
                csv = display_df.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name=f"flow_data_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col2:
                json_str = df.to_json(orient="records", date_format="iso")
                st.download_button(
                    label="Download as JSON",
                    data=json_str,
                    file_name=f"flow_data_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        else:
            st.info("No data available for the selected time range.")
            
            # Show Flow Graph section even without data
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("""
            <h2 style="font-weight: 500; letter-spacing: 0.3px; margin-top: 1.5rem; margin-bottom: 1rem;">
                📊 Flow Rate Analysis
            </h2>
            """, unsafe_allow_html=True)
            
            st.warning("""
            ⚠️ **No data available to display graph**
            
            The flow graph will appear here once data is being collected. Current status:
            - ✅ Device is reachable (see "Show Real-Time Data" in sidebar)
            - ❌ No data points stored in database yet
            
            **To start seeing data:**
            1. Ensure the monitor service is running (separate container/process)
            2. OR enable `ALLOW_STREAMLIT_WRITES=true` in environment variables, then use "Store This Reading" button in sidebar
            3. Wait for automatic collection (every 60 seconds when values change)
            """)
    else:
        st.warning("📊 **No measurements found in database**")
        
        st.markdown("""
        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; border-left: 4px solid #ffc107; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #856404;">🔧 Quick Start Guide</h3>
        
        <p><strong>Your device is online!</strong> Click "Show Real-Time Data" in the sidebar to verify connectivity.</p>
        
        <p><strong>To start seeing historical data and graphs:</strong></p>
        
        <p><strong>Option 1: Run the Monitor Service</strong> (Recommended for production)</p>
        <ul>
            <li>Start the monitor service: <code>python monitor.py</code></li>
            <li>Or use Docker: <code>docker-compose up -d</code></li>
            <li>Data will be collected automatically every 60 seconds</li>
        </ul>
        
        <p><strong>Option 2: Manual Data Storage</strong> (Quick testing)</p>
        <ul>
            <li>Set environment variable: <code>ALLOW_STREAMLIT_WRITES=true</code></li>
            <li>Restart the app</li>
            <li>Click "Show Real-Time Data" then "Store This Reading" in the sidebar</li>
            <li>Repeat a few times to build up data points</li>
        </ul>
        
        <p style="margin-bottom: 0;"><strong>Once data is stored:</strong> The flow graph and analytics will appear automatically!</p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("👈 Select a device from the sidebar to view data.")

# Footer
st.markdown("---")
st.markdown(
    f"<small>Last update: {datetime.now(pytz.timezone(DEFAULT_TZ)).strftime('%Y-%m-%d %H:%M:%S %Z')} | "
    f"Timezone: {DEFAULT_TZ}</small>",
    unsafe_allow_html=True
)
