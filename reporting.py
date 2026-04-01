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
                      charts: Dict[str, go.Figure],
                      logo_path: Optional[str] = None) -> str:
    """Generate an HTML report string with embedded charts, metrics, AI insights, and optional logo."""
    # Header and metadata
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_type_label = {
        "daily": "Daily Summary",
        "weekly": "Weekly Summary",
        "monthly": "Monthly Summary",
        "custom": "Custom Report",
    }.get(selections.report_type, "Technical Report")

    # Period label
    if not df.empty:
        ts = pd.to_datetime(df["timestamp"])
        period_start = ts.min().strftime("%Y-%m-%d %H:%M")
        period_end = ts.max().strftime("%Y-%m-%d %H:%M")
        period_label = f"{period_start} → {period_end}"
    else:
        period_label = f"Last {selections.time_window_hours} hours"

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

    # AI insights section
    ar: Optional[AnomalyReport] = selections.anomaly_report
    if ar is not None:
        qual_color = {"High": "#4CAF50", "Medium": "#F4B400", "Low": "#D93025"}.get(ar.quality_label, "#333")
        qual_bg = {"High": "#E8F5E9", "Medium": "#FFF8E1", "Low": "#FDECEA"}.get(ar.quality_label, "#f9fafb")
        ai_html = f"""
        <div class='section card' style='border-left: 4px solid {qual_color}; background: {qual_bg};'>
          <h2>AI Insights &amp; Data Quality</h2>
          <p><strong>Data Confidence Rating:</strong>
             <span style='color:{qual_color}; font-weight:700; font-size:1.1em;'>{ar.quality_label}</span>
             ({ar.confidence_score:.1f}/100)
          </p>
          <p><strong>Anomalies Detected:</strong> {len(ar.flags)}</p>
          <p><strong>Summary:</strong> {ar.summary}</p>
          <table>
            <thead><tr><th>Anomaly Type</th><th>Count</th></tr></thead>
            <tbody>
              <tr><td>Flatline</td><td>{ar.flatline_count}</td></tr>
              <tr><td>Spike</td><td>{ar.spike_count}</td></tr>
              <tr><td>Data Gaps (Dropouts)</td><td>{ar.dropout_count}</td></tr>
              <tr><td>Out-of-Range</td><td>{ar.out_of_range_count}</td></tr>
              <tr><td>Velocity/Depth Inconsistency</td><td>{ar.velocity_depth_count}</td></tr>
              <tr><td>Statistical Outlier (Z-score)</td><td>{ar.zscore_count}</td></tr>
            </tbody>
          </table>
        </div>
        <div class='section card'>
          <h2>Data Quality Summary</h2>
          <table>
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>
              <tr><td>Valid Data</td><td>{ar.pct_valid:.1f}%</td></tr>
              <tr><td>Flagged Data</td><td>{ar.pct_flagged:.1f}%</td></tr>
              <tr><td>Total Data Points</td><td>{len(df)}</td></tr>
              <tr><td>Anomaly Flags</td><td>{len(ar.flags)}</td></tr>
            </tbody>
          </table>
        </div>
        """
    else:
        ai_html = ""

    intro = f"""
    <html>
      <head>
        <meta charset='utf-8'/>
        <title>e-flow {report_type_label} — {device_name}</title>
        <style>
          body {{ font-family: -apple-system, Segoe UI, Roboto, Inter, sans-serif; color: #4A4A4A; margin: 40px; background: #F4F5F4; }}
          h1, h2 {{ font-weight: 600; color: #4A4A4A; }}
          h1 {{ margin-top: 0; color: #3A7F5F; }}
          h2 {{ color: #2F6B50; }}
          .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 30px; border-bottom: 3px solid #3A7F5F; padding-bottom: 20px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 6px rgba(58,127,95,0.08); }}
          .header-left {{ display: flex; align-items: center; gap: 20px; }}
          .section {{ margin: 24px 0; }}
          .card {{ border: 1px solid #D9D9D9; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #ffffff; box-shadow: 0 1px 4px rgba(58,127,95,0.05); }}
          table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
          th, td {{ border: 1px solid #D9D9D9; padding: 10px; text-align: right; }}
          th {{ background: #E8F3EE; text-align: left; font-weight: 600; color: #2F6B50; }}
          .small {{ color: #6b7280; font-size: 12px; margin-top: 8px; }}
          .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }}
          .metric-box {{ border: 1px solid #D9D9D9; padding: 12px; border-radius: 8px; background: white; }}
          .metric-label {{ color: #6b7280; font-size: 12px; font-weight: 500; text-transform: uppercase; }}
          .metric-value {{ font-size: 18px; font-weight: 600; color: #3A7F5F; margin-top: 4px; }}
        </style>
      </head>
      <body>
        <div class='header'>
          <div class='header-left'>
            {logo_html}
            <div>
              <h1>e-flow {report_type_label}</h1>
              <div class='small'>Generated: {generated_at}</div>
            </div>
          </div>
        </div>

        <div class='section card'>
          <h2>Site Information</h2>
          <p><strong>Station:</strong> {html.escape(device_name)}</p>
          {'<p><strong>Site ID:</strong> ' + html.escape(selections.site_id) + '</p>' if selections.site_id else ''}
          {'<p><strong>Location:</strong> ' + html.escape(selections.location) + '</p>' if selections.location else ''}
          <p><strong>Monitoring Period:</strong> {html.escape(period_label)}</p>
          <p><strong>Variables:</strong> {html.escape(', '.join(selections.variables))}</p>
          <p><strong>Data Points:</strong> {len(df)}</p>
        </div>

        {ai_html}

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
    metrics_html = "<div class='section card'><h2>Summary Statistics</h2>"
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
            charts_html += f"<h3>{var}</h3>" + fig.to_html(include_plotlyjs="cdn", full_html=False)
    charts_html += "</div>"

    outro = "</body></html>"

    return intro + metrics_html + charts_html + outro


def _build_pdf_reportlab(device_name: str,
                         df: pd.DataFrame,
                         selections: ReportSelections,
                         calculations: Dict[str, Dict[str, float]],
                         charts: Dict[str, go.Figure]) -> bytes:
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

    def _tbl(data, col_widths=None):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0), C_LIGHT_GREEN),
            ('TEXTCOLOR',    (0, 0), (-1, 0), C_DARK_GREEN),
            ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, -1), 9),
            ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_ROW_ALT]),
            ('GRID',         (0, 0), (-1, -1), 0.5, C_BORDER),
            ('ALIGN',        (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN',        (0, 0), (0, -1), 'LEFT'),
            ('TOPPADDING',   (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',  (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        return t

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    report_type_label = {
        'daily': 'Daily Summary', 'weekly': 'Weekly Summary',
        'monthly': 'Monthly Summary', 'custom': 'Custom Report',
    }.get(selections.report_type, 'Technical Report')

    generated_at = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    story.append(Paragraph(f'e-flow™ {report_type_label}', title_style))
    story.append(Paragraph(f'Generated: {generated_at}', small_style))
    story.append(HRFlowable(width='100%', thickness=2, color=C_GREEN, spaceAfter=10))

    # ── Site information ─────────────────────────────────────────────────────
    story.append(Paragraph('Site Information', h2_style))

    if not df.empty:
        ts = pd.to_datetime(df['timestamp'])
        period_start = ts.min().strftime('%d/%m/%Y %H:%M')
        period_end   = ts.max().strftime('%d/%m/%Y %H:%M')
        period_label = f'{period_start} → {period_end}'
    else:
        period_label = f'Last {selections.time_window_hours} hours'

    site_rows = [['Field', 'Value'],
                 ['Station', html.escape(device_name)]]
    if selections.site_id:
        site_rows.append(['Site ID', html.escape(selections.site_id)])
    if selections.location:
        site_rows.append(['Location', html.escape(selections.location)])
    site_rows += [
        ['Monitoring Period', period_label],
        ['Variables', ', '.join(selections.variables)],
        ['Data Points', str(len(df))],
    ]
    story.append(_tbl(site_rows, col_widths=[55 * mm, USABLE_W - 55 * mm]))
    story.append(Spacer(1, 6 * mm))

    # ── AI Insights ──────────────────────────────────────────────────────────
    ar: Optional[AnomalyReport] = selections.anomaly_report
    if ar is not None:
        story.append(Paragraph('AI Insights & Data Quality', h2_style))
        ai_rows = [
            ['Metric', 'Value'],
            ['Data Quality', ar.quality_label],
            ['Confidence Score', f'{ar.confidence_score:.1f} / 100'],
            ['Total Anomalies', str(len(ar.flags))],
            ['Valid Data', f'{ar.pct_valid:.1f}%'],
            ['Flagged Data', f'{ar.pct_flagged:.1f}%'],
            ['Flatline Events', str(ar.flatline_count)],
            ['Spikes', str(ar.spike_count)],
            ['Data Gaps', str(ar.dropout_count)],
            ['Out-of-Range', str(ar.out_of_range_count)],
            ['Statistical Outliers', str(ar.zscore_count)],
        ]
        story.append(_tbl(ai_rows, col_widths=[80 * mm, USABLE_W - 80 * mm]))
        if ar.summary:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(f'<i>Summary: {html.escape(ar.summary)}</i>', body_style))
        story.append(Spacer(1, 6 * mm))

    # ── Summary statistics ───────────────────────────────────────────────────
    if calculations:
        story.append(Paragraph('Summary Statistics', h2_style))
        VAR_LABELS = {
            'depth_mm': 'Water Depth (mm)',
            'velocity_mps': 'Flow Velocity (m/s)',
            'flow_lps': 'Flow Rate (L/s)',
        }
        METRIC_LABELS = {
            'mean': 'Mean', 'max': 'Maximum', 'min': 'Minimum',
            'std': 'Std Deviation', 'p50': 'Median (P50)', 'p95': 'P95',
            'range': 'Range', 'count': 'Count',
            'volume_liters': 'Total Volume (L)', 'volume_m3': 'Total Volume (m³)',
        }
        for var, stats in calculations.items():
            if not stats:
                continue
            story.append(Paragraph(VAR_LABELS.get(var, var), h3_style))
            stat_rows = [['Metric', 'Value']] + [
                [METRIC_LABELS.get(k, k), f'{v:,.3f}'] for k, v in stats.items()
            ]
            story.append(_tbl(stat_rows, col_widths=[80 * mm, USABLE_W - 80 * mm]))
        story.append(Spacer(1, 6 * mm))

    # ── Charts ───────────────────────────────────────────────────────────────
    if charts and _KALEIDO_AVAILABLE:
        story.append(Paragraph('Charts', h2_style))
        VAR_LABELS = {
            'depth_mm': 'Water Depth (mm)',
            'velocity_mps': 'Flow Velocity (m/s)',
            'flow_lps': 'Flow Rate (L/s)',
        }
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
                     logo_path: Optional[str] = None) -> bytes:
    """Generate a PDF report.

    Tries WeasyPrint first (richer HTML-CSS rendering); falls back to a
    pure-Python reportlab implementation that requires no system libraries.
    Returns empty bytes only if both engines are unavailable.
    """
    # ── WeasyPrint path ──────────────────────────────────────────────────────
    if _WEASYPRINT_AVAILABLE:
        try:
            html_content = build_html_report(
                device_name, df, selections, calculations, charts, logo_path
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
                device_name, df, selections, calculations, charts
            )
        except Exception as e:
            print(f"reportlab PDF generation failed: {e}")

    return b""
