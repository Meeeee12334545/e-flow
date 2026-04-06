"""
GIS Map page for EDS FlowSense.

Displays all monitoring sites on an interactive map, coloured by I/I risk.
Accessible from the Streamlit sidebar navigation.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from database import FlowDatabase
from gis import build_gis_figure
from metrics import compute_engineering_metrics
from shared_styles import apply_styles
from streamlit_auth import (
    filter_devices_for_user,
    get_sidebar_logo_path,
    init_auth_state,
    is_authenticated,
    login_page,
    render_auth_header,
)

# ── Auth guard ─────────────────────────────────────────────────────────────────
init_auth_state()
if not is_authenticated():
    login_page()
    st.stop()

st.set_page_config(
    page_title="EDS FlowSense | GIS Map",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()

_ASSETS = Path(__file__).parent.parent / "assets"
st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

db = FlowDatabase()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    render_auth_header()
    st.markdown("## GIS Map")
    st.caption("Monitoring sites coloured by I/I risk level.")

# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <p class="page-header-title">GIS Site Map</p>
    <p class="page-header-sub">
        Interactive map of all monitoring sites. Sites are coloured by
        Inflow/Infiltration (I/I) risk level.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Risk legend ────────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex; gap:20px; margin-bottom:1.25rem; flex-wrap:wrap;">
    <span style="display:flex;align-items:center;gap:6px;font-size:0.85rem;">
        <span style="width:14px;height:14px;border-radius:50%;background:#D93025;display:inline-block;"></span>
        High I/I Risk
    </span>
    <span style="display:flex;align-items:center;gap:6px;font-size:0.85rem;">
        <span style="width:14px;height:14px;border-radius:50%;background:#F4B400;display:inline-block;"></span>
        Medium I/I Risk
    </span>
    <span style="display:flex;align-items:center;gap:6px;font-size:0.85rem;">
        <span style="width:14px;height:14px;border-radius:50%;background:#4CAF50;display:inline-block;"></span>
        Low I/I Risk
    </span>
    <span style="display:flex;align-items:center;gap:6px;font-size:0.85rem;">
        <span style="width:14px;height:14px;border-radius:50%;background:#6b7280;display:inline-block;"></span>
        Unknown / No Data
    </span>
</div>
""", unsafe_allow_html=True)

# ── Load devices and compute per-device metrics ────────────────────────────────
devices = db.get_devices()
devices = filter_devices_for_user(devices)

device_metrics: dict = {}
for dev in devices:
    did = dev["device_id"]
    try:
        import pandas as pd
        measurements = db.get_measurements(device_id=did, limit=500)
        if measurements:
            df_dev = pd.DataFrame(measurements).copy()
            df_dev["timestamp"] = pd.to_datetime(df_dev["timestamp"], errors="coerce")
            df_dev = df_dev.dropna(subset=["timestamp"])
            device_metrics[did] = compute_engineering_metrics(df_dev)
        else:
            device_metrics[did] = {}
    except Exception:
        device_metrics[did] = {}

# ── Map ────────────────────────────────────────────────────────────────────────
fig = build_gis_figure(devices, device_metrics)
st.plotly_chart(fig, use_container_width=True)

# ── Site summary table ─────────────────────────────────────────────────────────
if devices:
    import pandas as pd

    st.markdown('<p class="section-title" style="margin-top:1.5rem;">Site Summary</p>', unsafe_allow_html=True)
    rows = []
    for dev in devices:
        did = dev["device_id"]
        m = device_metrics.get(did, {})
        lat = dev.get("latitude")
        lon = dev.get("longitude")
        rows.append({
            "Site": dev.get("device_name") or did,
            "Location": dev.get("location") or "—",
            "Coordinates": f"{lat:.4f}, {lon:.4f}" if (lat and lon) else "Not set",
            "I/I Risk": m.get("ii_risk", "—"),
            "DWF (L/s)": f"{m['dwf']:.1f}" if m.get("dwf") is not None else "—",
            "Peak Flow (L/s)": f"{m['pwwf']:.1f}" if m.get("pwwf") is not None else "—",
            "Confidence": f"{m['confidence']:.0f}%" if m.get("confidence") is not None else "—",
            "Model Readiness": m.get("model_readiness_label", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No devices found. Add devices in the Admin Panel.")

st.markdown(
    "<p style='font-size:0.8rem;color:#9ca3af;margin-top:1rem;'>"
    "Set GPS coordinates for each site in Admin Panel → Map Location to enable map plotting.</p>",
    unsafe_allow_html=True,
)
