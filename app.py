import asyncio
import os
import sys
import subprocess
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
from config import DEVICES

# Ensure Playwright browsers are installed for Streamlit Cloud
@st.cache_resource
def ensure_playwright_installed():
    """Install Playwright browsers if not already installed."""
    try:
        # Try to install Playwright browsers
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            timeout=120
        )
    except Exception as e:
        pass  # Silent fail - monitoring happens elsewhere
    return True

# Install on startup (cached so only runs once)
ensure_playwright_installed()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="e-flow | Hydrological Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Page styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 8px;
        border-left: 4px solid #0066cc;
    }
    .status-active { color: #00aa00; font-weight: bold; }
    .status-idle { color: #cc6600; font-weight: bold; }
    .status-error { color: #cc0000; font-weight: bold; }
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
    measurements = db.get_measurements(device_id, hours=24)
    if not measurements:
        return {}
    
    df = pd.DataFrame(measurements)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return {
        'total_points': len(df),
        'time_span': (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 3600,
        'collection_rate': len(df) / max(1, (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60),
    }


# Page header
col1, col2 = st.columns([3, 1])
with col1:
    st.title("e-flow | Hydrological Analytics Platform")
with col2:
    st.markdown(f"<div class='status-active'>● LIVE</div>", unsafe_allow_html=True)

st.markdown("---")

# Sidebar configuration
with st.sidebar:
    st.header("Configuration & Status")
    
    st.markdown("""
    **System Status**: Continuous monitoring active
    - Monitor interval: 60 seconds
    - Collection method: Selenium WebDriver
    - Database: SQLite3 with change-detection
    """)
    
    st.divider()
    
    # Select device to view
    devices = db.get_devices()
    if devices:
        device_names = {d["device_name"]: d["device_id"] for d in devices}
        selected_device_name = st.selectbox(
            "📍 Select Monitoring Station",
            options=sorted(device_names.keys()),
            key="device_selector"
        )
        selected_device_id = device_names[selected_device_name]
        
        # Get selected device info
        device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)
        if device_info:
            with st.expander("Station Details"):
                st.write(f"**ID**: {device_info['device_id']}")
                st.write(f"**Name**: {device_info['device_name']}")
                st.write(f"**Location**: {device_info['location'] or 'N/A'}")
                st.write(f"**Initialized**: {device_info['created_at']}")
    else:
        st.error("⚠️ No devices configured")
        st.info("Expected devices: " + ", ".join(DEVICES.keys()))
        selected_device_id = None
    
    st.divider()
    
    # Time range selection
    st.subheader("Query Parameters")
    time_range = st.selectbox(
        "Time Window",
        options=[(1, "1 hour"), (6, "6 hours"), (24, "24 hours"), (168, "7 days"), (720, "30 days")],
        format_func=lambda x: x[1],
        key="time_range"
    )[0]
    
    # Database stats
    st.subheader("System Metrics")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Monitored Stations", db.get_device_count())
    with col2:
        st.metric("Total Data Points", db.get_measurement_count())
    
    if selected_device_id:
        stats = get_collection_stats(selected_device_id)
        if stats:
            st.metric("24h Collection Rate", f"{stats.get('collection_rate', 0):.1f} pts/min")

# Main content area
if selected_device_id:
    # Get measurements for selected device
    measurements = db.get_measurements(device_id=selected_device_id)
    
    if measurements:
        df = pd.DataFrame(measurements)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Filter by time range
        cutoff_time = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=time_range)
        df = df[df["timestamp"] >= cutoff_time].sort_values("timestamp")
        
# Main content area
if selected_device_id:
    # Get measurements for selected device
    measurements = db.get_measurements(device_id=selected_device_id)
    
    if measurements:
        df = pd.DataFrame(measurements)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Filter by time range
        cutoff_time = datetime.now(pytz.timezone(DEFAULT_TZ)) - timedelta(hours=time_range)
        df = df[df["timestamp"] >= cutoff_time].sort_values("timestamp")
        
        if not df.empty:
            # Latest values with enhanced metrics
            st.subheader(f"Current Status: {selected_device_name}")
            latest = df.iloc[-1]
            last_update = latest["timestamp"]
            
            metric_cols = st.columns(3)
            
            with metric_cols[0]:
                depth = latest["depth_mm"]
                st.metric(
                    "Water Depth",
                    f"{depth:.1f} mm" if depth else "N/A",
                    delta=None,
                    help="Water level measurement in millimeters"
                )
            
            with metric_cols[1]:
                velocity = latest["velocity_mps"]
                st.metric(
                    "Flow Velocity",
                    f"{velocity:.3f} m/s" if velocity else "N/A",
                    delta=None,
                    help="Water velocity in meters per second"
                )
            
            with metric_cols[2]:
                flow = latest["flow_lps"]
                st.metric(
                    "Flow Rate",
                    f"{flow:.1f} L/s" if flow else "N/A",
                    delta=None,
                    help="Volumetric flow rate in liters per second"
                )
            
            # Data quality indicators
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.caption(f"🕒 Last Update: {last_update.strftime('%Y-%m-%d %H:%M:%S')}")
            with col_info2:
                st.caption(f"📊 Data Points (window): {len(df)}")
            with col_info3:
                st.caption(f"⏱️ Collection Rate: {len(df)/(time_range if time_range > 0 else 1):.1f} pts/hr")
            
            st.markdown("---")
            
            # Advanced analytics
            st.subheader("Time Series Analysis")
            
            if len(df) > 1:
                # Create tabs for different views
                tab1, tab2, tab3, tab4 = st.tabs(["Depth", "Velocity", "Flow", "Summary Statistics"])
                
                with tab1:
                    fig_depth = px.line(
                        df, x="timestamp", y="depth_mm",
                        title="Water Depth Time Series",
                        labels={"depth_mm": "Depth (mm)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_depth.update_traces(line=dict(color="#1f77b4", width=2), marker=dict(size=4))
                    fig_depth.update_layout(hovermode="x unified", height=400)
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
                        title="Velocity over Time",
                        labels={"velocity_mps": "Velocity (m/s)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_velocity.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_velocity, use_container_width=True)
                
                with tab3:
                    fig_flow = px.line(
                        df, x="timestamp", y="flow_lps",
                        title="Flow over Time",
                        labels={"flow_lps": "Flow (L/s)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_flow.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_flow, use_container_width=True)
            
            # Data table
            st.subheader("📋 Data Table")
            display_df = df[["timestamp", "depth_mm", "velocity_mps", "flow_lps"]].copy()
            display_df.columns = ["Timestamp", "Depth (mm)", "Velocity (m/s)", "Flow (L/s)"]
            display_df["Timestamp"] = display_df["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Export functionality
            st.subheader("📥 Export Data")
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
    else:
        st.info("No measurements found for this device. Please refresh data.")
else:
    st.info("👈 Select a device from the sidebar to view data.")

# Footer
st.markdown("---")
st.markdown(
    f"<small>Last update: {datetime.now(pytz.timezone(DEFAULT_TZ)).strftime('%Y-%m-%d %H:%M:%S %Z')} | "
    f"Timezone: {DEFAULT_TZ}</small>",
    unsafe_allow_html=True
)
