from __future__ import annotations

import html
import io
import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from anomaly import AnomalyReport

# ── Module-level constants ─────────────────────────────────────────────────

# Metric formatting: keys map to format-string templates used in tables.
_METRIC_FORMATS: Dict[str, str] = {
    "count":          "{:.0f}",
    "volume_liters":  "{:,.0f} L",
    "volume_m3":      "{:,.3f} m³",
}


def _strip_html(text: str) -> str:
    """Return plain text with all HTML tags removed (safe for PDF output)."""
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: List[str] = []

        def handle_data(self, data: str) -> None:
            self._parts.append(data)

        def get_text(self) -> str:
            return "".join(self._parts)

    stripper = _Stripper()
    stripper.feed(text)
    return stripper.get_text()

# For static image export of plotly charts
# kaleido is optional; if unavailable, images will be skipped
try:
    import kaleido  # noqa: F401
    _KALEIDO_AVAILABLE = True
except Exception:
    _KALEIDO_AVAILABLE = False

# For PDF generation
try:
    from weasyprint import HTML, CSS
    _WEASYPRINT_AVAILABLE = True
except Exception:
    _WEASYPRINT_AVAILABLE = False

# Pure-Python PDF fallback (no system-level dependencies)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.enums import TA_CENTER
    _REPORTLAB_AVAILABLE = True
except Exception:
    _REPORTLAB_AVAILABLE = False


@dataclass
class ReportSelections:
    variables: List[str]  # e.g., ["depth_mm", "velocity_mps", "flow_lps"]
    calculations: List[str]  # e.g., ["mean","max","min","std","p50","p95","volume"]
    device_name: str
    time_window_hours: int
    report_type: str = "custom"        # daily | weekly | monthly | custom
    site_id: str = ""
    location: str = ""
    anomaly_report: Optional[AnomalyReport] = field(default=None)
    # Content toggles
    include_stats_table: bool = True
    include_charts: bool = True
    include_volume_breakdown: bool = False
    volume_breakdown_interval: str = "daily"   # "daily" | "am_pm" | "hourly"
    # Metadata
    report_timezone: str = "Australia/Brisbane"
    custom_title: str = ""


def compute_calculations(df: pd.DataFrame, selections: ReportSelections) -> Dict[str, Dict[str, float]]:
    """Compute selected calculations per variable.
    Supported calculations:
    - mean, max, min, std, median (p50), p95
    - volume (for flow_lps only): integrate L/s over time to liters and m^3
    - count, range
    """
    results: Dict[str, Dict[str, float]] = {}
    if df.empty:
        return results

    # Ensure timestamp is datetime and sorted ascending
    dfx = df.copy()
    dfx["timestamp"] = pd.to_datetime(dfx["timestamp"], utc=True)  # normalise to UTC
    dfx = dfx.sort_values("timestamp")

    for var in selections.variables:
        if var not in dfx.columns:
            continue
        series = pd.to_numeric(dfx[var], errors="coerce")
        series = series.dropna()
        if series.empty:
            continue

        stats: Dict[str, float] = {}
        if "mean" in selections.calculations:
            stats["mean"] = float(series.mean())
        if "max" in selections.calculations:
            stats["max"] = float(series.max())
        if "min" in selections.calculations:
            stats["min"] = float(series.min())
        if "std" in selections.calculations:
            stats["std"] = float(series.std(ddof=1))
        if "p50" in selections.calculations or "median" in selections.calculations:
            stats["p50"] = float(series.quantile(0.5))
        if "p95" in selections.calculations:
            stats["p95"] = float(series.quantile(0.95))
        if "range" in selections.calculations:
            stats["range"] = float(series.max() - series.min())
        if "count" in selections.calculations:
            stats["count"] = float(series.shape[0])

        # Volume calculation only applies to flow_lps
        if var == "flow_lps" and "volume" in selections.calculations:
            # Average flow rate (L/s) × elapsed seconds in the period = total volume (L)
            f = pd.to_numeric(dfx["flow_lps"], errors="coerce").dropna()
            t = pd.to_datetime(dfx["timestamp"], utc=True)
            if f.shape[0] > 1:
                avg_flow_lps = float(f.mean())
                elapsed_seconds = (t.max() - t.min()).total_seconds()
                liters = avg_flow_lps * elapsed_seconds
                m3 = liters / 1000.0
                stats["volume_liters"] = liters
                stats["volume_m3"] = m3

        results[var] = stats

    return results


