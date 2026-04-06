"""
GIS map rendering for EDS FlowSense.

Builds an interactive Plotly Scattermapbox figure that plots monitoring sites
coloured by I/I risk level.  All rendering is read-only.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import plotly.graph_objects as go

# Risk → marker colour mapping
_RISK_COLOR: Dict[str, str] = {
    "HIGH": "#D93025",
    "MEDIUM": "#F4B400",
    "LOW": "#4CAF50",
    "Unknown": "#6b7280",
}


def build_gis_figure(
    devices: List[Dict],
    device_metrics: Optional[Dict[str, Dict]] = None,
) -> go.Figure:
    """Build a Plotly Scattermapbox figure of monitoring sites.

    Parameters
    ----------
    devices : list of device dicts from ``FlowDatabase.get_devices()``
    device_metrics : optional mapping of device_id → metrics dict from
        ``metrics.compute_engineering_metrics``; used to colour sites by risk.

    Returns
    -------
    Plotly Figure — ready to pass to ``st.plotly_chart``.
    """
    lats: List[float] = []
    lons: List[float] = []
    names: List[str] = []
    colors: List[str] = []
    texts: List[str] = []

    for d in devices:
        lat = d.get("latitude")
        lon = d.get("longitude")
        if lat is None or lon is None:
            continue

        lats.append(float(lat))
        lons.append(float(lon))
        names.append(d.get("device_name") or d["device_id"])

        m = (device_metrics or {}).get(d["device_id"], {})
        ii_risk = m.get("ii_risk", "Unknown")
        colors.append(_RISK_COLOR.get(ii_risk, "#6b7280"))

        # Build rich tooltip
        dwf = m.get("dwf")
        pwwf = m.get("pwwf")
        conf = m.get("confidence")
        tooltip_lines = [
            f"<b>{d.get('device_name') or d['device_id']}</b>",
            f"I/I Risk: <b>{ii_risk}</b>",
        ]
        if dwf is not None:
            tooltip_lines.append(f"DWF: {dwf:.1f} L/s")
        if pwwf is not None:
            tooltip_lines.append(f"Peak Flow: {pwwf:.1f} L/s")
        if conf is not None:
            tooltip_lines.append(f"Confidence: {conf:.0f}%")
        if d.get("location"):
            tooltip_lines.append(f"Location: {d['location']}")
        texts.append("<br>".join(tooltip_lines))

    if not lats:
        fig = go.Figure()
        fig.update_layout(
            annotations=[
                dict(
                    text=(
                        "No device coordinates set.<br>"
                        "Configure GPS locations in Admin Panel → Map Location."
                    ),
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=14, color="#6b7280"),
                    align="center",
                )
            ],
            height=480,
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f9faf9",
        )
        return fig

    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    fig = go.Figure(
        go.Scattermapbox(
            lat=lats,
            lon=lons,
            mode="markers+text",
            marker=dict(size=16, color=colors, opacity=0.9),
            text=names,
            textposition="top center",
            hovertext=texts,
            hoverinfo="text",
            name="",
        )
    )

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=10,
        ),
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#ffffff",
        showlegend=False,
    )
    return fig
