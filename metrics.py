"""
Engineering metrics computation for EDS FlowSense.

Derives high-level hydraulic indicators from measured flow data.
All computations are read-only — no existing data is modified.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

# Hydraulic thresholds
_SELF_CLEANSING_MPS = 0.6   # minimum self-cleansing velocity (m/s) — WaPUG guidance
_II_HIGH_RATIO = 2.0         # peak/dry flow ratio > this → High I/I risk
_II_MEDIUM_RATIO = 1.5       # peak/dry flow ratio > this → Medium I/I risk
_DWF_PERCENTILE = 0.10       # 10th-percentile represents dry-weather baseline


def compute_engineering_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute engineering metrics from a flow dataframe.

    Parameters
    ----------
    df : DataFrame with columns [timestamp, depth_mm, velocity_mps, flow_lps]

    Returns
    -------
    dict with keys:
        dwf, pwwf, ii_risk, ii_risk_color, confidence, confidence_label,
        confidence_explanation, model_readiness, model_readiness_label,
        model_readiness_color, system_health, system_health_color,
        site_status, site_status_color, flow_ratio, velocity_note,
        self_cleansing_ok, zero_flow_pct, data_points
    """
    result: Dict[str, Any] = {
        "dwf": None,
        "pwwf": None,
        "ii_risk": "Unknown",
        "ii_risk_color": "#6b7280",
        "confidence": 0.0,
        "confidence_label": "Low",
        "confidence_explanation": "Insufficient data for reliable analysis",
        "model_readiness": "INSUFFICIENT DATA",
        "model_readiness_label": "INSUFFICIENT DATA",
        "model_readiness_color": "#D93025",
        "system_health": "Unknown",
        "system_health_color": "#6b7280",
        "site_status": "AWAITING DATA — Insufficient readings for analysis",
        "site_status_color": "#6b7280",
        "flow_ratio": None,
        "velocity_note": None,
        "self_cleansing_ok": None,
        "zero_flow_pct": None,
        "data_points": 0,
    }

    if df is None or df.empty:
        return result

    df = df.copy()
    n = len(df)
    result["data_points"] = n

    # ── Flow metrics ────────────────────────────────────────────────────────
    if "flow_lps" in df.columns:
        flow = df["flow_lps"].dropna()
        if not flow.empty:
            # 10th-percentile approximates dry-weather baseflow.
            # This assumes the majority of readings occur during dry conditions;
            # results may be less representative in highly infiltrated systems
            # or during extended wet periods where dry readings are scarce.
            dwf = float(flow.quantile(_DWF_PERCENTILE))
            pwwf = float(flow.max())
            result["dwf"] = dwf
            result["pwwf"] = pwwf
            flow_ratio = pwwf / max(dwf, 0.01)
            result["flow_ratio"] = round(flow_ratio, 2)

            if flow_ratio > _II_HIGH_RATIO:
                result["ii_risk"] = "HIGH"
                result["ii_risk_color"] = "#D93025"
            elif flow_ratio > _II_MEDIUM_RATIO:
                result["ii_risk"] = "MEDIUM"
                result["ii_risk_color"] = "#F4B400"
            else:
                result["ii_risk"] = "LOW"
                result["ii_risk_color"] = "#4CAF50"

            zero_flow_pct = float((flow <= 0.01).sum() / len(flow) * 100)
            result["zero_flow_pct"] = round(zero_flow_pct, 1)

    # ── Velocity ────────────────────────────────────────────────────────────
    if "velocity_mps" in df.columns:
        vel = df["velocity_mps"].dropna()
        if not vel.empty:
            avg_vel = float(vel.mean())
            if avg_vel < _SELF_CLEANSING_MPS:
                result["self_cleansing_ok"] = False
                result["velocity_note"] = (
                    f"Below self-cleansing threshold ({_SELF_CLEANSING_MPS} m/s)"
                )
            else:
                result["self_cleansing_ok"] = True
                result["velocity_note"] = (
                    f"Above self-cleansing threshold ({_SELF_CLEANSING_MPS} m/s)"
                )

    # ── Confidence score ────────────────────────────────────────────────────
    if n >= 200:
        confidence = 85.0
    elif n >= 100:
        confidence = 70.0
    elif n >= 50:
        confidence = 55.0
    elif n >= 20:
        confidence = 40.0
    else:
        confidence = 20.0

    # Penalise for missing values
    if "flow_lps" in df.columns:
        missing_pct = df["flow_lps"].isna().sum() / max(1, n) * 100
        confidence -= min(20.0, missing_pct * 0.5)

    confidence = round(max(0.0, min(100.0, confidence)), 1)
    result["confidence"] = confidence

    if confidence >= 80:
        result["confidence_label"] = "High"
        result["confidence_explanation"] = (
            "High reliability — suitable for calibration and reporting"
        )
    elif confidence >= 60:
        result["confidence_label"] = "Medium"
        result["confidence_explanation"] = (
            "Moderate reliability — suitable for indicative analysis"
        )
    else:
        result["confidence_label"] = "Low"
        result["confidence_explanation"] = "Low reliability — more data required"

    # ── Model Readiness ─────────────────────────────────────────────────────
    if confidence >= 80 and n >= 100:
        result["model_readiness"] = "SUITABLE"
        result["model_readiness_label"] = "SUITABLE"
        result["model_readiness_color"] = "#4CAF50"
    elif confidence >= 60 and n >= 50:
        result["model_readiness"] = "CONDITIONAL"
        result["model_readiness_label"] = "CONDITIONAL"
        result["model_readiness_color"] = "#F4B400"
    else:
        result["model_readiness"] = "INSUFFICIENT DATA"
        result["model_readiness_label"] = "INSUFFICIENT DATA"
        result["model_readiness_color"] = "#D93025"

    # ── System Health ───────────────────────────────────────────────────────
    ii_risk = result["ii_risk"]
    if ii_risk == "HIGH":
        result["system_health"] = "CRITICAL"
        result["system_health_color"] = "#D93025"
    elif ii_risk == "MEDIUM":
        result["system_health"] = "WARNING"
        result["system_health_color"] = "#F4B400"
    elif ii_risk == "LOW":
        result["system_health"] = "NORMAL"
        result["system_health_color"] = "#4CAF50"

    # ── Site Status ─────────────────────────────────────────────────────────
    parts = []
    if ii_risk == "HIGH":
        parts.append("HIGH INFLOW DETECTED")
        parts.append(
            "Suitable for preliminary analysis"
            if confidence >= 60
            else "More data recommended"
        )
    elif ii_risk == "MEDIUM":
        parts.append("MODERATE INFLOW DETECTED")
        parts.append("Monitor closely")
    elif ii_risk == "LOW":
        parts.append("STABLE CONDITIONS")
        parts.append("Baseline established")
    else:
        parts.append("ANALYSIS IN PROGRESS")

    result["site_status"] = " — ".join(parts)
    result["site_status_color"] = result["ii_risk_color"]

    return result