def compute_volume_breakdown(
    df: pd.DataFrame,
    interval: str = "daily",
    tz: str = "Australia/Brisbane",
) -> List[Dict]:
    """Compute flow volume totals broken down by time period.

    Parameters
    ----------
    df       : DataFrame with 'timestamp' and 'flow_lps' columns.
    interval : "daily" | "am_pm" | "hourly"
    tz       : IANA timezone used for period grouping.

    Returns
    -------
    List of dicts with keys:
        period_label, is_subtotal, is_grand_total,
        volume_l, volume_m3, volume_ml,
        mean_flow_lps, peak_flow_lps, reading_count
    """
    if df is None or df.empty or "flow_lps" not in df.columns:
        return []

    dfx = df.copy()
    dfx["_ts"] = pd.to_datetime(dfx["timestamp"], utc=True)
    dfx["_flow"] = pd.to_numeric(dfx["flow_lps"], errors="coerce")
    dfx = dfx.dropna(subset=["_flow", "_ts"]).sort_values("_ts")
    if dfx.empty:
        return []

    local_ts = dfx["_ts"].dt.tz_convert(tz)
    dfx["_local_date"] = local_ts.dt.date
    dfx["_local_hour"] = local_ts.dt.hour

    def _integrate(sub: pd.DataFrame) -> Optional[Dict]:
        flow_vals = sub["_flow"].values
        ts_epoch = sub["_ts"].astype("int64").values / 1e9
        if len(flow_vals) < 1:
            return None
        vol_l = max(0.0, float(np.trapz(flow_vals, ts_epoch)))
        return {
            "volume_l":       vol_l,
            "volume_m3":      vol_l / 1_000.0,
            "volume_ml":      vol_l / 1_000_000.0,
            "mean_flow_lps":  float(flow_vals.mean()),
            "peak_flow_lps":  float(flow_vals.max()),
            "reading_count":  int(len(flow_vals)),
        }

    rows: List[Dict] = []

    if interval == "hourly":
        dfx["_group"] = local_ts.dt.strftime("%Y-%m-%d_%H")
        for group_key in sorted(dfx["_group"].unique()):
            sub = dfx[dfx["_group"] == group_key]
            r = _integrate(sub)
            if r is None:
                continue
            dt_part, h_part = group_key.rsplit("_", 1)
            label = f"{pd.Timestamp(dt_part).strftime('%d/%m/%Y')} {h_part}:00–{h_part}:59"
            rows.append({"period_label": label, "is_subtotal": False, "is_grand_total": False, **r})
        # Grand total
        if rows:
            total_l = sum(r["volume_l"] for r in rows)
            all_r = _integrate(dfx)
            if all_r:
                rows.append({
                    "period_label": "Period Total",
                    "is_subtotal": False, "is_grand_total": True,
                    "volume_l": total_l, "volume_m3": total_l / 1_000.0,
                    "volume_ml": total_l / 1_000_000.0,
                    "mean_flow_lps": all_r["mean_flow_lps"],
                    "peak_flow_lps": all_r["peak_flow_lps"],
                    "reading_count": all_r["reading_count"],
                })

    elif interval == "am_pm":
        dates = sorted(dfx["_local_date"].unique())
        for date in dates:
            day_df = dfx[dfx["_local_date"] == date]
            date_str = date.strftime("%d/%m/%Y")
            half_vols: List[float] = []
            for is_am in [True, False]:
                half_label = "AM  (00:00–11:59)" if is_am else "PM  (12:00–23:59)"
                half_df = day_df[day_df["_local_hour"] < 12] if is_am else day_df[day_df["_local_hour"] >= 12]
                r = _integrate(half_df)
                if r is None or r["reading_count"] == 0:
                    continue
                rows.append({
                    "period_label": f"{date_str}  {half_label}",
                    "is_subtotal": False, "is_grand_total": False, **r,
                })
                half_vols.append(r["volume_l"])
            # Daily subtotal
            if half_vols:
                day_r = _integrate(day_df)
                day_total_l = sum(half_vols)
                if day_r:
                    rows.append({
                        "period_label": f"{date_str}  Daily Total",
                        "is_subtotal": True, "is_grand_total": False,
                        "volume_l":      day_total_l,
                        "volume_m3":     day_total_l / 1_000.0,
                        "volume_ml":     day_total_l / 1_000_000.0,
                        "mean_flow_lps": day_r["mean_flow_lps"],
                        "peak_flow_lps": day_r["peak_flow_lps"],
                        "reading_count": day_r["reading_count"],
                    })
        # Grand total from all half-day rows
        half_rows = [r for r in rows if not r["is_subtotal"] and not r["is_grand_total"]]
        if half_rows:
            grand_l = sum(r["volume_l"] for r in half_rows)
            all_r = _integrate(dfx)
            if all_r:
                rows.append({
                    "period_label": "Period Total",
                    "is_subtotal": False, "is_grand_total": True,
                    "volume_l":      grand_l,
                    "volume_m3":     grand_l / 1_000.0,
                    "volume_ml":     grand_l / 1_000_000.0,
                    "mean_flow_lps": all_r["mean_flow_lps"],
                    "peak_flow_lps": all_r["peak_flow_lps"],
                    "reading_count": all_r["reading_count"],
                })

    else:  # daily
        dfx["_group"] = local_ts.dt.strftime("%Y-%m-%d")
        for group_key in sorted(dfx["_group"].unique()):
            sub = dfx[dfx["_group"] == group_key]
            r = _integrate(sub)
            if r is None:
                continue
            label = pd.Timestamp(group_key).strftime("%d/%m/%Y")
            rows.append({"period_label": label, "is_subtotal": False, "is_grand_total": False, **r})
        if rows:
            total_l = sum(r["volume_l"] for r in rows)
            all_r = _integrate(dfx)
            if all_r:
                rows.append({
                    "period_label": "Period Total",
                    "is_subtotal": False, "is_grand_total": True,
                    "volume_l":      total_l,
                    "volume_m3":     total_l / 1_000.0,
                    "volume_ml":     total_l / 1_000_000.0,
                    "mean_flow_lps": all_r["mean_flow_lps"],
                    "peak_flow_lps": all_r["peak_flow_lps"],
                    "reading_count": all_r["reading_count"],
                })

    return rows


