"""
Rainfall analysis and AI Inflow/Infiltration (I/I) detection module for EDS FlowSense (EDS-FS).

Public API
----------
compute_dry_weather_baseline(df_flow, df_rainfall)  → float
detect_rain_events(df_rainfall, threshold_mm)        → List[RainEvent]
detect_inflow_infiltration(df_flow, df_rainfall, baseline) → RainfallResponse
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Timezone helper ───────────────────────────────────────────────────────────

def _to_utc_naive(series: pd.Series) -> pd.Series:
    """Convert a datetime Series to UTC-naive (strips or converts tz info).

    Ensures tz-aware and tz-naive timestamps can be joined/compared without
    raising ``TypeError: Cannot join tz-naive and tz-aware DatetimeIndexes``.
    """
    series = pd.to_datetime(series)
    if series.dt.tz is not None:
        series = series.dt.tz_convert("UTC").dt.tz_localize(None)
    return series


# ── Thresholds (adjustable via keyword args) ──────────────────────────────────
_DEFAULT_RAIN_THRESHOLD_MM = 0.1      # minimum mm/hr to count as "raining" (WMO measurable-rain threshold)
_DEFAULT_II_MULTIPLIER     = 1.5      # flow > baseline × this → I/I flag
_DRY_DAY_PRECIP_CAP_MM     = 0.1     # hourly mm/hr ≤ this → dry period for baseline calculation
_BASELINE_LOOKBACK_DAYS    = 7       # rolling window for dry-weather baseline
_MIN_DRY_READINGS          = 10      # minimum dry readings to compute baseline
_EVENT_MERGE_GAP_HOURS     = 3       # merge rain events closer than this many hours
_POST_RAIN_WINDOW_HOURS    = 6       # hours after rain stops to monitor flow
_Z_SCORE_CONFIDENCE_SCALE  = 10.0    # maps z-score to 0-100 confidence boost


@dataclass
class RainEvent:
    """A discrete rainfall event."""
    start: pd.Timestamp
    end: pd.Timestamp
    total_mm: float
    peak_mm_per_hour: float
    duration_hours: float


@dataclass
class IIFlag:
    """A detected Inflow/Infiltration response to a rain event."""
    rain_event: RainEvent
    peak_flow_lps: float
    baseline_lps: float
    response_ratio: float          # peak_flow / baseline
    lag_hours: float               # hours between rain start and peak flow
    severity: str                  # low / medium / high / critical
    confidence: float              # 0-100
    description: str


@dataclass
class RainfallResponse:
    """Top-level result of rainfall/I/I analysis."""
    baseline_lps: float
    quality_label: str             # High / Medium / Low
    confidence_score: float        # 0-100
    rain_events: List[RainEvent] = field(default_factory=list)
    ii_flags: List[IIFlag] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    dry_period_count: int = 0
    wet_period_count: int = 0


# ── Baseline computation ──────────────────────────────────────────────────────

def compute_dry_weather_baseline(
    df_flow: pd.DataFrame,
    df_rainfall: pd.DataFrame,
    lookback_days: int = _BASELINE_LOOKBACK_DAYS,
    dry_cap_mm: float = _DRY_DAY_PRECIP_CAP_MM,
) -> float:
    """Calculate dry-weather flow baseline (median L/s).

    Identifies dry periods (hourly rainfall ≤ *dry_cap_mm*) and computes the
    rolling median of flow readings over those periods within *lookback_days*.

    Parameters
    ----------
    df_flow : DataFrame with columns [timestamp, flow_lps]
    df_rainfall : DataFrame with columns [timestamp, rainfall_mm]
    lookback_days : only consider data this many days old
    dry_cap_mm : hourly rainfall threshold to classify a period as dry

    Returns
    -------
    float — median dry-weather flow in L/s, or the overall median if no dry
            periods can be found.
    """
    if df_flow is None or df_flow.empty or "flow_lps" not in df_flow.columns:
        return 0.0

    df_f = df_flow[["timestamp", "flow_lps"]].copy()
    df_f["timestamp"] = _to_utc_naive(df_f["timestamp"])
    df_f = df_f.dropna(subset=["timestamp", "flow_lps"])

    if df_f.empty:
        return 0.0

    # Limit to lookback window
    cutoff = df_f["timestamp"].max() - pd.Timedelta(days=lookback_days)
    df_f = df_f[df_f["timestamp"] >= cutoff]

    if df_f.empty:
        return float(df_flow["flow_lps"].median())

    # If rainfall data is available, mask out wet periods
    if df_rainfall is not None and not df_rainfall.empty and "rainfall_mm" in df_rainfall.columns:
        df_r = df_rainfall[["timestamp", "rainfall_mm"]].copy()
        df_r["timestamp"] = _to_utc_naive(df_r["timestamp"])
        df_r = df_r.dropna(subset=["timestamp"])

        # Merge on nearest hour
        df_f = df_f.set_index("timestamp").sort_index()
        df_r = df_r.set_index("timestamp").sort_index()

        # Resample rainfall to hourly buckets
        df_r_hourly = df_r["rainfall_mm"].resample("1h").sum()

        # Merge with flow (forward-fill for missing rainfall hours = 0)
        df_merged = df_f.join(df_r_hourly.rename("rain_h"), how="left")
        df_merged["rain_h"] = df_merged["rain_h"].fillna(0.0)

        dry_mask = df_merged["rain_h"] <= dry_cap_mm
        dry_readings = df_merged.loc[dry_mask, "flow_lps"].dropna()

        if len(dry_readings) >= _MIN_DRY_READINGS:
            # Use 10th–90th percentile to exclude outliers
            p10, p90 = dry_readings.quantile(0.10), dry_readings.quantile(0.90)
            trimmed = dry_readings[(dry_readings >= p10) & (dry_readings <= p90)]
            return float(trimmed.median()) if not trimmed.empty else float(dry_readings.median())
        # Fall back to overall median if not enough dry periods
        return float(df_f["flow_lps"].median())
    else:
        return float(df_f["flow_lps"].median())


# ── Rain event detection ──────────────────────────────────────────────────────

def detect_rain_events(
    df_rainfall: pd.DataFrame,
    threshold_mm: float = _DEFAULT_RAIN_THRESHOLD_MM,
    merge_gap_hours: float = _EVENT_MERGE_GAP_HOURS,
) -> List[RainEvent]:
    """Identify discrete rainfall events.

    Parameters
    ----------
    df_rainfall : DataFrame with columns [timestamp, rainfall_mm]
    threshold_mm : hourly mm threshold to classify a timestep as "raining"
    merge_gap_hours : consecutive dry gaps shorter than this are bridged

    Returns
    -------
    List of RainEvent objects sorted by start time.
    """
    if df_rainfall is None or df_rainfall.empty:
        return []

    df = df_rainfall[["timestamp", "rainfall_mm"]].copy()
    df["timestamp"] = _to_utc_naive(df["timestamp"])
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    if "rainfall_mm" not in df.columns:
        return []
    df["rainfall_mm"] = pd.to_numeric(df["rainfall_mm"], errors="coerce").fillna(0.0)
    df["is_raining"] = df["rainfall_mm"] >= threshold_mm

    events: List[RainEvent] = []
    in_event = False
    event_start: Optional[pd.Timestamp] = None
    event_rows: List[int] = []

    for idx, row in df.iterrows():
        if row["is_raining"]:
            if not in_event:
                in_event = True
                event_start = row["timestamp"]
                event_rows = [idx]
            else:
                event_rows.append(idx)
        else:
            if in_event:
                # Check merge gap: is the dry spell short?
                next_rain = df[(df.index > idx) & df["is_raining"]]
                if not next_rain.empty:
                    gap_h = (next_rain.iloc[0]["timestamp"] - row["timestamp"]).total_seconds() / 3600
                    if gap_h <= merge_gap_hours:
                        continue  # bridge the gap
                # End the event
                event_df = df.loc[event_rows]
                events.append(
                    RainEvent(
                        start=event_start,
                        end=event_df["timestamp"].max(),
                        total_mm=float(event_df["rainfall_mm"].sum()),
                        peak_mm_per_hour=float(event_df["rainfall_mm"].max()),
                        duration_hours=float(
                            (event_df["timestamp"].max() - event_start).total_seconds() / 3600
                        ),
                    )
                )
                in_event = False
                event_rows = []

    # Close any open event at end of data
    if in_event and event_rows:
        event_df = df.loc[event_rows]
        events.append(
            RainEvent(
                start=event_start,
                end=event_df["timestamp"].max(),
                total_mm=float(event_df["rainfall_mm"].sum()),
                peak_mm_per_hour=float(event_df["rainfall_mm"].max()),
                duration_hours=float(
                    (event_df["timestamp"].max() - event_start).total_seconds() / 3600
                ),
            )
        )

    return sorted(events, key=lambda e: e.start)


# ── I/I detection ─────────────────────────────────────────────────────────────

def _severity_from_ratio(ratio: float) -> str:
    """Map response_ratio to severity label."""
    if ratio >= 4.0:
        return "critical"
    if ratio >= 2.5:
        return "high"
    if ratio >= 1.75:
        return "medium"
    return "low"


def detect_inflow_infiltration(
    df_flow: pd.DataFrame,
    df_rainfall: pd.DataFrame,
    baseline: float,
    ii_multiplier: float = _DEFAULT_II_MULTIPLIER,
    post_rain_hours: float = _POST_RAIN_WINDOW_HOURS,
    rain_threshold_mm: float = _DEFAULT_RAIN_THRESHOLD_MM,
) -> RainfallResponse:
    """Detect Inflow & Infiltration (I/I) responses to rainfall events.

    For each detected rain event:
    - Extract flow readings during and up to *post_rain_hours* after the event.
    - If peak flow > baseline × ii_multiplier, flag it as I/I.
    - Compute lag time (rain start → peak flow), response ratio, and confidence.

    Parameters
    ----------
    df_flow     : DataFrame with [timestamp, flow_lps]
    df_rainfall : DataFrame with [timestamp, rainfall_mm]
    baseline    : dry-weather flow baseline in L/s
    ii_multiplier : threshold multiplier; flow > baseline × this → I/I
    post_rain_hours : monitoring window after rain ends
    rain_threshold_mm : mm/hr to classify as raining

    Returns
    -------
    RainfallResponse with all detected flags and recommendations.
    """
    result = RainfallResponse(
        baseline_lps=round(baseline, 2),
        quality_label="Low",
        confidence_score=0.0,
    )

    if df_flow is None or df_flow.empty:
        result.recommendations.append(
            "Insufficient flow data to perform I/I analysis. "
            "Ensure the monitor service is collecting data."
        )
        return result

    df_f = df_flow[["timestamp", "flow_lps"]].copy()
    df_f["timestamp"] = _to_utc_naive(df_f["timestamp"])
    df_f = df_f.dropna(subset=["timestamp", "flow_lps"]).sort_values("timestamp")

    # Compute dry/wet period counts for context
    if df_rainfall is not None and not df_rainfall.empty:
        df_r = df_rainfall[["timestamp", "rainfall_mm"]].copy()
        df_r["timestamp"] = _to_utc_naive(df_r["timestamp"])
        df_r["is_wet"] = df_r["rainfall_mm"].fillna(0) >= rain_threshold_mm
        result.wet_period_count = int(df_r["is_wet"].sum())
        result.dry_period_count = int((~df_r["is_wet"]).sum())

    # Detect events
    events = detect_rain_events(df_rainfall, threshold_mm=rain_threshold_mm)
    result.rain_events = events

    if not events:
        result.recommendations.append(
            f"No rainfall events detected (threshold: {rain_threshold_mm} mm/hr). "
            "All flow in the selected period represents dry-weather conditions."
        )
        result.quality_label = "High"
        result.confidence_score = 90.0
        return result

    # Analyse each event
    ii_flags: List[IIFlag] = []
    for event in events:
        monitor_end = event.end + pd.Timedelta(hours=post_rain_hours)
        window = df_f[
            (df_f["timestamp"] >= event.start) & (df_f["timestamp"] <= monitor_end)
        ]
        if window.empty:
            continue

        peak_flow = float(window["flow_lps"].max())
        peak_time = window.loc[window["flow_lps"].idxmax(), "timestamp"]
        lag_h = (peak_time - event.start).total_seconds() / 3600

        response_ratio = peak_flow / baseline if baseline > 0 else 0.0

        # Z-score of peak flow relative to full-period flow distribution
        flow_std = float(df_f["flow_lps"].std())
        if flow_std > 0:
            z = (peak_flow - baseline) / flow_std
        else:
            z = 0.0
        confidence = min(100.0, 50.0 + z * _Z_SCORE_CONFIDENCE_SCALE)
        confidence = max(10.0, confidence)

        if response_ratio >= ii_multiplier:
            sev = _severity_from_ratio(response_ratio)
            desc = (
                f"Flow rose to {peak_flow:.1f} L/s ({response_ratio:.1f}× baseline) "
                f"{lag_h:.1f} h after rain started "
                f"({event.total_mm:.1f} mm total). "
                f"Severity: {sev.upper()}."
            )
            ii_flags.append(
                IIFlag(
                    rain_event=event,
                    peak_flow_lps=round(peak_flow, 2),
                    baseline_lps=round(baseline, 2),
                    response_ratio=round(response_ratio, 2),
                    lag_hours=round(lag_h, 2),
                    severity=sev,
                    confidence=round(confidence, 1),
                    description=desc,
                )
            )

    result.ii_flags = ii_flags

    # Overall quality assessment
    if ii_flags:
        max_ratio = max(f.response_ratio for f in ii_flags)
        avg_conf = float(np.mean([f.confidence for f in ii_flags]))
        result.confidence_score = round(avg_conf, 1)

        if max_ratio >= 4.0:
            result.quality_label = "Critical"
        elif max_ratio >= 2.5:
            result.quality_label = "High"
        elif max_ratio >= 1.75:
            result.quality_label = "Medium"
        else:
            result.quality_label = "Low"

        # Recommendations
        critical_flags = [f for f in ii_flags if f.severity in ("critical", "high")]
        if critical_flags:
            result.recommendations.append(
                f"{len(critical_flags)} high/critical I/I event(s) detected. "
                "Inspect sewer network for infiltration entry points, particularly "
                "after heavy rainfall. Consider CCTV survey and manhole inspection."
            )
        medium_flags = [f for f in ii_flags if f.severity == "medium"]
        if medium_flags:
            result.recommendations.append(
                f"{len(medium_flags)} moderate I/I event(s) detected. "
                "Monitor trend over time. Increase collection frequency around rain events."
            )
        low_flags = [f for f in ii_flags if f.severity == "low"]
        if low_flags:
            result.recommendations.append(
                f"{len(low_flags)} low-level I/I response(s) detected. "
                "Within acceptable range; no immediate action required."
            )
        lags = [f.lag_hours for f in ii_flags]
        if lags:
            avg_lag = float(np.mean(lags))
            if avg_lag < 1.0:
                result.recommendations.append(
                    f"Very short lag time ({avg_lag:.1f} h) suggests direct inflow "
                    "(surface water entry). Check stormwater connections to sewer."
                )
            elif avg_lag > 6.0:
                result.recommendations.append(
                    f"Long lag time ({avg_lag:.1f} h) suggests groundwater infiltration. "
                    "Inspect pipe joints and manhole seals in the catchment."
                )
    else:
        result.quality_label = "High"
        result.confidence_score = 85.0
        result.recommendations.append(
            f"{len(events)} rainfall event(s) detected but no significant I/I responses found. "
            "Sewer appears tight under the observed rainfall conditions."
        )

    return result
