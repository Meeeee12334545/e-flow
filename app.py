import asyncio
import base64
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
from config import DEVICES, MONITOR_URL, MONITOR_ENABLED, DEFAULT_SELECTORS
from shared_styles import apply_styles
from rainfall import get_rainfall_for_device
from rainfall_analysis import (
    compute_dry_weather_baseline,
    detect_rain_events,
    detect_inflow_infiltration,
)

from streamlit_auth import init_auth_state, is_authenticated, is_admin, login_page, render_auth_header, filter_devices_for_user, get_org_logo_data_uri, get_sidebar_logo_path

# set_page_config MUST be the first Streamlit command in the script
st.set_page_config(
    page_title="e-flow | Hydrological Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

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


@st.cache_resource
def start_background_monitor():
    """Start monitor.py as a background subprocess if it is not already running.

    Uses monitor.py's own SingletonProcessLock so a second instance launched
    externally (e.g. via docker-compose or start.sh) is simply ignored here.
    Returns the Popen object (or None on failure).
    """
    import atexit
    try:
        monitor_script = Path(__file__).parent / "monitor.py"
        if not monitor_script.exists():
            return None
        env = os.environ.copy()
        env.setdefault("MONITOR_ENABLED", "true")
        env.setdefault("MONITOR_INTERVAL", "60")
        env.setdefault("SCRAPER_FORCE_REQUESTS", "1")
        env.setdefault("STORE_ALL_READINGS", "false")
        # Keep EXIT_ON_UNHEALTHY=false here: without a process manager to
        # restart the subprocess on failure, letting it call sys.exit(1) would
        # permanently kill background collection.  supervisord.conf sets this
        # to true because supervisord will automatically restart the process.
        env.setdefault("EXIT_ON_UNHEALTHY", "false")
        # Redirect stderr to monitor.log (append mode) so crash tracebacks are
        # captured without the pipe-buffer deadlock that stderr=PIPE can cause.
        # monitor.py already has a RotatingFileHandler on monitor.log, so all
        # structured log output goes there via the logging framework regardless.
        log_path = monitor_script.parent / "monitor.log"
        # Use a 'with' block so the parent's file handle is always closed even
        # if Popen() raises; the subprocess inherits the fd before we close.
        with open(log_path, "ab") as log_fp:
            proc = subprocess.Popen(
                [sys.executable, str(monitor_script)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=log_fp,
            )
        # Ensure the monitor subprocess is terminated when Streamlit exits
        atexit.register(lambda: proc.terminate())
        return proc
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Could not start background monitor: %s", e, exc_info=True
        )
        return None


# Launch background monitor so data is collected automatically even when
# running Streamlit alone (without a separate monitor.py process).
# monitor.py's SingletonProcessLock prevents a second instance if one is
# already running externally.
_monitor_proc = start_background_monitor()

# Setup logging before anything else
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Apply shared professional design system (Inter font, blue palette, component overrides)
apply_styles()

# EDS brand logo in the sidebar header (wide) and collapsed icon
_ASSETS = Path(__file__).parent / "assets"
st.logo(
    get_sidebar_logo_path(),
    icon_image=str(_ASSETS / "logo_icon.svg"),
)


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
            location=device_info.get("location", ""),
            dashboard_url=device_info.get("url", ""),
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


@st.cache_data(ttl=60)
def get_cached_measurements(device_id: str = None, limit: int = 1000):
    """Return measurements from the DB, cached for 60 seconds per device/limit."""
    return db.get_measurements(device_id=device_id, limit=limit)


@st.cache_data(ttl=30)
def get_cached_device_count() -> int:
    """Return device count cached for 30 seconds."""
    return db.get_device_count()


@st.cache_data(ttl=30)
def get_cached_measurement_count() -> int:
    """Return total measurement count cached for 30 seconds."""
    return db.get_measurement_count()


@st.cache_data(ttl=3600)
def get_cached_rainfall(device_id: str, date_from_iso: str, date_to_iso: str):
    """Fetch & cache rainfall data for *device_id* over the requested period (1-hr TTL)."""
    from datetime import datetime as _dt
    df = get_rainfall_for_device(
        device_id,
        db,
        _dt.fromisoformat(date_from_iso),
        _dt.fromisoformat(date_to_iso),
    )
    # Return as JSON-serialisable list so Streamlit can cache it
    if df.empty:
        return []
    df["timestamp"] = df["timestamp"].astype(str)
    return df.to_dict("records")


def get_collection_stats(device_id):
    """Calculate data collection statistics."""
    measurements = get_cached_measurements(device_id, limit=2000)
    if not measurements:
        return {}

    df = pd.DataFrame(measurements)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp'])
    if df.empty:
        return {}

    span_secs = (df['timestamp'].max() - df['timestamp'].min()).total_seconds()
    return {
        'total_points': len(df),
        'time_span': span_secs / 3600,
        'collection_rate': len(df) / max(1, span_secs / 60),
    }


def fetch_latest_reading(device_id: str):
    """
    Fetch and return the latest real-time reading as fast as possible.
    The reading is returned for display; persistence is handled by the monitor service.

    Returns: (success: bool, message: str, timestamp: datetime, payload: dict)
    """
    device_config = DEVICES.get(device_id)
    if not device_config:
        # Device was added via admin panel — look up its URL from the database
        all_devices = db.get_devices()
        db_device = next((d for d in all_devices if d["device_id"] == device_id), None)
        if db_device and db_device.get("dashboard_url"):
            device_config = {
                "url": db_device["dashboard_url"],
                "selectors": DEFAULT_SELECTORS,
            }
        else:
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


# Page header — use custom org logo if set, otherwise fall back to EDS logo
_org_logo_uri = get_org_logo_data_uri()
if _org_logo_uri:
    # Custom org logo — render on white/transparent background (no brightness invert)
    _hero_logo_src = _org_logo_uri
    _hero_logo_style = "max-height:52px; max-width:220px; margin-bottom: 0.8rem; display:block; object-fit: contain;"
    _hero_logo_filter = ""
else:
    _logo_wide_b64 = base64.b64encode((_ASSETS / "logo_wide.svg").read_bytes()).decode()
    _hero_logo_src = f"data:image/svg+xml;base64,{_logo_wide_b64}"
    _hero_logo_style = "height:52px; margin-bottom: 0.8rem; display:block;"
    _hero_logo_filter = "filter: brightness(0) invert(1);"

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown(f"""
    <div class="hero-card">
        <img src="{_hero_logo_src}"
             alt="Organisation Logo"
             style="{_hero_logo_style} {_hero_logo_filter}"/>
        <p class="hero-subtitle">Real-time sewer flow monitoring &nbsp;·&nbsp; Precision depth, velocity &amp; flow measurement &nbsp;·&nbsp; Advanced data analytics &amp; export</p>
        <div style="display:flex; flex-wrap: wrap; gap: 8px;">
            <span class="hero-badge" style="background: rgba(255,255,255,0.15); color: #ffffff; border: 1px solid rgba(255,255,255,0.28);">Live Data</span>
            <span class="hero-badge" style="background: rgba(255,255,255,0.15); color: #ffffff; border: 1px solid rgba(255,255,255,0.28);">Historical Analytics</span>
            <span class="hero-badge" style="background: rgba(255,255,255,0.15); color: #ffffff; border: 1px solid rgba(255,255,255,0.28);">Operational Insights</span>
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
        options=["Simplified View", "Full Dashboard"],
        index=0,
        help="Simplified View for standard users, Full Dashboard for power users."
    )
    st.session_state['page_mode'] = page_mode

    st.markdown("## Device")

    st.markdown("""
    <div style="background: #E8F3EE; border-left: 3px solid #3A7F5F; padding: 10px 12px; border-radius: 6px; margin-bottom: 1rem;">
        <p style="font-size: 0.82rem; margin: 0; color: #4A4A4A; line-height: 1.6;">
            <strong>Status:</strong> Connected &amp; streaming<br>
            <span style="color: #6b7280;">• Interval: 60 s &nbsp;• WAL persistence: on</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Monitor status
    if _monitor_proc is not None:
        st.success("Monitor service: running (auto-collecting data)")
    elif MONITOR_ENABLED:
        st.success("Monitor service: active")
    else:
        st.info("Monitor service: not running. Start monitor.py to collect data.")

    # Build device mapping from database
    devices = db.get_devices()
    
    # Filter devices based on user's access rights
    devices = filter_devices_for_user(devices)
    
    device_names = {d['device_name']: d['device_id'] for d in devices}
    
    if not device_names:
        st.warning("No devices assigned to your account")
        if is_admin():
            st.info("As an admin, go to the Admin Panel to manage device assignments")
        st.stop()
    
    selected_device_name: str = st.selectbox(
        "Select Device",
        options=sorted(device_names.keys()),
        key="device_selector",
    )
    selected_device_id = device_names[selected_device_name]
    
    # Get selected device info
    device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)
    if device_info:
        with st.expander("Station Details", expanded=False):
            _lat = device_info.get("latitude")
            _lon = device_info.get("longitude")
            _loc_str = f"{_lat:.4f}, {_lon:.4f}" if (_lat and _lon) else "Not set"
            st.markdown(f"""
            <div style="line-height: 1.7; word-break: break-word; overflow-wrap: break-word;">
                <p style="margin: 0 0 0.5rem 0;"><strong>Station ID</strong><br>
                    <code style="display: block; word-break: break-word; overflow-wrap: break-word; white-space: pre-wrap;">{device_info['device_id']}</code></p>
                <p style="margin: 0 0 0.5rem 0;"><strong>Location</strong><br>
                    <span>{device_info['location'] or 'Not specified'}</span></p>
                <p style="margin: 0 0 0.5rem 0;"><strong>Coordinates</strong><br>
                    <span>{_loc_str}</span></p>
                <p style="margin: 0;"><strong>Initialized</strong><br>
                    <code style="display: block; word-break: break-word; overflow-wrap: break-word; white-space: pre-wrap;">{device_info['created_at']}</code></p>
            </div>
            """, unsafe_allow_html=True)

        # Rain gauge info
        _rain_assignment = db.get_device_rainfall_station(selected_device_id)
        if _rain_assignment:
            _st_name = _rain_assignment.get("station_name") or _rain_assignment["station_id"]
            _st_state = _rain_assignment.get("state") or ""
            with st.expander("Rain Gauge", expanded=False):
                st.markdown(
                    f"<div style='font-size:0.85rem;line-height:1.6;'>"
                    f"<strong>{_st_name}</strong><br>"
                    f"<span style='color:#6b7280;'>{_rain_assignment['station_id']}"
                    f"{' — ' + _st_state if _st_state else ''}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        elif device_info.get("latitude") and device_info.get("longitude"):
            with st.expander("Rain Gauge", expanded=False):
                st.caption("Using Open-Meteo grid data (coordinates-based). Assign a BOM station in the Admin panel for higher accuracy.")

        st.markdown("<div style='margin-top: 0.75rem;'></div>", unsafe_allow_html=True)

        # Manual refresh to pull the newest reading into the app (fast API path)
        refresh_clicked = st.button("Get Latest Data", type="primary", key="refresh_button", width="stretch")
        
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
                # Auto-save the reading to the database
                try:
                    writer = DataScraper(db)
                    stored = writer.store_measurement(
                        device_id=selected_device_id,
                        device_name=selected_device_name,
                        depth_mm=payload.get("depth_mm"),
                        velocity_mps=payload.get("velocity_mps"),
                        flow_lps=payload.get("flow_lps"),
                        allow_storage=True
                    )
                    if stored:
                        get_cached_measurements.clear()
                        get_cached_measurement_count.clear()
                        st.success(f"✅ Reading fetched and saved to database at {ts_str}")
                    else:
                        st.info(f"✓ Reading fetched at {ts_str} (no change from last stored value)")
                except Exception as e:
                    st.warning(f"⚠️ Reading fetched at {ts_str} but could not save: {e}")
            else:
                st.error(message)
        
        # Display real-time data if available
        if 'realtime_data' in st.session_state:
            rtd = st.session_state['realtime_data']
            depth = rtd.get('depth_mm')
            velocity = rtd.get('velocity_mps')
            flow = rtd.get('flow_lps')
            ts = rtd.get('timestamp')

            has_data = depth is not None or velocity is not None or flow is not None
            bg_color = "linear-gradient(135deg, #e8f5e9 0%, #ffffff 100%)" if has_data else "linear-gradient(135deg, #ffebee 0%, #ffffff 100%)"
            border_color = "#4caf50" if has_data else "#f44336"
            text_color = "#2e7d32" if has_data else "#c62828"
            status_dot_color = "#4caf50" if has_data else "#f44336"

            st.markdown(f"""
            <div style="background: {bg_color};
                        padding: 14px; border-radius: 10px; border: 2px solid {border_color};
                        margin-top: 0.75rem; margin-bottom: 0.75rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 0.82rem; color: {text_color}; font-weight: 600; display:inline-flex; align-items:center; gap:5px;">
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{status_dot_color};flex-shrink:0;"></span>
                        LIVE DATA
                    </span>
                    <span style="font-size: 0.72rem; color: #666;">{ts.strftime('%H:%M:%S') if ts else 'N/A'}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; text-align: center;">
                    <div>
                        <div style="font-size: 0.7rem; color: #666; margin-bottom: 2px;">Depth</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: {text_color}; line-height: 1.2;">{f'{depth:.1f}' if depth is not None else 'N/A'}</div>
                        <div style="font-size: 0.65rem; color: #888;">mm</div>
                    </div>
                    <div>
                        <div style="font-size: 0.7rem; color: #666; margin-bottom: 2px;">Velocity</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: {text_color}; line-height: 1.2;">{f'{velocity:.3f}' if velocity is not None else 'N/A'}</div>
                        <div style="font-size: 0.65rem; color: #888;">m/s</div>
                    </div>
                    <div>
                        <div style="font-size: 0.7rem; color: #666; margin-bottom: 2px;">Flow</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: {text_color}; line-height: 1.2;">{f'{flow:.1f}' if flow is not None else 'N/A'}</div>
                        <div style="font-size: 0.65rem; color: #888;">L/s</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.error("No devices configured")
        st.info("Expected devices: " + ", ".join(DEVICES.keys()))
        selected_device_id = None

    total_measurements = get_cached_measurement_count()
    if total_measurements == 0:
        st.warning("No measurements yet.")
        if _monitor_proc is not None:
            st.info("⏳ Background monitor is running — first reading will arrive within 60 seconds. You can also click **Get Latest Data** above to fetch and save a reading right now.")
        else:
            st.info("Click **Get Latest Data** to fetch and save a live reading, or start monitor.py to collect data automatically.")

# Main content area
page_mode = st.session_state.get('page_mode', 'Simplified View')

if page_mode == 'Simplified View':
    if selected_device_id:
        measurements = get_cached_measurements(device_id=selected_device_id)
        if measurements:
            df = pd.DataFrame(measurements)
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])
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
                <div class="metric-card depth">
                    <p class="metric-label">Water Depth</p>
                    <p class="metric-value">{latest_depth}<span class="metric-unit">mm</span></p>
                </div>
                <div class="metric-card velocity">
                    <p class="metric-label">Flow Velocity</p>
                    <p class="metric-value green">{latest_velocity}<span class="metric-unit">m/s</span></p>
                </div>
                <div class="metric-card flow">
                    <p class="metric-label">Flow Rate</p>
                    <p class="metric-value amber">{latest_flow}<span class="metric-unit">L/s</span></p>
                </div>
            </div>
            <p style="font-size: 0.82rem; color: #6b7280; margin: -0.75rem 0 1.5rem 4px;">
                Last reading: {last_ts_str} &nbsp;·&nbsp; {len(df)} total records in database
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
                <h2 style="margin: 0; font-weight: 700; letter-spacing: -0.02em; color: #4A4A4A;">Performance trend</h2>
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
                    line=dict(color='#1D4E89', width=2.5),
                    marker=dict(size=5),
                    fill='tozeroy',
                    fillcolor='rgba(29, 78, 137, 0.07)',
                ),
                secondary_y=False
            )
            fig.add_trace(
                go.Scatter(
                    x=df_window['timestamp'],
                    y=df_window['depth_mm'],
                    mode='lines+markers',
                    name='Depth (mm)',
                    line=dict(color='#3A7F5F', width=2, dash='dash'),
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
                    line=dict(color='#2A9D8F', width=2, dash='dot'),
                    marker=dict(size=5)
                ),
                secondary_y=True
            )
            fig.update_layout(
                title=dict(text=''),
                legend=dict(
                    orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                    font=dict(size=12),
                    title=dict(text=''),
                ),
                hovermode='x unified',
                margin=dict(l=0, r=0, t=40, b=0),
                template='plotly_white',
                height=440,
                paper_bgcolor='#ffffff',
                plot_bgcolor='#ffffff',
                font=dict(family='Inter, -apple-system, sans-serif', color='#4A4A4A', size=12),
                xaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9'),
                yaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9'),
            )
            # Hide any auto-generated unnamed traces (e.g. secondary-y anchors)
            fig.for_each_trace(
                lambda t: t.update(showlegend=False) if not t.name else None
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
            # Format timestamps as dd/mm/yyyy hh:mm:ss for export
            df_export = df.copy()
            if 'timestamp' in df_export.columns:
                ts_col = pd.to_datetime(df_export['timestamp'], utc=True, format="ISO8601", errors='coerce')
                df_export['timestamp'] = ts_col.dt.tz_convert(DEFAULT_TZ).dt.strftime('%d/%m/%Y %H:%M:%S')
            csv_data = df_export.to_csv(index=False)
            json_data = df.to_json(orient='records', date_format='iso')
            with col_download1:
                st.download_button('⬇ Download CSV', data=csv_data,
                                   file_name=f'{selected_device_id}_data.csv', mime='text/csv',
                                   width="stretch")
            with col_download2:
                st.download_button('⬇ Download JSON', data=json_data,
                                   file_name=f'{selected_device_id}_data.json',
                                   mime='application/json', width="stretch")
        else:
            st.markdown("""
            <div style="background: #ffffff; border: 1px solid #D9D9D9; border-radius: 12px; padding: 40px; text-align: center; margin: 2rem 0;">
                <h3 style="color: #4A4A4A; margin: 0 0 0.5rem;">Awaiting first reading</h3>
                <p style="color: #6b7280; margin: 0 0 1.5rem;">No measurements have been stored yet for this device.</p>
                <p style="color: #6b7280; font-size: 0.9rem;">Start the <code>monitor.py</code> service to begin collecting data automatically.</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning('No device selected. Choose a device in the sidebar.')

    st.markdown("""
    <div style="margin-top: 2.5rem; padding: 1.25rem 1.5rem; border-top: 1px solid #D9D9D9;
                display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <svg width="32" height="32" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="20" cy="20" r="20" fill="#3A7F5F"/>
                <text x="20" y="26" text-anchor="middle" font-family="Inter,sans-serif" font-size="13" font-weight="700" fill="#ffffff">EDS</text>
            </svg>
            <div>
                <p style="margin:0; font-size:0.82rem; font-weight:600; color:#3A7F5F; line-height:1.2;">Environmental Data Services</p>
                <p style="margin:0; font-size:0.75rem; color:#6b7280; line-height:1.2;">e-flow™ sewer monitoring platform</p>
            </div>
        </div>
        <p style="margin:0; font-size:0.75rem; color:#9ca3af;">
            <a href="https://www.e-d-s.com.au" target="_blank"
               style="color:#3A7F5F; text-decoration:none; font-weight:500;">www.e-d-s.com.au</a>
            &nbsp;·&nbsp; © 2026 EDS
        </p>
    </div>
    """, unsafe_allow_html=True)

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
        <h2 style="margin: 0; font-weight: 700; letter-spacing: -0.02em; color: #4A4A4A;">
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
    measurements = get_cached_measurements(device_id=selected_device_id)

    if measurements:
        df = pd.DataFrame(measurements)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
        df = df.dropna(subset=["timestamp"])

        # Make timestamps tz-aware (UTC) so comparison with cutoff_time works
        if not df.empty and df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(pytz.utc)

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
                    <p class="metric-label">Water Depth</p>
                    <p class="metric-value">{depth_str}<span class="metric-unit">mm</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">Flow Velocity</p>
                    <p class="metric-value green">{velocity_str}<span class="metric-unit">m/s</span></p>
                </div>
                <div class="metric-card">
                    <p class="metric-label">Flow Rate</p>
                    <p class="metric-value amber">{flow_str}<span class="metric-unit">L/s</span></p>
                </div>
            </div>
            <p style="font-size: 0.82rem; color: #6b7280; margin: 0 0 1.5rem 4px;">
                ✓ Last reading: {lu_str} &nbsp;·&nbsp; {len(df)} records in selected window
            </p>
            """, unsafe_allow_html=True)

            # ── Main flow chart ─────────────────────────────────────────────
            st.markdown("""
            <p class="section-title" style="margin-top: 0.5rem;">Flow Rate Analysis</p>
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
                    line=dict(color='#1D4E89', width=2.5),
                    marker=dict(size=5, color='#1D4E89'),
                    fill='tozeroy',
                    fillcolor='rgba(29, 78, 137, 0.07)',
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
                    font=dict(family='Inter, -apple-system, sans-serif', color='#4A4A4A', size=12),
                    margin=dict(l=0, r=0, t=20, b=0),
                    xaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9'),
                    yaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9'),
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
                    f"No data for {graph_start.strftime('%Y-%m-%d %H:%M')} "
                    f"→ {graph_end.strftime('%Y-%m-%d %H:%M')}"
                )

            st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

            # ── Time-series tabs ───────────────────────────────────────────
            st.markdown('<p class="section-title">Time Series Analysis</p>', unsafe_allow_html=True)

            _chart_layout = dict(
                hovermode="x unified",
                height=400,
                template="plotly_white",
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
                font=dict(family='Inter, -apple-system, sans-serif', color='#4A4A4A', size=12),
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9', title='Time'),
                yaxis=dict(gridcolor='#f0f4f4', linecolor='#D9D9D9'),
            )

            tab1, tab2, tab3, tab4, tab5 = st.tabs(["Depth", "Velocity", "Flow", "Rainfall & I/I", "Statistics"])

            with tab1:
                fig_depth = px.line(df, x="timestamp", y="depth_mm",
                                    labels={"depth_mm": "Depth (mm)", "timestamp": "Time"},
                                    markers=True)
                fig_depth.update_traces(line=dict(color="#3A7F5F", width=2.5), marker=dict(size=5))
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
                fig_vel.update_traces(line=dict(color="#2A9D8F", width=2.5), marker=dict(size=5))
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
                fig_flow.update_traces(line=dict(color="#1D4E89", width=2.5), marker=dict(size=5))
                fig_flow.update_layout(**_chart_layout)
                fig_flow.update_yaxes(title_text="Flow Rate (L/s)")
                st.plotly_chart(fig_flow, use_container_width=True)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Mean", f"{df['flow_lps'].mean():.1f} L/s")
                col_s2.metric("Max", f"{df['flow_lps'].max():.1f} L/s")
                col_s3.metric("Min", f"{df['flow_lps'].min():.1f} L/s")
                col_s4.metric("Std Dev", f"{df['flow_lps'].std():.1f} L/s")

            with tab4:
                # ── Rainfall & I/I tab ─────────────────────────────────────
                _dev_info_r = next((d for d in db.get_devices() if d["device_id"] == selected_device_id), None)
                _has_loc = _dev_info_r and _dev_info_r.get("latitude") and _dev_info_r.get("longitude")
                _has_rain_station = db.get_device_rainfall_station(selected_device_id) is not None

                if not _has_loc and not _has_rain_station:
                    st.info(
                        "**No location set for this device.**\n\n"
                        "Go to Admin Panel → **Map Location & Rain Gauge** to set GPS coordinates "
                        "and optionally assign a BOM station. Rainfall data will then be fetched automatically."
                    )
                else:
                    # Fetch rainfall data for the current view window
                    _rain_date_from = graph_start if 'graph_start' in dir() else (datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=168))
                    _rain_date_to = graph_end if 'graph_end' in dir() else datetime.now(pytz.timezone(DEFAULT_TZ))

                    with st.spinner("Loading rainfall data…"):
                        try:
                            _rain_records = get_cached_rainfall(
                                selected_device_id,
                                _rain_date_from.isoformat(),
                                _rain_date_to.isoformat(),
                            )
                            df_rain = pd.DataFrame(_rain_records) if _rain_records else pd.DataFrame(columns=["timestamp", "rainfall_mm"])
                            if not df_rain.empty:
                                df_rain["timestamp"] = pd.to_datetime(df_rain["timestamp"])
                        except Exception as _re:
                            df_rain = pd.DataFrame(columns=["timestamp", "rainfall_mm"])
                            st.warning(f"⚠️ Could not load rainfall data: {_re}")

                    # ── Analysis ──────────────────────────────────────────
                    _df_flow_r = df.copy() if not df.empty else pd.DataFrame(columns=["timestamp", "flow_lps"])
                    _baseline = compute_dry_weather_baseline(_df_flow_r, df_rain)
                    _response = detect_inflow_infiltration(_df_flow_r, df_rain, _baseline)

                    # ── Summary cards ─────────────────────────────────────
                    _sev_color = {
                        "High": "#3A7F5F", "Medium": "#F4B400",
                        "Critical": "#D93025", "Low": "#4CAF50",
                    }
                    _ql = _response.quality_label
                    _badge_color = _sev_color.get(_ql, "#6b7280")

                    r_col1, r_col2, r_col3, r_col4 = st.columns(4)
                    r_col1.metric("Dry-Weather Baseline", f"{_baseline:.1f} L/s",
                                  help="Median flow during dry periods over the last 7 days")
                    r_col2.metric("Rain Events", len(_response.rain_events),
                                  help="Number of discrete rainfall events detected")
                    r_col3.metric("I/I Flags", len(_response.ii_flags),
                                  help="Flow responses that exceeded 1.5× baseline")
                    r_col4.metric("Confidence", f"{_response.confidence_score:.0f}%",
                                  help="Statistical confidence in the analysis")

                    st.markdown(
                        f"<div style='display:inline-block;background:{_badge_color};color:#fff;"
                        f"padding:4px 12px;border-radius:20px;font-size:0.82rem;"
                        f"font-weight:600;margin-bottom:1rem;'>"
                        f"I/I Risk: {_ql}</div>",
                        unsafe_allow_html=True,
                    )

                    # ── Combined chart ─────────────────────────────────────
                    if not df_rain.empty and not df.empty:
                        _fig_rain = make_subplots(
                            specs=[[{"secondary_y": True}]],
                            shared_xaxes=True,
                        )
                        # Rainfall bars (secondary y)
                        _fig_rain.add_trace(
                            go.Bar(
                                x=df_rain["timestamp"],
                                y=df_rain["rainfall_mm"],
                                name="Rainfall (mm/hr)",
                                marker_color="rgba(41, 182, 246, 0.6)",
                                hovertemplate="%{y:.1f} mm<extra>Rainfall</extra>",
                            ),
                            secondary_y=True,
                        )
                        # Flow line (primary y)
                        _fig_rain.add_trace(
                            go.Scatter(
                                x=df["timestamp"],
                                y=df["flow_lps"],
                                name="Flow (L/s)",
                                line=dict(color="#1D4E89", width=2.5),
                                fill="tozeroy",
                                fillcolor="rgba(29,78,137,0.07)",
                                hovertemplate="%{y:.2f} L/s<extra>Flow</extra>",
                            ),
                            secondary_y=False,
                        )
                        # Dry-weather baseline band
                        _fig_rain.add_hline(
                            y=_baseline,
                            line_dash="dash",
                            line_color="#3A7F5F",
                            annotation_text=f"Baseline {_baseline:.1f} L/s",
                            annotation_font_color="#3A7F5F",
                            secondary_y=False,
                        )
                        # Shade I/I event windows
                        for _flag in _response.ii_flags:
                            _fig_rain.add_vrect(
                                x0=_flag.rain_event.start,
                                x1=_flag.rain_event.end,
                                fillcolor="rgba(217,48,37,0.08)",
                                line_color="rgba(217,48,37,0.3)",
                                annotation_text=f"⚠ I/I ({_flag.severity})",
                                annotation_font_size=10,
                                annotation_font_color="#D93025",
                            )
                        _fig_rain.update_layout(
                            height=460,
                            template="plotly_white",
                            paper_bgcolor="#ffffff",
                            plot_bgcolor="#ffffff",
                            font=dict(family="Inter, sans-serif", color="#4A4A4A", size=12),
                            margin=dict(l=0, r=0, t=30, b=0),
                            hovermode="x unified",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            xaxis=dict(gridcolor="#f0f4f4", linecolor="#D9D9D9", title="Time"),
                            yaxis=dict(gridcolor="#f0f4f4", linecolor="#D9D9D9"),
                        )
                        _fig_rain.update_yaxes(title_text="Flow Rate (L/s)", secondary_y=False)
                        _fig_rain.update_yaxes(
                            title_text="Rainfall (mm/hr)", secondary_y=True,
                            autorange="reversed",
                        )
                        st.plotly_chart(_fig_rain, use_container_width=True)
                    elif df.empty:
                        st.info("No flow data available for the selected window.")
                    else:
                        st.info(
                            "No rainfall data available for this period. "
                            "The system will attempt to fetch data from BOM or Open-Meteo. "
                            "Try refreshing or widen the time window."
                        )

                    # ── Rain events table ──────────────────────────────────
                    if _response.rain_events:
                        with st.expander(f"Rain Events ({len(_response.rain_events)})", expanded=False):
                            _ev_df = pd.DataFrame([
                                {
                                    "Start": e.start.strftime("%d/%m %H:%M") if hasattr(e.start, "strftime") else str(e.start),
                                    "End": e.end.strftime("%d/%m %H:%M") if hasattr(e.end, "strftime") else str(e.end),
                                    "Duration (h)": f"{e.duration_hours:.1f}",
                                    "Total (mm)": f"{e.total_mm:.1f}",
                                    "Peak (mm/hr)": f"{e.peak_mm_per_hour:.1f}",
                                }
                                for e in _response.rain_events
                            ])
                            st.dataframe(_ev_df, use_container_width=True, hide_index=True)

                    # ── I/I flags table ────────────────────────────────────
                    if _response.ii_flags:
                        _sev_color = {"critical": "#c62828", "high": "#e65100", "medium": "#f57f17", "low": "#1565c0"}
                        with st.expander(f"I/I Flags ({len(_response.ii_flags)})", expanded=True):
                            for _flag in _response.ii_flags:
                                _col = _sev_color.get(_flag.severity, "#555")
                                st.markdown(
                                    f"<span style='font-weight:600;color:{_col};'>{_flag.severity.upper()}</span> — "
                                    f"{_flag.description}  \n"
                                    f"<span style='font-size:0.8rem;color:#6b7280;'>"
                                    f"Peak: {_flag.peak_flow_lps:.1f} L/s &nbsp;·&nbsp; "
                                    f"Ratio: {_flag.response_ratio:.1f}× &nbsp;·&nbsp; "
                                    f"Lag: {_flag.lag_hours:.1f} h &nbsp;·&nbsp; "
                                    f"Confidence: {_flag.confidence:.0f}%</span>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

                    # ── Recommendations ────────────────────────────────────
                    if _response.recommendations:
                        st.markdown("#### Recommendations")
                        for _rec in _response.recommendations:
                            st.markdown(_rec)

            with tab5:
                st.markdown("#### Aggregate Statistics")
                col_sum1, col_sum2, col_sum3 = st.columns(3)
                with col_sum1:
                    st.markdown("**Water Depth**")
                    st.metric("Mean", f"{df['depth_mm'].mean():.1f} mm")
                    st.metric("Median", f"{df['depth_mm'].median():.1f} mm")
                    st.metric("Range", f"{df['depth_mm'].max() - df['depth_mm'].min():.1f} mm")
                with col_sum2:
                    st.markdown("**Flow Velocity**")
                    st.metric("Mean", f"{df['velocity_mps'].mean():.3f} m/s")
                    st.metric("Median", f"{df['velocity_mps'].median():.3f} m/s")
                    st.metric("Range", f"{df['velocity_mps'].max() - df['velocity_mps'].min():.3f} m/s")
                with col_sum3:
                    st.markdown("**Flow Rate**")
                    st.metric("Mean", f"{df['flow_lps'].mean():.1f} L/s")
                    st.metric("Median", f"{df['flow_lps'].median():.1f} L/s")
                    st.metric("Range", f"{df['flow_lps'].max() - df['flow_lps'].min():.1f} L/s")

                st.markdown("---")
                st.markdown("#### Distribution")
                dist_col1, dist_col2 = st.columns(2)
                with dist_col1:
                    fig_hist_d = px.histogram(df, x="depth_mm", nbins=20,
                                              labels={"depth_mm": "Depth (mm)"})
                    fig_hist_d.update_traces(marker_color="#3A7F5F")
                    fig_hist_d.update_layout(
                        height=280, template="plotly_white", paper_bgcolor="#ffffff",
                        plot_bgcolor="#ffffff", margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(family='Inter, sans-serif', size=11),
                        xaxis=dict(gridcolor='#f0f4f4'), yaxis=dict(gridcolor='#f0f4f4')
                    )
                    st.plotly_chart(fig_hist_d, use_container_width=True)
                with dist_col2:
                    fig_hist_f = px.histogram(df, x="flow_lps", nbins=20,
                                              labels={"flow_lps": "Flow (L/s)"})
                    fig_hist_f.update_traces(marker_color="#1D4E89")
                    fig_hist_f.update_layout(
                        height=280, template="plotly_white", paper_bgcolor="#ffffff",
                        plot_bgcolor="#ffffff", margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(family='Inter, sans-serif', size=11),
                        xaxis=dict(gridcolor='#f0f4f4'), yaxis=dict(gridcolor='#f0f4f4')
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
            st.markdown('<p class="section-title">Data Table & Export</p>', unsafe_allow_html=True)
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
                    width="stretch"
                )
            with col_dl2:
                st.download_button(
                    "⬇ Download JSON",
                    data=df.to_json(orient="records", date_format="iso"),
                    file_name=f"flow_{selected_device_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                    width="stretch"
                )
        else:
            st.markdown("""
            <div style="background: #ffffff; border: 1px solid #D9D9D9; border-radius: 12px; padding: 40px; text-align: center; margin: 2rem 0;">
                <h3 style="color: #4A4A4A; margin: 0 0 0.5rem;">No data in selected window</h3>
                <p style="color: #6b7280; margin: 0;">Try a wider time window, or start the <code>monitor.py</code> service to collect data.</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: #ffffff; border: 1px solid #D9D9D9; border-radius: 12px; padding: 40px; text-align: center; margin: 2rem 0;">
            <h3 style="color: #4A4A4A; margin: 0 0 0.5rem;">Awaiting first reading</h3>
            <p style="color: #6b7280; margin: 0 0 1.5rem;">No measurements have been stored yet.</p>
            <p style="color: #6b7280; font-size: 0.9rem;">Run <code>python monitor.py</code> or <code>docker-compose up</code> to start collecting data automatically.</p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("Select a device from the sidebar to view data.")

# ── Footer ──────────────────────────────────────────────────────────────────
now_footer = datetime.now(pytz.timezone(DEFAULT_TZ))
st.markdown(f"""
<div class="app-footer">
    <span class="app-footer-brand">e-flow™ by EDS</span>
    <span class="app-footer-meta">
        {now_footer.strftime('%Y-%m-%d %H:%M %Z')} &nbsp;·&nbsp;
        Timezone: {DEFAULT_TZ} &nbsp;·&nbsp;
        Monitor service: {'enabled' if MONITOR_ENABLED else 'disabled'}
    </span>
</div>
""", unsafe_allow_html=True)