# Human-readable descriptions for each anomaly type used in the report narrative.
_ANOMALY_DESCRIPTIONS = {
    "flatline":       "sensor flatline event(s) — consecutive identical readings "
                      "(may reflect genuinely stable flow; verify with field records)",
    "spike":          "rapid rate-of-change alert(s) — abrupt transitions between "
                      "consecutive readings that may warrant operator review",
    "dropout":        "data gap(s) — period(s) where no measurements were recorded, "
                      "likely due to a temporary communications interruption",
    "out_of_range":   "out-of-range reading(s) — values outside physically plausible "
                      "instrument bounds; recommend inspection",
    "velocity_depth": "hydraulic inconsistenc(ies) — velocity unusually high relative "
                      "to the measured water depth",
    "zscore":         "statistical outlier(s) — readings significantly outside the "
                      "rolling measurement baseline",
}


def _quality_narrative(ar: "AnomalyReport", total_rows: int, period_hours: float) -> str:
    """Return a plain-English data quality narrative for inclusion in reports."""
    hours_str = f"{period_hours:.1f} hours" if period_hours < 48 else f"{period_hours / 24:.1f} days"

    if not ar.flags:
        return (
            f"The automated quality analysis reviewed {total_rows:,} measurements spanning "
            f"{hours_str}. No data quality events were identified. The monitoring equipment "
            f"is operating within expected parameters and the collected data is suitable for "
            f"operational decision-making and regulatory reporting."
        )

    label_map = {"High": "High", "Medium": "Medium", "Low": "Low"}
    qual = label_map.get(ar.quality_label, ar.quality_label)

    opening = (
        f"The automated quality analysis reviewed {total_rows:,} measurements spanning "
        f"{hours_str}. Overall data quality is assessed as <strong>{qual}</strong> "
        f"(confidence score {ar.confidence_score:.0f}/100). "
    )

    findings: List[str] = []
    type_counts = [
        (ar.flatline_count,       "flatline"),
        (ar.spike_count,          "spike"),
        (ar.dropout_count,        "dropout"),
        (ar.out_of_range_count,   "out_of_range"),
        (ar.velocity_depth_count, "velocity_depth"),
        (ar.zscore_count,         "zscore"),
    ]
    for count, atype in type_counts:
        if count:
            findings.append(f"{count} {_ANOMALY_DESCRIPTIONS[atype]}")

    if findings:
        closing = "Events identified for review: " + "; ".join(findings) + ". "
    else:
        closing = "No significant data quality concerns were identified. "

    if ar.quality_label == "High":
        advice = (
            "The data is suitable for operational reporting. Flagged events are provided "
            "for information only and do not materially affect data integrity."
        )
    elif ar.quality_label == "Medium":
        advice = (
            "The data is suitable for general operational use. The flagged periods should "
            "be reviewed before submitting data for regulatory compliance."
        )
    else:
        advice = (
            "The flagged data should be carefully reviewed before use in regulatory "
            "submissions or formal engineering assessments."
        )

    return opening + closing + advice


