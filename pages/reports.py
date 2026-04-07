"""
Reports page – on-demand PDF report generation with AI insights.

Accessible from the Streamlit sidebar navigation.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytz
import streamlit as st

from database import FlowDatabase
from anomaly import run_anomaly_detection
from reporting import (
    ReportSelections,
    compute_calculations,
    compute_volume_breakdown,
    create_charts,
    build_pdf_report,
)
from shared_styles import apply_styles
from streamlit_auth import (
    init_auth_state,
    is_authenticated,
    is_admin,
    login_page,
    render_auth_header,
    filter_devices_for_user,
    get_current_user,
    get_sidebar_logo_path,
)

# ── Auth guard ─────────────────────────────────────────────────────────────
init_auth_state()
if not is_authenticated():
    login_page()
    st.stop()

st.set_page_config(
    page_title="EDS FlowSense | Reports",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()

# EDS brand logo in the sidebar header (wide) and collapsed icon
_ASSETS = Path(__file__).parent.parent / "assets"
st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

DEFAULT_TZ = "Australia/Brisbane"
db = FlowDatabase()

# ── Load devices (outside sidebar so they are accessible everywhere) ────────
devices = db.get_devices()
devices = filter_devices_for_user(devices)
device_names = {d["device_name"]: d["device_id"] for d in devices}

if not device_names:
    st.warning("No devices assigned to your account.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    render_auth_header()

# ── Page header ────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 style="margin:0; font-size:1.9rem; font-weight:700; color:#ffffff;">
        Report Generation
    </h1>
    <p style="margin:0.3rem 0 0; color:rgba(255,255,255,0.85); font-size:0.95rem;">
        Generate on-demand PDF reports with AI data quality insights.
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── Report configuration ───────────────────────────────────────────────────
col_cfg, col_prev = st.columns([1, 2])

with col_cfg:
    st.markdown("### Report Settings")

    # ── Site / device selector ─────────────────────────────────────────────
    selected_device_name: str = st.selectbox(
        "Select Site",
        options=sorted(device_names.keys()),
        key="report_device_selector",
    )
    selected_device_id = device_names[selected_device_name]
    device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)

    report_type = st.selectbox(
        "Report Type",
        options=["Daily Summary", "Weekly Summary", "Monthly Summary", "Custom Range"],
        index=0,
        key="report_type",
    )

    now_local = datetime.now(pytz.timezone(DEFAULT_TZ))
    # Strip timezone for naive datetime arithmetic; values represent local time
    now_naive = now_local.astimezone(pytz.utc).replace(tzinfo=None)

    if report_type == "Daily Summary":
        date_from = now_naive - timedelta(hours=24)
        date_to = now_naive
        hours = 24
        report_type_key = "daily"
    elif report_type == "Weekly Summary":
        date_from = now_naive - timedelta(days=7)
        date_to = now_naive
        hours = 168
        report_type_key = "weekly"
    elif report_type == "Monthly Summary":
        date_from = now_naive - timedelta(days=30)
        date_to = now_naive
        hours = 720
        report_type_key = "monthly"
    else:
        report_type_key = "custom"
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            date_from = st.date_input("From", value=(now_local - timedelta(days=7)).date())
        with col_d2:
            date_to = st.date_input("To", value=now_local.date())
        date_from = datetime.combine(date_from, datetime.min.time())
        date_to = datetime.combine(date_to, datetime.max.time().replace(microsecond=0))
        hours = max(1, int((date_to - date_from).total_seconds() / 3600))

    st.markdown("**Variables to include**")
    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        inc_depth = st.checkbox("Depth", value=True)
    with col_v2:
        inc_vel = st.checkbox("Velocity", value=True)
    with col_v3:
        inc_flow = st.checkbox("Flow", value=True)

    variables = []
    if inc_depth:
        variables.append("depth_mm")
    if inc_vel:
        variables.append("velocity_mps")
    if inc_flow:
        variables.append("flow_lps")

    if not variables:
        st.warning("Select at least one variable.")

    st.markdown("**Report Content**")
    inc_stats   = st.checkbox("Summary statistics table", value=True, key="inc_stats")
    inc_charts  = st.checkbox("Time-series charts", value=True, key="inc_charts")
    inc_ai      = st.checkbox("Data quality assessment", value=True, key="inc_ai")

    # Volume breakdown — only relevant when flow is selected
    inc_vol_breakdown = False
    vol_interval = "daily"
    if inc_flow:
        inc_vol_breakdown = st.checkbox(
            "Flow volume breakdown (AM/PM & daily totals)",
            value=True,
            key="inc_vol_breakdown",
        )
        if inc_vol_breakdown:
            vol_interval = st.radio(
                "Breakdown interval",
                options=["daily", "am_pm", "hourly"],
                format_func=lambda x: {
                    "daily":  "Daily totals",
                    "am_pm":  "AM & PM + daily totals",
                    "hourly": "Hourly + daily totals",
                }[x],
                index=1,
                horizontal=True,
                key="vol_interval",
            )

    custom_title = st.text_input(
        "Custom report title (optional)",
        placeholder="e.g. Monthly Inflow Report — March 2025",
        key="custom_title",
    )

    generate_clicked = st.button(
        "Generate Report",
        type="primary",
        disabled=not variables,
        key="generate_report_btn",
    )

with col_prev:
    st.markdown("### Preview")
    if generate_clicked and variables:
        with st.spinner("Running anomaly detection and building report…"):
            # ── Load data ──────────────────────────────────────────────────
            limit = max(5000, hours * 60 + 500)
            rows = db.get_measurements(device_id=selected_device_id, limit=limit)
            df = pd.DataFrame(rows) if rows else pd.DataFrame()

            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
                df.sort_values("timestamp", inplace=True)
                # Normalise both the filter bounds and the df timestamps to UTC-naive
                # for a timezone-agnostic comparison.
                ts_from = pd.Timestamp(date_from)  # already naive (UTC) from date_from
                ts_to = pd.Timestamp(date_to)       # already naive (UTC) from date_to
                if df["timestamp"].dt.tz is not None:
                    # Convert tz-aware timestamps to UTC then strip tz for comparison
                    df_ts_cmp = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)
                else:
                    df_ts_cmp = df["timestamp"]
                mask = (df_ts_cmp >= ts_from) & (df_ts_cmp <= ts_to)
                df_window = df[mask].copy()
            else:
                df_window = pd.DataFrame()

            # ── Anomaly detection ──────────────────────────────────────────
            anomaly_rep = None
            if inc_ai and not df_window.empty:
                anomaly_rep = run_anomaly_detection(df_window, columns=variables)

            # ── Volume breakdown ───────────────────────────────────────────
            vol_breakdown = None
            if inc_vol_breakdown and "flow_lps" in variables and not df_window.empty:
                vol_breakdown = compute_volume_breakdown(
                    df_window,
                    interval=vol_interval,
                    tz=DEFAULT_TZ,
                )

            # ── Build report ───────────────────────────────────────────────
            calculations_all = ["mean", "max", "min", "std", "p50", "p95", "volume", "count"]
            selections = ReportSelections(
                variables=variables,
                calculations=calculations_all,
                device_name=selected_device_name,
                time_window_hours=hours,
                report_type=report_type_key,
                site_id=selected_device_id,
                location=device_info.get("location", "") if device_info else "",
                anomaly_report=anomaly_rep,
                include_stats_table=inc_stats,
                include_charts=inc_charts,
                include_volume_breakdown=inc_vol_breakdown,
                volume_breakdown_interval=vol_interval,
                report_timezone=DEFAULT_TZ,
                custom_title=custom_title.strip() if custom_title else "",
            )

            calcs = compute_calculations(df_window, selections)
            charts = create_charts(df_window, selections)

            _logo_path = get_sidebar_logo_path()
            pdf_bytes = build_pdf_report(
                selected_device_name, df_window, selections, calcs, charts,
                logo_path=_logo_path,
                volume_breakdown=vol_breakdown,
            )

            # ── Save report record to DB ───────────────────────────────────
            try:
                period_start_dt = pd.Timestamp(date_from).to_pydatetime()
                period_end_dt = pd.Timestamp(date_to).to_pydatetime()
                db.save_report_record(
                    device_id=selected_device_id,
                    report_type=report_type_key,
                    period_start=period_start_dt,
                    period_end=period_end_dt,
                    anomaly_count=len(anomaly_rep.flags) if anomaly_rep else 0,
                    confidence_score=anomaly_rep.confidence_score if anomaly_rep else 100.0,
                    quality_label=anomaly_rep.quality_label if anomaly_rep else "High",
                    summary=anomaly_rep.summary if anomaly_rep else "",
                )
            except Exception:
                pass

            st.session_state["last_report_pdf"] = pdf_bytes
            st.session_state["last_report_name"] = (
                f"eflow_{selected_device_id}_{report_type_key}_{datetime.now().strftime('%Y%m%d_%H%M')}"
            )
            st.session_state["last_anomaly_rep"] = anomaly_rep
            st.session_state["last_report_df"] = df_window

        st.success("Report generated successfully")

    # ── Show data quality badge ────────────────────────────────────────────
    if "last_anomaly_rep" in st.session_state and st.session_state["last_anomaly_rep"] is not None:
        ar = st.session_state["last_anomaly_rep"]
        qual_color = {"High": "#4CAF50", "Medium": "#F4B400", "Low": "#D93025"}.get(ar.quality_label, "#333")
        qual_bg = {"High": "#E8F5E9", "Medium": "#FFF8E1", "Low": "#FDECEA"}.get(ar.quality_label, "#f9fafb")
        st.markdown(f"""
        <div style="background:{qual_bg}; border: 2px solid {qual_color}; border-radius:10px;
                    padding:14px 18px; margin-bottom:1rem;">
            <div style="font-size:1.1rem; font-weight:700; color:{qual_color};">
                Data Quality: {ar.quality_label}
            </div>
            <div style="font-size:0.88rem; color:#555; margin-top:4px;">
                Confidence Score: <strong>{ar.confidence_score:.1f}/100</strong> &nbsp;·&nbsp;
                {len(ar.flags)} anomaly flag(s) &nbsp;·&nbsp;
                {ar.pct_valid:.1f}% valid data
            </div>
            <div style="font-size:0.84rem; color:#666; margin-top:4px;"><em>{ar.summary}</em></div>
        </div>
        """, unsafe_allow_html=True)

    # ── Download buttons ───────────────────────────────────────────────────
    if "last_report_pdf" in st.session_state and st.session_state["last_report_pdf"]:
        pdf_bytes = st.session_state["last_report_pdf"]
        fname = st.session_state.get("last_report_name", "eflow_report")
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name=f"{fname}.pdf",
            mime="application/pdf",
            type="primary",
        )

    if "last_report_df" in st.session_state:
        df_dl = st.session_state["last_report_df"]
        if not df_dl.empty:
            # ── CSV download options ────────────────────────────────────────
            st.markdown("**CSV Export**")
            csv_type = st.radio(
                "Data to include",
                options=["All data (raw)", "Valid data only (AI-cleaned)", "Flagged data only"],
                index=0,
                horizontal=True,
                key="csv_export_type",
            )
            ar_csv = st.session_state.get("last_anomaly_rep")
            fname = st.session_state.get("last_report_name", "eflow_data")

            if csv_type == "Valid data only (AI-cleaned)" and ar_csv is not None:
                flagged_idx = ar_csv.flagged_indices()
                df_export = df_dl[~df_dl.index.isin(flagged_idx)]
            elif csv_type == "Flagged data only" and ar_csv is not None:
                flagged_idx = ar_csv.flagged_indices()
                df_export = df_dl[df_dl.index.isin(flagged_idx)]
            else:
                df_export = df_dl

            csv_data = df_export.copy()
            if 'timestamp' in csv_data.columns:
                ts_col = pd.to_datetime(csv_data['timestamp'], utc=True, format="ISO8601", errors='coerce')
                csv_data['timestamp'] = ts_col.dt.tz_convert(DEFAULT_TZ).dt.strftime('%d/%m/%Y %H:%M:%S')
            csv_data = csv_data.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"{fname}.csv",
                mime="text/csv",
            )

# ── Report history ─────────────────────────────────────────────────────────
st.divider()
st.markdown("### Report History")
history = db.get_report_records(device_id=selected_device_id, limit=20)
if history:
    hist_df = pd.DataFrame(history)
    display_cols = [c for c in
                    ["generated_at", "report_type", "period_start", "period_end",
                     "quality_label", "confidence_score", "anomaly_count", "summary"]
                    if c in hist_df.columns]
    st.dataframe(hist_df[display_cols], width="stretch", hide_index=True)
else:
    st.info("No reports generated yet for this device.")

# ── Anomaly log ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Anomaly Log")

with st.expander("View recent anomaly flags for this device", expanded=False):
    flags = db.get_anomaly_flags(device_id=selected_device_id, include_overridden=True, limit=200)
    if flags:
        flags_df = pd.DataFrame(flags)
        # Format the measurement timestamp to a readable date/time string
        if 'measurement_timestamp' in flags_df.columns:
            flags_df['measurement_timestamp'] = (
                pd.to_datetime(flags_df['measurement_timestamp'], utc=True, errors='coerce')
                .dt.tz_convert(DEFAULT_TZ)
                .dt.strftime('%d/%m/%Y %H:%M:%S')
            )
            flags_df = flags_df.rename(columns={'measurement_timestamp': 'Date / Time'})
        display_cols = [c for c in
                        ["Date / Time", "column_name", "anomaly_type",
                         "severity", "description", "overridden", "override_note"]
                        if c in flags_df.columns]
        st.dataframe(flags_df[display_cols], width="stretch", hide_index=True)

        # Admin: override a flag
        if is_admin():
            st.markdown("#### Override a Flag")
            flag_id = st.number_input("Flag ID to override", min_value=1, step=1, key="override_flag_id")
            override_note = st.text_input("Override note", key="override_note")
            if st.button("Mark as overridden", key="override_btn"):
                user = get_current_user()
                username = user.get("username", "admin") if user else "admin"
                ok = db.override_anomaly_flag(
                    flag_id=int(flag_id),
                    override_note=override_note,
                    overridden_by=username,
                )
                if ok:
                    st.success(f"Flag #{flag_id} overridden.")
                    st.rerun()
                else:
                    st.error("Flag not found.")
    else:
        st.info("No anomaly flags stored for this device yet.")
