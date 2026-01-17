from __future__ import annotations

import io
import base64
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# For static image export of plotly charts
# kaleido is optional; if unavailable, images will be skipped
try:
    import kaleido  # noqa: F401
    _KALEIDO_AVAILABLE = True
except Exception:
    _KALEIDO_AVAILABLE = False


@dataclass
class ReportSelections:
    variables: List[str]  # e.g., ["depth_mm", "velocity_mps", "flow_lps"]
    calculations: List[str]  # e.g., ["mean","max","min","std","p50","p95","volume"]
    device_name: str
    time_window_hours: int


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
    dfx["timestamp"] = pd.to_datetime(dfx["timestamp"])  # tz-aware preserved
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

        # Volume integration only applies to flow_lps
        if var == "flow_lps" and "volume" in selections.calculations:
            # Integrate flow (L/s) over time using trapezoidal rule on irregular sampling
            t = dfx["timestamp"].astype("int64") / 1e9  # seconds since epoch
            f = pd.to_numeric(dfx["flow_lps"], errors="coerce").fillna(0.0)
            if t.shape[0] > 1:
                # Compute time differences and trapezoids
                dt = np.diff(t.values)  # seconds
                f_mid = (f.values[:-1] + f.values[1:]) / 2.0  # L/s
                liters = float(np.sum(f_mid * dt))  # L
                m3 = liters / 1000.0
                stats["volume_liters"] = liters
                stats["volume_m3"] = m3

        results[var] = stats

    return results


def create_charts(df: pd.DataFrame, selections: ReportSelections) -> Dict[str, go.Figure]:
    """Create time-series charts for selected variables."""
    charts: Dict[str, go.Figure] = {}
    if df.empty:
        return charts
    dfx = df.copy()
    dfx["timestamp"] = pd.to_datetime(dfx["timestamp"])
    dfx = dfx.sort_values("timestamp")

    for var in selections.variables:
        if var not in dfx.columns:
            continue
        fig = px.line(dfx, x="timestamp", y=var, title=f"{selections.device_name} — {var}")
        fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=320)
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
                      charts: Dict[str, go.Figure]) -> str:
    """Generate an HTML report string with embedded charts and metrics."""
    # Header and metadata
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    intro = f"""
    <html>
      <head>
        <meta charset='utf-8'/>
        <title>e-flow Technical Report — {device_name}</title>
        <style>
          body {{ font-family: -apple-system, Segoe UI, Roboto, Inter, sans-serif; color: #222; }}
          h1, h2 {{ font-weight: 600; }}
          .section {{ margin: 18px 0; }}
          .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; margin-bottom: 12px; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border: 1px solid #eee; padding: 8px; text-align: right; }}
          th {{ background: #f8fafc; text-align: left; }}
          .small {{ color: #666; font-size: 12px; }}
        </style>
      </head>
      <body>
        <h1>e-flow Technical Report</h1>
        <div class='small'>Generated: {generated_at}</div>
        <div class='section card'>
          <h2>Overview</h2>
          <p><strong>Station:</strong> {device_name}</p>
          <p><strong>Time Window:</strong> Last {selections.time_window_hours} hours</p>
          <p><strong>Variables:</strong> {', '.join(selections.variables)}</p>
          <p><strong>Calculations:</strong> {', '.join(selections.calculations)}</p>
        </div>

        <div class='section card'>
          <h2>Metrics Glossary</h2>
          <table>
            <thead><tr><th>Metric</th><th>Definition</th></tr></thead>
            <tbody>
              <tr><td><strong>mean</strong></td><td>Average value across all measurements in the time window</td></tr>
              <tr><td><strong>max</strong></td><td>Highest value recorded</td></tr>
              <tr><td><strong>min</strong></td><td>Lowest value recorded</td></tr>
              <tr><td><strong>std</strong></td><td>Standard deviation — how spread out values are from the mean (variability indicator)</td></tr>
              <tr><td><strong>p50</strong></td><td>Median (50th percentile) — middle value where 50% of data falls below and 50% above</td></tr>
              <tr><td><strong>p95</strong></td><td>95th percentile — value below which 95% of measurements fall; useful for high-flow/capacity analysis</td></tr>
              <tr><td><strong>range</strong></td><td>Difference between maximum and minimum values</td></tr>
              <tr><td><strong>count</strong></td><td>Total number of measurements in the time window</td></tr>
              <tr><td><strong>volume</strong></td><td>Total flow volume integrated over time (flow_lps only) — reported in liters and cubic meters</td></tr>
            </tbody>
          </table>
        </div>
    """

    # Metrics table
    metrics_html = "<div class='section card'><h2>Calculated Metrics</h2>"
    for var, stats in calculations.items():
        metrics_html += f"<h3>{var}</h3>"
        metrics_html += "<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
        for k, v in stats.items():
            metrics_html += f"<tr><td>{k}</td><td>{v:.3f}</td></tr>"
        metrics_html += "</tbody></table>"
    metrics_html += "</div>"

    # Charts
    charts_html = "<div class='section card'><h2>Charts</h2>"
    for var, fig in charts.items():
        b64 = fig_to_base64_png(fig)
        if b64:
            charts_html += f"<h3>{var}</h3><img src='data:image/png;base64,{b64}' style='max-width:100%;height:auto;border:1px solid #eee;border-radius:6px;'/>"
        else:
            # Fallback: embed interactive HTML (may not preserve on PDF export)
            charts_html += f"<h3>{var}</h3>" + fig.to_html(include_plotlyjs="cdn", full_html=False)
    charts_html += "</div>"

    outro = "</body></html>"

    return intro + metrics_html + charts_html + outro