def create_charts(df: pd.DataFrame, selections: ReportSelections) -> Dict[str, go.Figure]:
    """Create time-series charts for selected variables with brand styling."""
    charts: Dict[str, go.Figure] = {}
    if df.empty:
        return charts
    dfx = df.copy()
    dfx["timestamp"] = pd.to_datetime(dfx["timestamp"], utc=True)
    dfx = dfx.sort_values("timestamp")

    _COLOURS = {
        "depth_mm":     "#3A7F5F",
        "velocity_mps": "#2A9D8F",
        "flow_lps":     "#1D4E89",
    }
    _YLABELS = {
        "depth_mm":     "Water Depth (mm)",
        "velocity_mps": "Flow Velocity (m/s)",
        "flow_lps":     "Flow Rate (L/s)",
    }
    _TITLES = {
        "depth_mm":     "Water Depth",
        "velocity_mps": "Flow Velocity",
        "flow_lps":     "Flow Rate",
    }

    for var in selections.variables:
        if var not in dfx.columns:
            continue
        colour = _COLOURS.get(var, "#3A7F5F")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dfx["timestamp"],
            y=pd.to_numeric(dfx[var], errors="coerce"),
            mode="lines",
            line=dict(color=colour, width=1.5),
            name=_TITLES.get(var, var),
        ))
        fig.update_layout(
            title=dict(
                text=f"{selections.device_name} — {_TITLES.get(var, var)}",
                font=dict(size=13, color="#4A4A4A"),
            ),
            xaxis=dict(title="Time", gridcolor="#E5E7EB"),
            yaxis=dict(title=_YLABELS.get(var, var), gridcolor="#E5E7EB"),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            margin=dict(l=20, r=20, t=40, b=20),
            height=320,
            font=dict(family="Helvetica, Arial, sans-serif", color="#4A4A4A"),
        )
        charts[var] = fig
    return charts


def fig_to_base64_png(fig: go.Figure) -> Optional[str]:
    """Render plotly figure to base64 PNG string using kaleido."""
    if not _KALEIDO_AVAILABLE:
        return None
    try:
        buf = fig.to_image(format="png", scale=2)
        b64 = base64.b64encode(buf).decode("ascii")
        return b64
    except Exception:
        return None


