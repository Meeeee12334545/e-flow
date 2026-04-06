"""
Automated engineering insights generator for EDS FlowSense.

Produces 3–5 plain-language observations from flow data and pre-computed
metrics.  All analysis is read-only.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def generate_insights(
    df: pd.DataFrame,
    metrics: Dict[str, Any],
) -> List[str]:
    """Generate 3–5 engineering insights from flow data and computed metrics.

    Parameters
    ----------
    df : DataFrame with columns [timestamp, depth_mm, velocity_mps, flow_lps]
    metrics : dict returned by ``metrics.compute_engineering_metrics``

    Returns
    -------
    List of plain-language insight strings (at most 5).
    """
    insights: List[str] = []

    if df is None or df.empty or metrics.get("data_points", 0) == 0:
        return [
            "Insufficient data — connect a monitoring device to generate insights."
        ]

    ii_risk = metrics.get("ii_risk", "Unknown")
    flow_ratio = metrics.get("flow_ratio")
    zero_pct = metrics.get("zero_flow_pct")
    conf_label = metrics.get("confidence_label", "Low")
    n = metrics.get("data_points", 0)

    # ── Insight 1: I/I detection ─────────────────────────────────────────────
    if ii_risk == "HIGH" and flow_ratio is not None:
        insights.append(
            f"Flow increases significantly during rainfall — inflow detected "
            f"(peak/dry ratio: {flow_ratio:.1f}×, indicating significant "
            f"rainfall-derived inflow entering the network)"
        )
    elif ii_risk == "MEDIUM" and flow_ratio is not None:
        insights.append(
            f"Moderate flow response to wet weather detected "
            f"(peak/dry ratio: {flow_ratio:.1f}×) — further investigation recommended"
        )
    elif ii_risk == "LOW":
        insights.append(
            "Stable dry weather baseline established — suitable for network "
            "calibration and hydraulic modelling"
        )

    # ── Insight 2: Zero-flow / control structure ─────────────────────────────
    if zero_pct is not None:
        if zero_pct > 20:
            insights.append(
                f"Intermittent zero flow detected ({zero_pct:.0f}% of readings) "
                "— possible control structure, pump operation or gate present"
            )
        elif zero_pct < 5 and metrics.get("dwf", 0) is not None:
            insights.append(
                "Continuous flow observed — no intermittent shutoffs detected, "
                "consistent with a gravity-fed catchment"
            )

    # ── Insight 3: Self-cleansing velocity ───────────────────────────────────
    if metrics.get("velocity_note"):
        if not metrics.get("self_cleansing_ok"):
            insights.append(
                "Velocity is below the self-cleansing threshold — risk of sediment "
                "deposition in the pipe; consider operational review"
            )
        else:
            insights.append(
                "Velocity is above the self-cleansing threshold — sediment transport "
                "is adequate under current flow conditions"
            )

    # ── Insight 4: Data confidence ────────────────────────────────────────────
    if conf_label == "High":
        insights.append(
            f"High data confidence ({n} readings) — results are suitable for "
            "calibration and formal reporting"
        )
    elif conf_label == "Medium":
        insights.append(
            f"Moderate data confidence ({n} readings) — additional monitoring will "
            "improve analysis accuracy"
        )
    else:
        insights.append(
            f"Limited dataset ({n} readings) — continue monitoring to build "
            "sufficient data for reliable analysis"
        )

    # ── Insight 5: Flow variability ──────────────────────────────────────────
    if "flow_lps" in df.columns:
        flow = df["flow_lps"].dropna()
        if len(flow) >= 10:
            mean_flow = float(flow.mean())
            cv = float(flow.std() / max(mean_flow, 0.01))
            if cv > 0.5:
                insights.append(
                    "High flow variability detected — diurnal or event-driven "
                    "patterns are present; time-series decomposition is recommended"
                )
            elif cv < 0.15:
                insights.append(
                    "Low flow variability observed — consistent baseflow conditions "
                    "suitable for accurate dry-weather characterisation"
                )

    return insights[:5]
