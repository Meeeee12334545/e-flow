"""
Reports page – on-demand PDF / HTML report generation with AI insights.

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
    create_charts,
    build_html_report,
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
)

# ── Auth guard ─────────────────────────────────────────────────────────────
init_auth_state()
if not is_authenticated():
    login_page()
    st.stop()

st.set_page_config(
    page_title="e-flow | Reports",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()

DEFAULT_TZ = "Australia/Brisbane"
db = FlowDatabase()

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    render_auth_header()
    st.markdown("## Device")
    devices = db.get_devices()
    devices = filter_devices_for_user(devices)
    device_names = {d["device_name"]: d["device_id"] for d in devices}

    if not device_names:
        st.warning("⚠️ No devices assigned to your account")
        st.stop()

    selected_device_name: str = st.selectbox(
        "Select Device",
        options=sorted(device_names.keys()),
        key="report_device_selector",
        label_visibility="collapsed",
    )
    selected_device_id = device_names[selected_device_name]
    device_info = next((d for d in devices if d["device_id"] == selected_device_id), None)

# ── Page header ────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 style="margin:0; font-size:1.9rem; font-weight:700; color:#233047;">
        📄 Report Generation
    </h1>
    <p style="margin:0.3rem 0 0; color:#6b7280; font-size:0.95rem;">
        Generate on-demand PDF reports with AI data quality insights.
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── Report configuration ───────────────────────────────────────────────────
col_cfg, col_prev = st.columns([1, 2])

with col_cfg:
    st.markdown("### Report Settings")

    report_type = st.selectbox(
        "Report Type",
        options=["Daily Summary", "Weekly Summary", "Monthly Summary", "Custom Range"],
        index=0,
        key="report_type",
    )

    now_local = datetime.now(pytz.timezone(DEFAULT_TZ))

    if report_type == "Daily Summary":
        date_from = (now_local - timedelta(hours=24)).replace(tzinfo=None)
        date_to = now_local.replace(tzinfo=None)
        hours = 24
        report_type_key = "daily"
    elif report_type == "Weekly Summary":
        date_from = (now_local - timedelta(days=7)).replace(tzinfo=None)
        date_to = now_local.replace(tzinfo=None)
        hours = 168
        report_type_key = "weekly"
    elif report_type == "Monthly Summary":
        date_from = (now_local - timedelta(days=30)).replace(tzinfo=None)
        date_to = now_local.replace(tzinfo=None)
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
    inc_depth = st.checkbox("Depth (depth_mm)", value=True)
    inc_vel = st.checkbox("Velocity (velocity_mps)", value=True)
    inc_flow = st.checkbox("Flow (flow_lps)", value=True)

    variables = []
    if inc_depth:
        variables.append("depth_mm")
    if inc_vel:
        variables.append("velocity_mps")
    if inc_flow:
        variables.append("flow_lps")

    if not variables:
        st.warning("Select at least one variable.")

    include_ai = st.checkbox("Include AI anomaly analysis", value=True)

    generate_clicked = st.button(
        "🗂️ Generate Report",
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
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.sort_values("timestamp", inplace=True)
                # Filter to the requested window
                ts_from = pd.Timestamp(date_from)
                ts_to = pd.Timestamp(date_to)
                if ts_from.tzinfo is None:
                    ts_from = ts_from.tz_localize(None)
                if ts_to.tzinfo is None:
                    ts_to = ts_to.tz_localize(None)
                # Normalise df timestamps for comparison
                if df["timestamp"].dt.tz is not None:
                    df_ts_cmp = df["timestamp"].dt.tz_localize(None)
                else:
                    df_ts_cmp = df["timestamp"]
                mask = (df_ts_cmp >= ts_from) & (df_ts_cmp <= ts_to)
                df_window = df[mask].copy()
            else:
                df_window = pd.DataFrame()

            # ── Anomaly detection ──────────────────────────────────────────
            anomaly_rep = None
            if include_ai and not df_window.empty:
                anomaly_rep = run_anomaly_detection(df_window, columns=variables)

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
            )

            calcs = compute_calculations(df_window, selections)
            charts = create_charts(df_window, selections)

            html_content = build_html_report(
                selected_device_name, df_window, selections, calcs, charts
            )
            pdf_bytes = build_pdf_report(
                selected_device_name, df_window, selections, calcs, charts
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

            st.session_state["last_report_html"] = html_content
            st.session_state["last_report_pdf"] = pdf_bytes
            st.session_state["last_report_name"] = (
                f"eflow_{selected_device_id}_{report_type_key}_{datetime.now().strftime('%Y%m%d_%H%M')}"
            )
            st.session_state["last_anomaly_rep"] = anomaly_rep
            st.session_state["last_report_df"] = df_window

        st.success("✅ Report generated successfully")

    # ── Show data quality badge ────────────────────────────────────────────
    if "last_anomaly_rep" in st.session_state and st.session_state["last_anomaly_rep"] is not None:
        ar = st.session_state["last_anomaly_rep"]
        qual_color = {"High": "#047c3d", "Medium": "#b45309", "Low": "#b91c1c"}.get(ar.quality_label, "#333")
        qual_bg = {"High": "#daf9e6", "Medium": "#fef3c7", "Low": "#fee2e2"}.get(ar.quality_label, "#f9fafb")
        qual_icon = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(ar.quality_label, "⚪")
        st.markdown(f"""
        <div style="background:{qual_bg}; border: 2px solid {qual_color}; border-radius:10px;
                    padding:14px 18px; margin-bottom:1rem;">
            <div style="font-size:1.1rem; font-weight:700; color:{qual_color};">
                {qual_icon} Data Quality: {ar.quality_label}
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
            label="⬇️ Download PDF Report",
            data=pdf_bytes,
            file_name=f"{fname}.pdf",
            mime="application/pdf",
            type="primary",
        )
    elif "last_report_html" in st.session_state and st.session_state["last_report_html"]:
        html_bytes = st.session_state["last_report_html"].encode("utf-8")
        fname = st.session_state.get("last_report_name", "eflow_report")
        st.info("ℹ️ PDF export requires WeasyPrint. Downloading HTML report instead.")
        st.download_button(
            label="⬇️ Download HTML Report",
            data=html_bytes,
            file_name=f"{fname}.html",
            mime="text/html",
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

            csv_data = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Download CSV",
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
    st.dataframe(hist_df[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("No reports generated yet for this device.")

# ── Anomaly log ────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Anomaly Log")

with st.expander("View recent anomaly flags for this device", expanded=False):
    flags = db.get_anomaly_flags(device_id=selected_device_id, include_overridden=True, limit=200)
    if flags:
        flags_df = pd.DataFrame(flags)
        display_cols = [c for c in
                        ["measurement_timestamp", "column_name", "anomaly_type",
                         "severity", "description", "overridden", "override_note"]
                        if c in flags_df.columns]
        st.dataframe(flags_df[display_cols], use_container_width=True, hide_index=True)

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