def build_html_report(device_name: str,
                      df: pd.DataFrame,
                      selections: ReportSelections,
                      calculations: Dict[str, Dict[str, float]],
                      charts: Dict[str, go.Figure],
                      logo_path: Optional[str] = None,
                      volume_breakdown: Optional[List[Dict]] = None) -> str:
    """Generate an HTML report string with embedded charts, metrics, AI insights, and optional logo."""
    # Header and metadata
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_type_label = {
        "daily": "Daily Summary",
        "weekly": "Weekly Summary",
        "monthly": "Monthly Summary",
        "custom": "Custom Report",
    }.get(selections.report_type, "Technical Report")

    display_title = selections.custom_title or f"e-flow {report_type_label}"

    # Period label
    if not df.empty:
        ts = pd.to_datetime(df["timestamp"], utc=True)
        period_start = ts.min().strftime("%Y-%m-%d %H:%M")
        period_end = ts.max().strftime("%Y-%m-%d %H:%M")
        period_label = f"{period_start} → {period_end}"
        period_hours = (ts.max() - ts.min()).total_seconds() / 3600.0
    else:
        period_label = f"Last {selections.time_window_hours} hours"
        period_hours = float(selections.time_window_hours)

    # Logo HTML (if provided) — supports PNG and SVG
    logo_html = ""
    if logo_path and Path(logo_path).exists():
        try:
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            suffix = Path(logo_path).suffix.lower()
            mime = "image/svg+xml" if suffix == ".svg" else "image/png"
            logo_html = f"<img src='data:{mime};base64,{logo_b64}' style='height:60px;margin-bottom:20px;'/>"
        except Exception:
            pass

    # ── AI / Data Quality section ────────────────────────────────────────────
    ar: Optional[AnomalyReport] = selections.anomaly_report
    if ar is not None:
        qual_color = {"High": "#4CAF50", "Medium": "#F4B400", "Low": "#D93025"}.get(ar.quality_label, "#333")
        qual_bg = {"High": "#E8F5E9", "Medium": "#FFF8E1", "Low": "#FDECEA"}.get(ar.quality_label, "#f9fafb")
        narrative = _quality_narrative(ar, total_rows=len(df), period_hours=period_hours)

        # Only list anomaly types that actually occurred
        type_rows = ""
        type_map = [
            ("Sensor Flatline Events", ar.flatline_count),
            ("Rapid Rate-of-Change Alerts", ar.spike_count),
            ("Data Gaps", ar.dropout_count),
            ("Out-of-Range Readings", ar.out_of_range_count),
            ("Hydraulic Inconsistencies", ar.velocity_depth_count),
            ("Statistical Outliers", ar.zscore_count),
        ]
        for label, count in type_map:
            if count:
                type_rows += f"<tr><td>{label}</td><td>{count}</td></tr>"

        type_table = (
            f"<table><thead><tr><th>Event Type</th><th>Count</th></tr></thead>"
            f"<tbody>{type_rows}</tbody></table>"
        ) if type_rows else ""

        ai_html = f"""
        <div class='section card' style='border-left: 4px solid {qual_color}; background: {qual_bg};'>
          <h2>Data Quality Assessment</h2>
          <p style='margin-bottom:10px;'>{narrative}</p>
          <div style='display:flex;gap:24px;margin-bottom:10px;'>
            <div>
              <span style='font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;'>Quality Rating</span><br/>
              <span style='color:{qual_color};font-weight:700;font-size:1.2em;'>{ar.quality_label}</span>
            </div>
            <div>
              <span style='font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;'>Confidence Score</span><br/>
              <span style='font-weight:700;font-size:1.2em;'>{ar.confidence_score:.1f} / 100</span>
            </div>
            <div>
              <span style='font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;'>Readings Reviewed</span><br/>
              <span style='font-weight:700;font-size:1.2em;'>{len(df):,}</span>
            </div>
            <div>
              <span style='font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;'>Events Identified</span><br/>
              <span style='font-weight:700;font-size:1.2em;'>{len(ar.flags)}</span>
            </div>
          </div>
          {type_table}
        </div>
        """
    else:
        ai_html = ""

    # ── Volume breakdown section ─────────────────────────────────────────────
    vol_html = ""
    if selections.include_volume_breakdown and volume_breakdown:
        interval_labels = {
            "daily": "Daily",
            "am_pm": "AM / PM &amp; Daily",
            "hourly": "Hourly",
        }
        interval_label = interval_labels.get(selections.volume_breakdown_interval, "")
        vol_rows_html = ""
        for row in volume_breakdown:
            if row.get("is_grand_total"):
                style = "font-weight:700; background:#E8F3EE;"
            elif row.get("is_subtotal"):
                style = "font-weight:600; background:#F4F5F4;"
            else:
                style = ""
            vol_rows_html += (
                f"<tr style='{style}'>"
                f"<td style='text-align:left'>{html.escape(row['period_label'])}</td>"
                f"<td>{row['volume_m3']:,.1f}</td>"
                f"<td>{row['volume_ml']:.4f}</td>"
                f"<td>{row['mean_flow_lps']:.2f}</td>"
                f"<td>{row['peak_flow_lps']:.2f}</td>"
                f"<td>{row['reading_count']:,}</td>"
                f"</tr>"
            )
        vol_html = f"""
        <div class='section card'>
          <h2>Flow Volume Breakdown — {interval_label}</h2>
          <table>
            <thead>
              <tr>
                <th style='text-align:left'>Period</th>
                <th>Volume (m³)</th>
                <th>Volume (ML)</th>
                <th>Mean Flow (L/s)</th>
                <th>Peak Flow (L/s)</th>
                <th>Readings</th>
              </tr>
            </thead>
            <tbody>{vol_rows_html}</tbody>
          </table>
          <p class='small'>1 m³ = 1 kL &nbsp;·&nbsp; 1 ML = 1,000 m³ = 1,000,000 L &nbsp;·&nbsp;
          Volumes computed by trapezoidal integration of flow rate over time.</p>
        </div>
        """

    # ── Metrics (Summary Statistics) section ────────────────────────────────
    _VAR_LABELS = {
        "depth_mm":     "Water Depth (mm)",
        "velocity_mps": "Flow Velocity (m/s)",
        "flow_lps":     "Flow Rate (L/s)",
    }
    _METRIC_LABELS = {
        "mean": "Mean", "max": "Maximum", "min": "Minimum",
        "std": "Std Deviation", "p50": "Median (P50)", "p95": "95th Percentile (P95)",
        "range": "Range", "count": "Total Readings",
        "volume_liters": "Total Volume (L)", "volume_m3": "Total Volume (m³)",
    }

    metrics_html = ""
    if selections.include_stats_table and calculations:
        metrics_html = "<div class='section card'><h2>Summary Statistics</h2>"
        for var, stats in calculations.items():
            if not stats:
                continue
            metrics_html += f"<h3>{_VAR_LABELS.get(var, var)}</h3>"
            metrics_html += "<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
            for k, v in stats.items():
                fmt = _METRIC_FORMATS.get(k, "{:.3f}")
                formatted = fmt.format(v)
                metrics_html += f"<tr><td>{_METRIC_LABELS.get(k, k)}</td><td>{formatted}</td></tr>"
            metrics_html += "</tbody></table>"
        metrics_html += "</div>"

    # ── Charts section ───────────────────────────────────────────────────────
    charts_html = ""
    if selections.include_charts and charts:
        charts_html = "<div class='section card'><h2>Time-Series Charts</h2>"
        for var, fig in charts.items():
            b64 = fig_to_base64_png(fig)
            if b64:
                charts_html += (
                    f"<h3>{_VAR_LABELS.get(var, var)}</h3>"
                    f"<img src='data:image/png;base64,{b64}' "
                    f"style='max-width:100%;height:auto;border:1px solid #eee;border-radius:6px;'/>"
                )
            else:
                charts_html += (
                    f"<h3>{_VAR_LABELS.get(var, var)}</h3>"
                    + fig.to_html(include_plotlyjs="cdn", full_html=False)
                )
        charts_html += "</div>"

    intro = f"""
    <html>
      <head>
        <meta charset='utf-8'/>
        <title>{html.escape(display_title)} — {html.escape(device_name)}</title>
        <style>
          body {{ font-family: -apple-system, Segoe UI, Roboto, Inter, sans-serif; color: #4A4A4A; margin: 40px; background: #F4F5F4; }}
          h1, h2, h3 {{ font-weight: 600; color: #4A4A4A; }}
          h1 {{ margin-top: 0; color: #3A7F5F; }}
          h2 {{ color: #2F6B50; }}
          h3 {{ color: #3A7F5F; font-size: 1em; margin-top: 12px; }}
          .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 30px; border-bottom: 3px solid #3A7F5F; padding-bottom: 20px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(58,127,95,0.08); }}
          .header-left {{ display: flex; align-items: center; gap: 20px; }}
          .section {{ margin: 24px 0; }}
          .card {{ border: 1px solid #D9D9D9; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #ffffff; box-shadow: 0 1px 4px rgba(58,127,95,0.05); }}
          table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
          th, td {{ border: 1px solid #D9D9D9; padding: 10px; text-align: right; }}
          th {{ background: #E8F3EE; text-align: left; font-weight: 600; color: #2F6B50; }}
          td:first-child {{ text-align: left; }}
          .small {{ color: #6b7280; font-size: 12px; margin-top: 8px; }}
          .footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #D9D9D9; font-size: 11px; color: #9ca3af; text-align: center; }}
        </style>
      </head>
      <body>
        <div class='header'>
          <div class='header-left'>
            {logo_html}
            <div>
              <h1>{html.escape(display_title)}</h1>
              <div class='small'>Generated: {generated_at}</div>
            </div>
          </div>
        </div>

        <div class='section card'>
          <h2>Site Information</h2>
          <table>
            <thead><tr><th>Field</th><th>Detail</th></tr></thead>
            <tbody>
              <tr><td>Station</td><td>{html.escape(device_name)}</td></tr>
              {'<tr><td>Site ID</td><td>' + html.escape(selections.site_id) + '</td></tr>' if selections.site_id else ''}
              {'<tr><td>Location</td><td>' + html.escape(selections.location) + '</td></tr>' if selections.location else ''}
              <tr><td>Monitoring Period</td><td>{html.escape(period_label)}</td></tr>
              <tr><td>Variables Analysed</td><td>{html.escape(', '.join(_VAR_LABELS.get(v, v) for v in selections.variables))}</td></tr>
              <tr><td>Total Readings</td><td>{len(df):,}</td></tr>
            </tbody>
          </table>
        </div>

        {ai_html}
        {vol_html}
        {metrics_html}
        {charts_html}

        <div class='footer'>e-flow™ by EDS — Hydrological Intelligence Platform</div>
      </body>
    </html>
    """
    return intro


