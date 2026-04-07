"""
Advanced hydraulic analysis module for EDS FlowSense (EDS-FS).

Implements pipe-capacity and utilisation analysis based on Manning's equation
for circular conduits flowing partially full.

Public API
----------
compute_pipe_capacity(diameter_mm, manning_n, slope_pct)    → float (L/s full-bore)
compute_hydraulic_utilisation(df, qfull_lps)                → HydraulicReport
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Defaults (can be overridden per call) ──────────────────────────────────────
_DEFAULT_MANNING_N: float = 0.013    # smooth concrete / vitrified clay sewer (WSAA ref.)
_DEFAULT_SLOPE_PCT: float = 0.5      # 0.5 % → 1 : 200, typical design grade
_FULL_BORE_THRESHOLD_PCT: float = 90.0  # ≥ 90 % utilisation = full-bore / surcharge risk
_MIN_READINGS: int = 20


@dataclass
class FullBoreEvent:
    """A contiguous period during which pipe utilisation exceeded the full-bore threshold."""
    start: pd.Timestamp
    end: pd.Timestamp
    duration_minutes: float
    peak_utilisation_pct: float


@dataclass
class HydraulicReport:
    """Results of the hydraulic capacity and utilisation analysis."""
    pipe_diameter_mm: float
    manning_n: float
    slope_pct: float
    qfull_lps: float                    # theoretical full-bore capacity (L/s)
    mean_utilisation_pct: float
    median_utilisation_pct: float
    max_utilisation_pct: float
    p90_utilisation_pct: float
    full_bore_events: List[FullBoreEvent]
    surcharge_risk_label: str           # Low / Moderate / High / Critical
    surcharge_risk_colour: str
    interpretation: str
    sample_size: int


def compute_pipe_capacity(
    diameter_mm: float,
    manning_n: float = _DEFAULT_MANNING_N,
    slope_pct: float = _DEFAULT_SLOPE_PCT,
) -> float:
    """Return the theoretical full-bore flow capacity (L/s) for a circular pipe.

    Uses Manning's equation:
        Q = (1 / n) × A × R^(2/3) × S^(1/2)

    where for a full circular section of diameter D (metres):
        A = π D² / 4
        R = D / 4  (hydraulic radius)
        S = slope as a fraction (dimensionless)

    Parameters
    ----------
    diameter_mm : internal pipe diameter in millimetres
    manning_n   : Manning's roughness coefficient (default 0.013 for concrete)
    slope_pct   : longitudinal slope in percent (e.g. 0.5 for 1:200)

    Returns
    -------
    float — full-bore capacity in litres per second (L/s)
    """
    if diameter_mm <= 0 or manning_n <= 0 or slope_pct <= 0:
        return 0.0
    D = diameter_mm / 1000.0          # mm → m
    A = np.pi * D ** 2 / 4.0          # cross-sectional area (m²)
    R = D / 4.0                        # hydraulic radius for full circle (m)
    S = slope_pct / 100.0              # slope fraction
    Q_m3s = (1.0 / manning_n) * A * R ** (2.0 / 3.0) * np.sqrt(S)
    return round(Q_m3s * 1000.0, 2)   # m³/s → L/s


def compute_hydraulic_utilisation(
    df: pd.DataFrame,
    qfull_lps: float,
    full_bore_threshold_pct: float = _FULL_BORE_THRESHOLD_PCT,
) -> Optional[HydraulicReport]:
    """Compute pipe utilisation statistics and detect full-bore / surcharge events.

    Parameters
    ----------
    df : DataFrame with at minimum columns [timestamp, flow_lps]
    qfull_lps : theoretical full-bore capacity in L/s (from compute_pipe_capacity)
    full_bore_threshold_pct : utilisation level (%) above which to flag surcharge risk

    Returns
    -------
    HydraulicReport, or None if there is insufficient data.
    """
    if df is None or df.empty or "flow_lps" not in df.columns:
        return None
    if qfull_lps <= 0:
        return None

    df_work = df[["timestamp", "flow_lps"]].copy()
    df_work["timestamp"] = pd.to_datetime(df_work["timestamp"], errors="coerce")
    df_work = (
        df_work.dropna(subset=["timestamp", "flow_lps"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    if len(df_work) < _MIN_READINGS:
        return None

    flow = pd.to_numeric(df_work["flow_lps"], errors="coerce").clip(lower=0.0)
    utilisation_pct = (flow / qfull_lps * 100.0).values

    mean_u   = float(np.nanmean(utilisation_pct))
    median_u = float(np.nanmedian(utilisation_pct))
    max_u    = float(np.nanmax(utilisation_pct))
    p90_u    = float(np.nanpercentile(utilisation_pct, 90))

    # Detect contiguous full-bore events
    above_threshold = utilisation_pct >= full_bore_threshold_pct
    events: List[FullBoreEvent] = []
    in_event = False
    event_start_idx = 0

    for i, flag in enumerate(above_threshold):
        if flag and not in_event:
            in_event = True
            event_start_idx = i
        elif not flag and in_event:
            in_event = False
            event_rows = df_work.iloc[event_start_idx:i]
            duration = (
                event_rows["timestamp"].iloc[-1] - event_rows["timestamp"].iloc[0]
            ).total_seconds() / 60.0
            events.append(FullBoreEvent(
                start=event_rows["timestamp"].iloc[0],
                end=event_rows["timestamp"].iloc[-1],
                duration_minutes=round(max(1.0, duration), 1),
                peak_utilisation_pct=round(float(utilisation_pct[event_start_idx:i].max()), 1),
            ))
    # Close any open event at end of data
    if in_event:
        event_rows = df_work.iloc[event_start_idx:]
        duration = (
            event_rows["timestamp"].iloc[-1] - event_rows["timestamp"].iloc[0]
        ).total_seconds() / 60.0
        events.append(FullBoreEvent(
            start=event_rows["timestamp"].iloc[0],
            end=event_rows["timestamp"].iloc[-1],
            duration_minutes=round(max(1.0, duration), 1),
            peak_utilisation_pct=round(float(utilisation_pct[event_start_idx:].max()), 1),
        ))

    # Risk classification
    if max_u >= 100.0 or len(events) >= 5:
        risk = "Critical"
        risk_colour = "#D93025"
        interp = (
            f"Pipe is operating at or beyond theoretical capacity "
            f"(peak utilisation {max_u:.0f}%). {len(events)} surcharge event(s) detected. "
            "Immediate investigation is recommended — assess for downstream flooding risk, "
            "sewer overflow, and possible capacity upgrade requirement."
        )
    elif max_u >= 90.0 or len(events) >= 2:
        risk = "High"
        risk_colour = "#E65100"
        interp = (
            f"Peak utilisation {max_u:.0f}% indicates the pipe is at or near design capacity "
            f"during {len(events)} event(s). Consider a condition survey and hydraulic modelling "
            "to confirm headroom during design storm events."
        )
    elif max_u >= 70.0:
        risk = "Moderate"
        risk_colour = "#F4B400"
        interp = (
            f"P90 utilisation of {p90_u:.0f}% and peak of {max_u:.0f}% indicate moderate loading. "
            "Monitor for increasing trends; review catchment growth plans."
        )
    else:
        risk = "Low"
        risk_colour = "#4CAF50"
        interp = (
            f"Pipe is operating well within capacity (peak {max_u:.0f}%, "
            f"mean {mean_u:.0f}%). No immediate hydraulic concern."
        )

    return HydraulicReport(
        pipe_diameter_mm=0.0,   # caller should set after creation if needed
        manning_n=0.0,
        slope_pct=0.0,
        qfull_lps=round(qfull_lps, 2),
        mean_utilisation_pct=round(mean_u, 1),
        median_utilisation_pct=round(median_u, 1),
        max_utilisation_pct=round(max_u, 1),
        p90_utilisation_pct=round(p90_u, 1),
        full_bore_events=events,
        surcharge_risk_label=risk,
        surcharge_risk_colour=risk_colour,
        interpretation=interp,
        sample_size=len(df_work),
    )
