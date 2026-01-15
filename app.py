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
from scraper import DataScraper

# Ensure Playwright browsers are installed for Streamlit Cloud
def ensure_playwright_installed():
    """Install Playwright browsers if not already installed."""
    try:
        # Try to install Playwright browsers
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            timeout=120
        )
    except Exception as e:
        print(f"Note: Playwright installation returned: {e}")
    return True

# Install on startup
ensure_playwright_installed()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Flow Data Dashboard", layout="wide")

# Initialize database and scraper
db = FlowDatabase()
scraper = DataScraper(db)

DEFAULT_TZ = "Australia/Brisbane"


def format_measurement(value, unit):
    """Format measurement value with unit."""
    if value is None:
        return "N/A"
    return f"{value:.2f} {unit}"


st.title("📊 Flow Data Dashboard")
st.markdown("Real-time depth, velocity, and flow monitoring data")

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Manual data refresh
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.info("Fetching latest data from monitor...")
        try:
            data = asyncio.run(scraper.fetch_monitor_data())
            if data:
                st.success("✅ Data refreshed successfully!")
            else:
                st.warning("⚠️ Could not fetch data. Please check the monitor URL.")
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    # Select device to view
    devices = db.get_devices()
    if devices:
        device_names = {d["device_name"]: d["device_id"] for d in devices}
        selected_device_name = st.selectbox(
            "Select Device",
            options=device_names.keys(),
            key="device_selector"
        )
        selected_device_id = device_names[selected_device_name]
    else:
        st.info("No devices found. Please refresh data first.")
        selected_device_id = None
    
    # Time range selection
    st.subheader("Time Range")
    time_range = st.slider(
        "Last N hours",
        min_value=1,
        max_value=720,
        value=24,
        step=1
    )
    
    # Database stats
    st.subheader("📈 Database Statistics")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Devices", db.get_device_count())
    with col2:
        st.metric("Total Measurements", db.get_measurement_count())

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
            # Latest values
            st.subheader(f"Latest Reading - {selected_device_name}")
            latest = df.iloc[-1]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Depth (mm)", format_measurement(latest["depth_mm"], "mm"))
            with col2:
                st.metric("Velocity (mps)", format_measurement(latest["velocity_mps"], "m/s"))
            with col3:
                st.metric("Flow (lps)", format_measurement(latest["flow_lps"], "L/s"))
            
            st.markdown("---")
            
            # Charts
            st.subheader("📉 Historical Data")
            
            if len(df) > 1:
                # Create tabs for different views
                tab1, tab2, tab3 = st.tabs(["Depth", "Velocity", "Flow"])
                
                with tab1:
                    fig_depth = px.line(
                        df, x="timestamp", y="depth_mm",
                        title="Depth over Time",
                        labels={"depth_mm": "Depth (mm)", "timestamp": "Time"},
                        markers=True
                    )
                    fig_depth.update_layout(hovermode="x unified")
                    st.plotly_chart(fig_depth, use_container_width=True)
                
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