def _build_pdf_reportlab(device_name: str,
                         df: pd.DataFrame,
                         selections: ReportSelections,
                         calculations: Dict[str, Dict[str, float]],
                         charts: Dict[str, go.Figure],
                         volume_breakdown: Optional[List[Dict]] = None) -> bytes:
    """Generate a professional PDF using reportlab (pure Python, no system deps)."""
    buf = io.BytesIO()

    PAGE_W, PAGE_H = A4
    MARGIN = 20 * mm
    USABLE_W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    # ── Colour palette ───────────────────────────────────────────────────────
    C_GREEN = rl_colors.HexColor('#3A7F5F')
    C_DARK_GREEN = rl_colors.HexColor('#2F6B50')
    C_LIGHT_GREEN = rl_colors.HexColor('#E8F3EE')
    C_SUBTOTAL = rl_colors.HexColor('#F4F5F4')
    C_TOTAL = rl_colors.HexColor('#D6EDE3')
    C_TEXT = rl_colors.HexColor('#4A4A4A')
    C_MUTED = rl_colors.HexColor('#6b7280')
    C_BORDER = rl_colors.HexColor('#D9D9D9')
    C_ROW_ALT = rl_colors.HexColor('#F9FAF9')

    # ── Styles ───────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ReportTitle', parent=base['Title'],
        fontSize=22, textColor=C_GREEN, spaceAfter=4, fontName='Helvetica-Bold',
    )
    h2_style = ParagraphStyle(
        'H2', parent=base['Heading2'],
        fontSize=13, textColor=C_DARK_GREEN,
        spaceBefore=14, spaceAfter=6, fontName='Helvetica-Bold',
    )
    h3_style = ParagraphStyle(
        'H3', parent=base['Heading3'],
        fontSize=10, textColor=C_GREEN,
        spaceBefore=8, spaceAfter=3, fontName='Helvetica-Bold',
    )
    body_style = ParagraphStyle(
        'Body', parent=base['Normal'],
        fontSize=9, textColor=C_TEXT, spaceAfter=4, fontName='Helvetica',
    )
    small_style = ParagraphStyle(
        'Small', parent=base['Normal'],
        fontSize=8, textColor=C_MUTED, fontName='Helvetica',
    )
    footer_style = ParagraphStyle(
        'Footer', parent=small_style, alignment=TA_CENTER, spaceBefore=4,
    )

    def _tbl(data, col_widths=None, extra_styles=None):
        t = Table(data, colWidths=col_widths)
        styles = [
            ('BACKGROUND',    (0, 0), (-1, 0), C_LIGHT_GREEN),
            ('TEXTCOLOR',     (0, 0), (-1, 0), C_DARK_GREEN),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, -1), 9),
            ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_ROW_ALT]),
            ('GRID',          (0, 0), (-1, -1), 0.5, C_BORDER),
            ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN',         (0, 0), (0, -1), 'LEFT'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ]
        if extra_styles:
            styles.extend(extra_styles)
        t.setStyle(TableStyle(styles))
        return t

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    report_type_label = {
        'daily': 'Daily Summary', 'weekly': 'Weekly Summary',
        'monthly': 'Monthly Summary', 'custom': 'Custom Report',
    }.get(selections.report_type, 'Technical Report')

    display_title = selections.custom_title or f'e-flow™ {report_type_label}'
    generated_at = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    story.append(Paragraph(html.escape(display_title), title_style))
    story.append(Paragraph(f'Generated: {generated_at}', small_style))
    story.append(HRFlowable(width='100%', thickness=2, color=C_GREEN, spaceAfter=10))

    # ── Site information ─────────────────────────────────────────────────────
    story.append(Paragraph('Site Information', h2_style))

    VAR_LABELS = {
        'depth_mm': 'Water Depth (mm)',
        'velocity_mps': 'Flow Velocity (m/s)',
        'flow_lps': 'Flow Rate (L/s)',
    }

    if not df.empty:
        ts = pd.to_datetime(df['timestamp'], utc=True)
        period_start = ts.min().strftime('%d/%m/%Y %H:%M')
        period_end   = ts.max().strftime('%d/%m/%Y %H:%M')
        period_label = f'{period_start} → {period_end}'
    else:
        period_label = f'Last {selections.time_window_hours} hours'

    site_rows = [['Field', 'Value'], ['Station', html.escape(device_name)]]
    if selections.site_id:
        site_rows.append(['Site ID', html.escape(selections.site_id)])
    if selections.location:
        site_rows.append(['Location', html.escape(selections.location)])
    site_rows += [
        ['Monitoring Period', period_label],
        ['Variables', ', '.join(VAR_LABELS.get(v, v) for v in selections.variables)],
        ['Total Readings', f'{len(df):,}'],
    ]
    story.append(_tbl(site_rows, col_widths=[55 * mm, USABLE_W - 55 * mm]))
    story.append(Spacer(1, 6 * mm))

    # ── Data Quality Assessment ──────────────────────────────────────────────
    ar: Optional[AnomalyReport] = selections.anomaly_report
    if ar is not None:
        period_hours = (
            (pd.to_datetime(df['timestamp'], utc=True).max() -
             pd.to_datetime(df['timestamp'], utc=True).min()).total_seconds() / 3600.0
            if not df.empty else float(selections.time_window_hours)
        )
        narrative = _quality_narrative(ar, total_rows=len(df), period_hours=period_hours)
        plain_narrative = _strip_html(narrative)

        story.append(Paragraph('Data Quality Assessment', h2_style))
        story.append(Paragraph(plain_narrative, body_style))
        story.append(Spacer(1, 3 * mm))

        ai_rows = [
            ['Metric', 'Value'],
            ['Quality Rating', ar.quality_label],
            ['Confidence Score', f'{ar.confidence_score:.1f} / 100'],
            ['Events Identified', str(len(ar.flags))],
        ]
        type_map = [
            ('Sensor Flatline Events', ar.flatline_count),
            ('Rapid Rate-of-Change Alerts', ar.spike_count),
            ('Data Gaps', ar.dropout_count),
            ('Out-of-Range Readings', ar.out_of_range_count),
            ('Hydraulic Inconsistencies', ar.velocity_depth_count),
            ('Statistical Outliers', ar.zscore_count),
        ]
        for label, count in type_map:
            if count:
                ai_rows.append([label, str(count)])
        story.append(_tbl(ai_rows, col_widths=[100 * mm, USABLE_W - 100 * mm]))
        story.append(Spacer(1, 6 * mm))

    # ── Flow Volume Breakdown ────────────────────────────────────────────────
    if selections.include_volume_breakdown and volume_breakdown:
        interval_labels = {
            'daily': 'Daily', 'am_pm': 'AM / PM & Daily', 'hourly': 'Hourly',
        }
        story.append(Paragraph(
            f"Flow Volume Breakdown — {interval_labels.get(selections.volume_breakdown_interval, '')}",
            h2_style,
        ))
        # Column widths: Period 62, m³ 26, ML 22, Mean 26, Peak 26, Count 8
        col_w = [62*mm, 26*mm, 22*mm, 26*mm, 26*mm, 8*mm]
        vol_data = [['Period', 'Volume (m³)', 'Vol (ML)', 'Mean (L/s)', 'Peak (L/s)', 'N']]
        extra_styles = []
        for i, row in enumerate(volume_breakdown, start=1):
            vol_data.append([
                row['period_label'],
                f"{row['volume_m3']:,.1f}",
                f"{row['volume_ml']:.4f}",
                f"{row['mean_flow_lps']:.2f}",
                f"{row['peak_flow_lps']:.2f}",
                str(row['reading_count']),
            ])
            if row.get('is_grand_total'):
                extra_styles += [
                    ('BACKGROUND', (0, i), (-1, i), C_TOTAL),
                    ('FONTNAME',   (0, i), (-1, i), 'Helvetica-Bold'),
                ]
            elif row.get('is_subtotal'):
                extra_styles += [
                    ('BACKGROUND', (0, i), (-1, i), C_SUBTOTAL),
                    ('FONTNAME',   (0, i), (-1, i), 'Helvetica-Bold'),
                ]
        story.append(_tbl(vol_data, col_widths=col_w, extra_styles=extra_styles))
        story.append(Paragraph(
            '1 m³ = 1 kL  ·  1 ML = 1,000 m³  ·  Volumes by trapezoidal integration.',
            small_style,
        ))
        story.append(Spacer(1, 6 * mm))

    # ── Summary statistics ───────────────────────────────────────────────────
    METRIC_LABELS = {
        'mean': 'Mean', 'max': 'Maximum', 'min': 'Minimum',
        'std': 'Std Deviation', 'p50': 'Median (P50)', 'p95': '95th Percentile (P95)',
        'range': 'Range', 'count': 'Total Readings',
        'volume_liters': 'Total Volume (L)', 'volume_m3': 'Total Volume (m³)',
    }
    if selections.include_stats_table and calculations:
        story.append(Paragraph('Summary Statistics', h2_style))
        for var, stats in calculations.items():
            if not stats:
                continue
            story.append(Paragraph(VAR_LABELS.get(var, var), h3_style))
            stat_rows = [['Metric', 'Value']] + [
                [METRIC_LABELS.get(k, k), _METRIC_FORMATS.get(k, '{:,.3f}').format(v)]
                for k, v in stats.items()
            ]
            story.append(_tbl(stat_rows, col_widths=[80 * mm, USABLE_W - 80 * mm]))
        story.append(Spacer(1, 6 * mm))

    # ── Charts ───────────────────────────────────────────────────────────────
    if selections.include_charts and charts and _KALEIDO_AVAILABLE:
        story.append(Paragraph('Time-Series Charts', h2_style))
        for var, fig in charts.items():
            b64 = fig_to_base64_png(fig)
            if b64:
                img_buf = io.BytesIO(base64.b64decode(b64))
                img = RLImage(img_buf, width=USABLE_W, height=USABLE_W * 0.45)
                story.append(Paragraph(VAR_LABELS.get(var, var), h3_style))
                story.append(img)
                story.append(Spacer(1, 4 * mm))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width='100%', thickness=1, color=C_BORDER))
    story.append(Paragraph('e-flow™ by EDS — Hydrological Intelligence Platform', footer_style))

    doc.build(story)
    return buf.getvalue()


