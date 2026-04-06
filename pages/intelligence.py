"""
Site Intelligence page — baseline learning and alarm advisory for e-flow EDS.

Analyses long-term monitoring data to:
  • Show data readiness status (insufficient → basic → full → seasonal)
  • Display diurnal / day-of-week / distribution profiles per sensor variable
  • Summarise long-term trends with statistical significance
  • Generate and manage data-driven alarm level recommendations

Accessible from the Streamlit sidebar navigation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from baseline_learning import (
    SENSOR_VARIABLES,
    AlarmRecommendation,
    SiteBaseline,
    baseline_from_json,
    baseline_to_json,
    build_intelligence_pdf,
    compute_site_baseline,
    generate_alarm_recommendations,
    check_data_sufficiency,
    _SENSOR_META,
    _LEVEL_LABELS,
    _SENSITIVITY_LABELS,
)
from database import FlowDatabase
from shared_styles import apply_styles
from streamlit_auth import (
    filter_devices_for_user,
    get_current_user,
    get_sidebar_logo_path,
    init_auth_state,
    is_authenticated,
    is_admin,
    login_page,
    render_auth_header,
)

# ── Auth guard ─────────────────────────────────────────────────────────────────
init_auth_state()
if not is_authenticated():
    login_page()
    st.stop()

st.set_page_config(
    page_title="e-flow | Site Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()

_ASSETS = Path(__file__).parent.parent / "assets"
st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

db = FlowDatabase()

# ── Load devices ───────────────────────────────────────────────────────────────
devices = db.get_devices()
devices = filter_devices_for_user(devices)
device_names = {d["device_name"]: d["device_id"] for d in devices}

if not device_names:
    st.warning("No devices assigned to your account.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    render_auth_header()

# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 style="margin:0; font-size:1.9rem; font-weight:700; color:#ffffff;">
        🧠 Site Intelligence
    </h1>
    <p style="margin:0.3rem 0 0; color:rgba(255,255,255,0.85); font-size:0.95rem;">
        Learn from historical data to generate site-specific alarm recommendations and trend insights.
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── Device selector ────────────────────────────────────────────────────────────
col_sel, col_action = st.columns([2, 1])
with col_sel:
    selected_device_name: str = st.selectbox(
        "Select Site",
        options=sorted(device_names.keys()),
        key="intel_device_selector",
    )
selected_device_id = device_names[selected_device_name]

# ── Colour helpers ─────────────────────────────────────────────────────────────
_STATUS_COLOURS = {
    "insufficient": ("#D93025", "#FDECEA"),
    "basic":        ("#F4B400", "#FFF8E1"),
    "full":         ("#3A7F5F", "#E8F3EE"),
    "seasonal":     ("#1D4E89", "#E3EBF6"),
}
_STATUS_LABELS = {
    "insufficient": "Insufficient Data",
    "basic":        "Basic Analysis",
    "full":         "Full Analysis",
    "seasonal":     "Seasonal Analysis",
}
_VAR_COLOURS = {
    "depth_mm":     "#3A7F5F",
    "velocity_mps": "#2A9D8F",
    "flow_lps":     "#1D4E89",
}
_LEVEL_COLOURS = {
    "low_warning":  "#F4B400",
    "high_warning": "#E65100",
    "critical":     "#D93025",
}
_TREND_COLOURS = {
    "stable":               "#4CAF50",
    "gradual_increase":     "#F4B400",
    "gradual_decrease":     "#2A9D8F",
    "significant_increase": "#D93025",
    "significant_decrease": "#1D4E89",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_all_measurements(device_id: str) -> pd.DataFrame:
    """Load all stored measurements for *device_id* (no row cap for baseline learning)."""
    rows = db.get_measurements(device_id=device_id, limit=200_000)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _cached_baseline(device_id: str) -> Optional[SiteBaseline]:
    """Load a SiteBaseline from the DB cache, or None if not present."""
    row = db.get_device_baseline(device_id)
    if row and row.get("baseline_json"):
        return baseline_from_json(row["baseline_json"])
    return None


def _run_analysis(device_id: str, df: pd.DataFrame) -> SiteBaseline:
    """Compute and persist a SiteBaseline for *device_id*."""
    baseline = compute_site_baseline(df, device_id)
    db.save_device_baseline(
        device_id=device_id,
        computed_at=baseline.computed_at,
        readings_used=baseline.readings_used,
        days_covered=baseline.days_covered,
        baseline_json=baseline_to_json(baseline),
        status=baseline.status,
    )
    # Persist all three sensitivity levels
    recs = generate_alarm_recommendations(baseline)
    if recs:
        rec_dicts = [
            {
                "variable":         r.variable,
                "direction":        r.direction,
                "level_name":       r.level_name,
                "recommended_value": r.recommended_value,
                "sensitivity":      r.sensitivity,
                "basis":            r.basis,
                "estimated_fp_pct": r.estimated_fp_pct,
            }
            for r in recs
        ]
        db.save_alarm_recommendations(device_id, rec_dicts)
    return baseline


# ── Section 1: Data Readiness ──────────────────────────────────────────────────

def _render_readiness(baseline: Optional[SiteBaseline], df: pd.DataFrame) -> None:
    st.markdown("### 📊 Data Readiness")

    if baseline is None:
        suf = check_data_sufficiency(df)
    else:
        suf = baseline.sufficiency

    colour, bg = _STATUS_COLOURS.get(suf.status, ("#333", "#f9f9f9"))
    status_label = _STATUS_LABELS.get(suf.status, suf.status.title())

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Status", status_label)
    col_b.metric("Total Readings", f"{suf.total_readings:,}")
    col_c.metric("Data Coverage", f"{suf.days_covered:.1f} days")
    col_d.metric("Collection Rate", f"{suf.readings_per_day:.0f} /day")

    st.markdown(f"""
    <div style="background:{bg}; border:2px solid {colour}; border-radius:10px;
                padding:14px 18px; margin:0.5rem 0 1rem;">
        <div style="font-size:1.05rem; font-weight:700; color:{colour}; margin-bottom:6px;">
            {status_label}
        </div>
        <div style="font-size:0.88rem; color:#4A4A4A;">{suf.status_description}</div>
        <div style="font-size:0.84rem; color:#6b7280; margin-top:6px;">
            <em>{suf.next_level_description}</em>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Progress bar showing level achieved
    level_pct = {"insufficient": 5, "basic": 33, "full": 66, "seasonal": 100}.get(suf.status, 5)
    st.progress(level_pct / 100, text=f"Analysis readiness: {level_pct}%")


# ── Diurnal chart ──────────────────────────────────────────────────────────────

def _diurnal_chart(variable: str, profile) -> go.Figure:
    diurnal = profile.diurnal
    colour  = _VAR_COLOURS.get(variable, "#3A7F5F")
    meta    = _SENSOR_META.get(variable, {})
    unit    = meta.get("unit", "")
    label   = meta.get("label", variable)
    hours   = diurnal.hours

    fig = go.Figure()
    # P10–P90 outer band
    fig.add_trace(go.Scatter(
        x=hours + hours[::-1],
        y=diurnal.p90 + diurnal.p10[::-1],
        fill="toself", fillcolor=f"rgba({_hex_to_rgb(colour)},0.10)",
        line=dict(color="rgba(0,0,0,0)"),
        name="P10–P90", showlegend=True, legendrank=3,
    ))
    # P25–P75 inner band
    fig.add_trace(go.Scatter(
        x=hours + hours[::-1],
        y=diurnal.p75 + diurnal.p25[::-1],
        fill="toself", fillcolor=f"rgba({_hex_to_rgb(colour)},0.22)",
        line=dict(color="rgba(0,0,0,0)"),
        name="P25–P75", showlegend=True, legendrank=2,
    ))
    # Median line
    fig.add_trace(go.Scatter(
        x=hours, y=diurnal.median,
        mode="lines+markers",
        line=dict(color=colour, width=2.5),
        marker=dict(size=5, color=colour),
        name="Median", legendrank=1,
    ))
    fig.update_layout(
        title=dict(text=f"{label} — 24-Hour Diurnal Profile", font=dict(size=13, color="#2F6B50")),
        xaxis=dict(title="Hour of Day (UTC)", tickmode="linear", dtick=3, gridcolor="#F0F0F0"),
        yaxis=dict(title=f"{label} ({unit})", gridcolor="#F0F0F0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#FAFAFA", paper_bgcolor="white",
        margin=dict(l=50, r=20, t=50, b=40),
        height=300,
    )
    return fig


def _dow_chart(variable: str, profile) -> go.Figure:
    dow    = profile.dow
    colour = _VAR_COLOURS.get(variable, "#3A7F5F")
    meta   = _SENSOR_META.get(variable, {})
    unit   = meta.get("unit", "")
    label  = meta.get("label", variable)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dow.day_names + dow.day_names[::-1],
        y=dow.p75 + dow.p25[::-1],
        fill="toself", fillcolor=f"rgba({_hex_to_rgb(colour)},0.18)",
        line=dict(color="rgba(0,0,0,0)"),
        name="P25–P75",
    ))
    fig.add_trace(go.Scatter(
        x=dow.day_names, y=dow.median,
        mode="lines+markers",
        line=dict(color=colour, width=2.5),
        marker=dict(size=7, color=colour),
        name="Median",
    ))
    fig.update_layout(
        title=dict(text=f"{label} — Day-of-Week Profile", font=dict(size=13, color="#2F6B50")),
        xaxis=dict(title="Day of Week", gridcolor="#F0F0F0"),
        yaxis=dict(title=f"{label} ({unit})", gridcolor="#F0F0F0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#FAFAFA", paper_bgcolor="white",
        margin=dict(l=50, r=20, t=50, b=40),
        height=270,
    )
    return fig


def _distribution_chart(variable: str, profile) -> go.Figure:
    dist   = profile.distribution
    colour = _VAR_COLOURS.get(variable, "#3A7F5F")
    meta   = _SENSOR_META.get(variable, {})
    unit   = meta.get("unit", "")
    label  = meta.get("label", variable)

    pcts = dist.percentiles
    fig = go.Figure()

    # Percentile markers as vertical lines
    marker_pcts = {10: "#9E9E9E", 50: colour, 90: "#E65100", 99: "#D93025"}
    for p, col in marker_pcts.items():
        v = pcts.get(p)
        if v is None:
            continue
        fig.add_vline(
            x=v,
            line=dict(color=col, dash="dash", width=1.5),
            annotation_text=f"P{p}",
            annotation_position="top right",
            annotation_font=dict(size=9, color=col),
        )

    # Distribution as bar chart using percentile buckets
    bucket_edges = [pcts.get(p) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]
                    if pcts.get(p) is not None]
    bucket_labels = [f"P{p}–P{q}" for p, q in zip([1, 5, 10, 25, 50, 75, 90, 95],
                                                    [5, 10, 25, 50, 75, 90, 95, 99])]
    bucket_widths = [b - a for a, b in zip(bucket_edges[:-1], bucket_edges[1:])]
    bucket_heights = [100 / (len(bucket_edges) - 1)] * len(bucket_widths) if bucket_widths else []

    if bucket_widths and bucket_heights:
        centres = [(a + b) / 2 for a, b in zip(bucket_edges[:-1], bucket_edges[1:])]
        fig.add_trace(go.Bar(
            x=centres,
            y=bucket_heights,
            width=bucket_widths,
            marker_color=f"rgba({_hex_to_rgb(colour)},0.55)",
            marker_line_color=colour,
            marker_line_width=0.8,
            name="Distribution",
            text=bucket_labels[:len(centres)],
            textposition="none",
            hovertemplate="%{text}<br>Range: %{width:.2f} {unit}<extra></extra>".replace("{unit}", unit),
        ))

    fig.update_layout(
        title=dict(text=f"{label} — Distribution Profile", font=dict(size=13, color="#2F6B50")),
        xaxis=dict(title=f"{label} ({unit})", gridcolor="#F0F0F0"),
        yaxis=dict(title="Relative Density (%)", gridcolor="#F0F0F0"),
        plot_bgcolor="#FAFAFA", paper_bgcolor="white",
        margin=dict(l=50, r=20, t=50, b=40),
        height=260,
        showlegend=False,
    )
    return fig