def build_pdf_report(device_name: str,
                     df: pd.DataFrame,
                     selections: ReportSelections,
                     calculations: Dict[str, Dict[str, float]],
                     charts: Dict[str, go.Figure],
                     logo_path: Optional[str] = None,
                     volume_breakdown: Optional[List[Dict]] = None) -> bytes:
    """Generate a PDF report.

    Tries WeasyPrint first (richer HTML-CSS rendering); falls back to a
    pure-Python reportlab implementation that requires no system libraries.
    Returns empty bytes only if both engines are unavailable.
    """
    # ── WeasyPrint path ──────────────────────────────────────────────────────
    if _WEASYPRINT_AVAILABLE:
        try:
            html_content = build_html_report(
                device_name, df, selections, calculations, charts, logo_path,
                volume_breakdown=volume_breakdown,
            )
            pdf_bytes = HTML(string=html_content).write_pdf()
            if pdf_bytes:
                return pdf_bytes
        except Exception as e:
            print(f"WeasyPrint PDF generation failed, falling back to reportlab: {e}")

    # ── reportlab fallback ───────────────────────────────────────────────────
    if _REPORTLAB_AVAILABLE:
        try:
            return _build_pdf_reportlab(
                device_name, df, selections, calculations, charts,
                volume_breakdown=volume_breakdown,
            )
        except Exception as e:
            print(f"reportlab PDF generation failed: {e}")

    return b""