def _hex_to_rgb(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


# ── Section 2: Baseline Profiles ───────────────────────────────────────────────

def _render_profiles(baseline: SiteBaseline) -> None:
    st.markdown("### 📈 Baseline Profiles")
    if not baseline.profiles:
        st.info("No sensor profiles available — collect more data to unlock profile analysis.")
        return

    for var, profile in baseline.profiles.items():
        meta  = _SENSOR_META.get(var, {})
        label = meta.get("label", var)
        dist  = profile.distribution

        with st.expander(f"**{label}** — {dist.count:,} readings", expanded=True):
            tab1, tab2, tab3 = st.tabs(["⏰ Diurnal Profile", "📅 Day-of-Week", "📊 Distribution"])

            with tab1:
                st.plotly_chart(_diurnal_chart(var, profile), use_container_width=True)
                st.caption(
                    "Median value (line) and interquartile bands (P25–P75, P10–P90) for each hour of the day. "
                    "All times are UTC. Use this to identify peak-flow hours and expected overnight behaviour."
                )

            with tab2:
                st.plotly_chart(_dow_chart(var, profile), use_container_width=True)
                st.caption(
                    "Day-of-week median and IQR. Significant differences between weekdays and weekends "
                    "indicate catchment-specific usage patterns that should inform alarm scheduling."
                )

            with tab3:
                st.plotly_chart(_distribution_chart(var, profile), use_container_width=True)
                # Key percentile table
                pcts = dist.percentiles
                unit = meta.get("unit", "")
                prec = meta.get("precision", 2)
                pct_data = {
                    "Percentile": ["P5", "P10", "P25", "P50 (Median)", "P75", "P90", "P95", "P99"],
                    f"Value ({unit})": [
                        f"{pcts.get(5, float('nan')):.{prec}f}",
                        f"{pcts.get(10, float('nan')):.{prec}f}",
                        f"{pcts.get(25, float('nan')):.{prec}f}",
                        f"{pcts.get(50, float('nan')):.{prec}f}",
                        f"{pcts.get(75, float('nan')):.{prec}f}",
                        f"{pcts.get(90, float('nan')):.{prec}f}",
                        f"{pcts.get(95, float('nan')):.{prec}f}",
                        f"{pcts.get(99, float('nan')):.{prec}f}",
                    ],
                }
                extra = {
                    "Stat": ["Mean", "Std Dev", "IQR", "Min", "Max"],
                    f"Value ({unit})": [
                        f"{dist.mean:.{prec}f}",
                        f"{dist.std:.{prec}f}",
                        f"{dist.iqr:.{prec}f}",
                        f"{dist.data_min:.{prec}f}",
                        f"{dist.data_max:.{prec}f}",
                    ],
                }
                col_pct, col_extra = st.columns(2)
                with col_pct:
                    st.dataframe(pct_data, use_container_width=True, hide_index=True)
                with col_extra:
                    st.dataframe(extra, use_container_width=True, hide_index=True)


# ── Section 3: Trend Summary ───────────────────────────────────────────────────

def _render_trends(baseline: SiteBaseline) -> None:
    st.markdown("### 📉 Long-Term Trend Summary")
    if not baseline.profiles:
        st.info("No trend data available yet.")
        return

    rows = []
    for var, profile in baseline.profiles.items():
        t    = profile.trend
        meta = _SENSOR_META.get(var, {})
        colour = _TREND_COLOURS.get(t.direction, "#4A4A4A")
        badge = (
            f"<span style='background:{colour}20; color:{colour}; border:1px solid {colour}; "
            f"border-radius:6px; padding:2px 8px; font-size:0.82rem; font-weight:600;'>"
            f"{t.direction_label}</span>"
        )
        rows.append({
            "Variable":   meta.get("label", var),
            "Trend":      badge,
            "Slope":      t.slope_description,
            "R²":         f"{t.r_squared:.3f}",
            "p-value":    f"{t.p_value:.4f}",
            "Significance": "Significant" if t.p_value < 0.05 else "Not significant",
        })

    # Render as HTML table to preserve badge styling
    header_cols = list(rows[0].keys())
    html_rows = ""
    for row in rows:
        cells = "".join(
            f"<td style='padding:8px 12px; border-bottom:1px solid #eee;'>{v}</td>"
            for k, v in row.items()
        )
        html_rows += f"<tr>{cells}</tr>"

    header_html = "".join(
        f"<th style='background:#E8F3EE; color:#2F6B50; padding:8px 12px; "
        f"text-align:left; font-size:0.85rem;'>{c}</th>"
        for c in header_cols
    )

    st.markdown(f"""
    <div style="overflow-x:auto; border-radius:8px; border:1px solid #D9D9D9; margin-bottom:1rem;">
    <table style="width:100%; border-collapse:collapse; font-size:0.88rem; color:#4A4A4A;">
      <thead><tr>{header_html}</tr></thead>
      <tbody>{html_rows}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    st.caption(
        "Trend is computed via ordinary least-squares linear regression over the full dataset. "
        "R² indicates how well the linear model fits; p-value < 0.05 indicates a statistically "
        "significant trend. A significant upward depth trend may indicate sewer blockage or "
        "infrastructure change; a significant downward velocity trend may indicate sediment build-up."
    )


# ── Section 4: Alarm Recommendations ──────────────────────────────────────────

def _render_recommendations(
    device_id: str,
    baseline: SiteBaseline,
    selected_sensitivity: str,
) -> None:
    st.markdown("### 🔔 Alarm Level Recommendations")

    # Load persisted recommendations from DB
    db_recs = db.get_alarm_recommendations(device_id, sensitivity=selected_sensitivity)

    if not db_recs:
        st.info(
            "No alarm recommendations are stored for this device. "
            "Click **Compute Baselines** to generate recommendations."
        )
        return

    current_user = get_current_user()
    username = current_user.get("username", "user") if current_user else "user"
    admin = is_admin()

    accepted_count = sum(1 for r in db_recs if r.get("status") == "accepted")
    total_count    = len(db_recs)

    # Explanation card
    st.markdown(f"""
    <div style="background:#E8F3EE; border-left:4px solid #3A7F5F; border-radius:8px;
                padding:12px 16px; margin-bottom:1rem; font-size:0.88rem; color:#4A4A4A;">
        <strong>Methodology:</strong> Alarm thresholds are derived from statistical analysis
        of <strong>{baseline.readings_used:,} readings</strong> spanning
        <strong>{baseline.days_covered:.0f} days</strong>. Thresholds are calculated from
        percentiles and IQR of the observed distribution.
        Estimated false-positive rates indicate the approximate proportion of normal readings
        that would exceed each threshold under stable operating conditions.
        <br/><br/>
        <strong>Note:</strong> These are data-driven recommendations only. Always validate
        against operational knowledge and site-specific requirements before implementation.
    </div>
    """, unsafe_allow_html=True)

    # Summary badge
    badge_colour = "#4CAF50" if accepted_count > 0 else "#6b7280"
    st.markdown(
        f"<span style='background:{badge_colour}20; color:{badge_colour}; border:1px solid {badge_colour}; "
        f"border-radius:20px; padding:4px 14px; font-size:0.85rem; font-weight:600;'>"
        f"✓ {accepted_count} of {total_count} recommendations accepted</span>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Group by variable for cleaner display
    var_order = ["depth_mm", "velocity_mps", "flow_lps"]
    grouped: Dict[str, List] = {}
    for rec in db_recs:
        grouped.setdefault(rec["variable"], []).append(rec)

    for var in var_order:
        recs_for_var = grouped.get(var)
        if not recs_for_var:
            continue

        meta  = _SENSOR_META.get(var, {})
        label = meta.get("label", var)
        unit  = meta.get("unit", "")
        prec  = meta.get("precision", 2)
        colour = _VAR_COLOURS.get(var, "#3A7F5F")

        st.markdown(
            f"<h4 style='color:{colour}; margin:1.2rem 0 0.4rem; font-size:1rem;'>"
            f"{'💧' if var == 'depth_mm' else '💨' if var == 'velocity_mps' else '🌊'} {label}</h4>",
            unsafe_allow_html=True,
        )

        # Sort: above first, then by level severity
        level_order = {"low_warning": 0, "high_warning": 1, "critical": 2}
        dir_order   = {"above": 0, "below": 1}
        recs_sorted = sorted(
            recs_for_var,
            key=lambda r: (dir_order.get(r["direction"], 9), level_order.get(r["level_name"], 9)),
        )

        for rec in recs_sorted:
            rec_id     = rec["id"]
            status     = rec.get("status", "pending")
            level_col  = _LEVEL_COLOURS.get(rec["level_name"], "#4A4A4A")
            val_to_show = rec.get("accepted_value") or rec["recommended_value"]
            dir_arrow  = "▲" if rec["direction"] == "above" else "▼"

            # Card background based on status
            if status == "accepted":
                card_bg = "#E8F5E9"
                card_border = "#4CAF50"
                status_badge = "✓ Accepted"
                status_colour = "#4CAF50"
            elif status == "dismissed":
                card_bg = "#F5F5F5"
                card_border = "#9E9E9E"
                status_badge = "✗ Dismissed"
                status_colour = "#9E9E9E"
            else:
                card_bg = "#FFFFFF"
                card_border = level_col
                status_badge = "Pending Review"
                status_colour = level_col

            accepted_note = ""
            if status == "accepted" and rec.get("accepted_value") is not None:
                accepted_note = (
                    f" (adjusted to <strong>{rec['accepted_value']:.{prec}f} {unit}</strong>)"
                )

            with st.container():
                st.markdown(f"""
                <div style="background:{card_bg}; border:1.5px solid {card_border}; border-radius:8px;
                            padding:12px 16px; margin-bottom:0.6rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-weight:700; color:{level_col}; font-size:0.95rem;">
                                {dir_arrow} {_LEVEL_LABELS.get(rec['level_name'], rec['level_name'])}
                                &nbsp;{rec['direction'].title()}
                            </span>
                            &nbsp;·&nbsp;
                            <span style="font-size:1.05rem; font-weight:700; color:#4A4A4A;">
                                {rec['recommended_value']:.{prec}f} {unit}{accepted_note}
                            </span>
                        </div>
                        <span style="background:{status_colour}20; color:{status_colour};
                                     border:1px solid {status_colour}; border-radius:20px;
                                     padding:2px 10px; font-size:0.78rem; font-weight:600;">
                            {status_badge}
                        </span>
                    </div>
                    <div style="font-size:0.81rem; color:#6b7280; margin-top:5px;">
                        {rec.get('basis', '')}
                    </div>
                    <div style="font-size:0.79rem; color:#9E9E9E; margin-top:3px;">
                        Est. false-positive rate: ≈{rec.get('estimated_fp_pct', 0):.0f}%
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if admin and status == "pending":
                    col_val, col_accept, col_dismiss = st.columns([2, 1, 1])
                    with col_val:
                        override_val = st.number_input(
                            f"Override value ({unit})",
                            value=float(rec["recommended_value"]),
                            step=1.0 if prec == 0 else 10 ** (-prec),
                            format=f"%.{prec}f",
                            key=f"override_{rec_id}",
                            label_visibility="collapsed",
                        )
                    with col_accept:
                        if st.button("✓ Accept", key=f"accept_{rec_id}", type="primary"):
                            db.update_alarm_recommendation_status(
                                rec_id=rec_id,
                                status="accepted",
                                reviewed_by=username,
                                accepted_value=float(override_val),
                            )
                            st.rerun()
                    with col_dismiss:
                        if st.button("✗ Dismiss", key=f"dismiss_{rec_id}"):
                            db.update_alarm_recommendation_status(
                                rec_id=rec_id,
                                status="dismissed",
                                reviewed_by=username,
                            )
                            st.rerun()

                elif admin and status in ("accepted", "dismissed"):
                    if st.button("↩ Reset to Pending", key=f"reset_{rec_id}"):
                        db.update_alarm_recommendation_status(
                            rec_id=rec_id,
                            status="pending",
                            reviewed_by=username,
                        )
                        st.rerun()


# ── Main page assembly ─────────────────────────────────────────────────────────

# Load measurements and cached baseline
with st.spinner("Loading site data…"):
    df_all = _load_all_measurements(selected_device_id)

cached = _cached_baseline(selected_device_id)

# Controls row
with col_action:
    if st.button("🔄 Compute Baselines", type="primary", use_container_width=True):
        if df_all.empty:
            st.error("No data found for this device.")
        else:
            with st.spinner("Running baseline analysis…"):
                cached = _run_analysis(selected_device_id, df_all)
            st.success("Baseline analysis complete.")
            st.rerun()

# ── Section 1: Readiness ───────────────────────────────────────────────────────
_render_readiness(cached, df_all)

st.divider()

if cached is None or not cached.sufficiency.has_basic:
    st.info(
        "🔍 Not enough data has been collected to run a meaningful analysis yet. "
        "Once you have at least **7 days** and **5,000 readings**, click "
        "**Compute Baselines** to unlock profile charts and alarm recommendations."
    )
    st.stop()

# ── Sensitivity selector ───────────────────────────────────────────────────────
sensitivity_options = list(_SENSITIVITY_LABELS.keys())
sensitivity_labels  = list(_SENSITIVITY_LABELS.values())
selected_sens_label = st.radio(
    "Alarm Sensitivity Level",
    options=sensitivity_labels,
    index=1,  # default: Standard
    horizontal=True,
    key="intel_sensitivity",
    help=(
        "**Conservative** — higher thresholds, fewer false alarms.  \n"
        "**Standard** — balanced thresholds based on P90–P99 and IQR.  \n"
        "**Sensitive** — lower thresholds, earlier warning, more false alarms."
    ),
)
selected_sensitivity = sensitivity_options[sensitivity_labels.index(selected_sens_label)]

st.divider()

# ── Section 2: Profiles ────────────────────────────────────────────────────────
_render_profiles(cached)

st.divider()

# ── Section 3: Trends ─────────────────────────────────────────────────────────
_render_trends(cached)

st.divider()

# ── Section 4: Alarm Recommendations ──────────────────────────────────────────
_render_recommendations(selected_device_id, cached, selected_sensitivity)

st.divider()

# ── Download PDF ───────────────────────────────────────────────────────────────
st.markdown("### 📄 Download Alarm Advisory Report")

db_recs_for_pdf = db.get_alarm_recommendations(selected_device_id, sensitivity=selected_sensitivity)
recs_for_pdf: List[AlarmRecommendation] = []
for r in db_recs_for_pdf:
    recs_for_pdf.append(AlarmRecommendation(
        variable=r["variable"],
        variable_label=_SENSOR_META.get(r["variable"], {}).get("label", r["variable"]),
        direction=r["direction"],
        level_name=r["level_name"],
        level_label=_LEVEL_LABELS.get(r["level_name"], r["level_name"]),
        recommended_value=r.get("accepted_value") or r["recommended_value"],
        unit=_SENSOR_META.get(r["variable"], {}).get("unit", ""),
        sensitivity=r["sensitivity"],
        sensitivity_label=_SENSITIVITY_LABELS.get(r["sensitivity"], r["sensitivity"]),
        basis=r.get("basis", ""),
        estimated_fp_pct=r.get("estimated_fp_pct") or 0.0,
    ))

if recs_for_pdf:
    pdf_bytes = build_intelligence_pdf(
        device_name=selected_device_name,
        baseline=cached,
        recommendations=recs_for_pdf,
        sensitivity_filter=selected_sensitivity,
    )
    if pdf_bytes:
        st.download_button(
            label="⬇️ Download Alarm Advisory PDF",
            data=pdf_bytes,
            file_name=(
                f"eflow_alarm_advisory_{selected_device_id}_{selected_sensitivity}_"
                f"{datetime.now().strftime('%Y%m%d')}.pdf"
            ),
            mime="application/pdf",
            type="primary",
        )
    else:
        st.info("PDF generation requires reportlab to be installed.")
else:
    st.info("Run baseline computation first to enable PDF download.")
