"""
AI-driven anomaly detection engine for e-flow EDS DAS.

Implements rule-based and statistical models to identify questionable or
abnormal sensor data, providing confidence scores and anomaly classifications.

Detection types:
  - Flatline: sensor stuck / identical repeated values
  - Spike: sudden unrealistic jumps (rate-of-change)
  - Dropout: missing / null data gaps
  - Out-of-range: values outside physical bounds
  - Velocity-depth inconsistency: hydraulic logic check
  - Z-score: statistical deviation from rolling mean
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Physical plausibility bounds ──────────────────────────────────────────
BOUNDS = {
    "depth_mm": (0.0, 3000.0),       # 0 – 3 000 mm
    "velocity_mps": (-5.0, 10.0),    # negative = reverse flow allowed
    "flow_lps": (-500.0, 5000.0),    # L/s
}

# Thresholds that can be tuned
FLATLINE_MIN_CONSECUTIVE = 5          # ≥N identical values = flatline
SPIKE_RATE_LIMITS = {                 # max allowable change per minute
    "depth_mm": 500.0,                # mm/min
    "velocity_mps": 3.0,              # m/s per minute
    "flow_lps": 1000.0,               # L/s per minute
}
ZSCORE_WINDOW = 20                    # rolling window for Z-score baseline
ZSCORE_THRESHOLD = 3.5               # |Z| > threshold → anomaly
DROPOUT_GAP_MINUTES = 5.0            # gap > N minutes = dropout
VELOCITY_DEPTH_MIN_DEPTH = 20.0      # mm below which we skip hydraulic check
VELOCITY_DEPTH_MAX_RATIO = 0.05      # max velocity (m/s) per mm of depth

# Anomaly severity labels
SEVERITY_ANOMALY = "anomaly"         # red
SEVERITY_WARNING = "warning"         # amber


@dataclass
class AnomalyFlag:
    """A single anomaly flag for a data point."""
    index: int                        # DataFrame row index
    timestamp: pd.Timestamp
    column: str                       # which sensor column
    anomaly_type: str                 # flatline | spike | dropout | out_of_range | velocity_depth | zscore
    severity: str                     # anomaly | warning
    description: str
    value: Optional[float] = None
    z_score: Optional[float] = None


@dataclass
class AnomalyReport:
    """Full anomaly analysis result for a DataFrame."""
    flags: List[AnomalyFlag] = field(default_factory=list)
    confidence_score: float = 100.0  # 0–100, higher = better data quality
    quality_label: str = "High"      # High / Medium / Low
    pct_valid: float = 100.0
    pct_flagged: float = 0.0
    summary: str = "No issues detected"

    # Per-type counts for display
    flatline_count: int = 0
    spike_count: int = 0
    dropout_count: int = 0
    out_of_range_count: int = 0
    velocity_depth_count: int = 0
    zscore_count: int = 0

    def flagged_indices(self) -> set:
        return {f.index for f in self.flags}

    def flags_by_index(self) -> Dict[int, List[AnomalyFlag]]:
        result: Dict[int, List[AnomalyFlag]] = {}
        for f in self.flags:
            result.setdefault(f.index, []).append(f)
        return result


# ── Individual detectors ──────────────────────────────────────────────────

def detect_out_of_range(df: pd.DataFrame, columns: List[str]) -> List[AnomalyFlag]:
    """Flag values outside physically plausible bounds."""
    flags: List[AnomalyFlag] = []
    for col in columns:
        if col not in df.columns or col not in BOUNDS:
            continue
        lo, hi = BOUNDS[col]
        series = pd.to_numeric(df[col], errors="coerce")
        for idx in df.index:
            val = series.loc[idx]
            if pd.isna(val):
                continue
            if val < lo or val > hi:
                flags.append(AnomalyFlag(
                    index=idx,
                    timestamp=pd.Timestamp(df.loc[idx, "timestamp"]),
                    column=col,
                    anomaly_type="out_of_range",
                    severity=SEVERITY_ANOMALY,
                    description=f"{col}={val:.3f} outside bounds [{lo}, {hi}]",
                    value=float(val),
                ))
    return flags


def detect_flatline(df: pd.DataFrame, columns: List[str]) -> List[AnomalyFlag]:
    """Detect sequences where a sensor outputs the same value consecutively."""
    flags: List[AnomalyFlag] = []
    for col in columns:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").reset_index(drop=True)
        original_indices = list(df.index)
        n = len(series)
        i = 0
        while i < n:
            if pd.isna(series.iloc[i]):
                i += 1
                continue
            j = i + 1
            while j < n and not pd.isna(series.iloc[j]) and series.iloc[j] == series.iloc[i]:
                j += 1
            run_length = j - i
            if run_length >= FLATLINE_MIN_CONSECUTIVE:
                # Flag every point in the flatline run
                for k in range(i, j):
                    orig_idx = original_indices[k]
                    flags.append(AnomalyFlag(
                        index=orig_idx,
                        timestamp=pd.Timestamp(df.loc[orig_idx, "timestamp"]),
                        column=col,
                        anomaly_type="flatline",
                        severity=SEVERITY_ANOMALY,
                        description=f"{col} flatline ({series.iloc[i]:.3f}) for {run_length} consecutive readings",
                        value=float(series.iloc[i]),
                    ))
            i = j
    return flags


def detect_spikes(df: pd.DataFrame, columns: List[str]) -> List[AnomalyFlag]:
    """Detect sudden unrealistic rate-of-change (spikes)."""
    flags: List[AnomalyFlag] = []
    if len(df) < 2:
        return flags

    dfx = df.sort_values("timestamp").copy()
    ts_seconds = pd.to_datetime(dfx["timestamp"]).astype("int64") / 1e9

    for col in columns:
        if col not in dfx.columns or col not in SPIKE_RATE_LIMITS:
            continue
        max_rate = SPIKE_RATE_LIMITS[col]
        series = pd.to_numeric(dfx[col], errors="coerce").values
        ts_vals = ts_seconds.values
        n = len(series)

        for i in range(1, n):
            v_prev, v_curr = series[i - 1], series[i]
            if pd.isna(v_prev) or pd.isna(v_curr):
                continue
            dt_minutes = (ts_vals[i] - ts_vals[i - 1]) / 60.0
            if dt_minutes <= 0:
                continue
            rate = abs(v_curr - v_prev) / dt_minutes
            if rate > max_rate:
                orig_idx = dfx.index[i]
                flags.append(AnomalyFlag(
                    index=orig_idx,
                    timestamp=pd.Timestamp(dfx.loc[orig_idx, "timestamp"]),
                    column=col,
                    anomaly_type="spike",
                    severity=SEVERITY_ANOMALY,
                    description=f"{col} spike: rate {rate:.1f}/min exceeds {max_rate}/min limit",
                    value=float(v_curr),
                ))
    return flags


def detect_dropouts(df: pd.DataFrame) -> List[AnomalyFlag]:
    """Detect gaps in the timestamp sequence indicating missing data."""
    flags: List[AnomalyFlag] = []
    if len(df) < 2:
        return flags

    dfx = df.sort_values("timestamp").copy()
    timestamps = pd.to_datetime(dfx["timestamp"])
    indices = list(dfx.index)

    for i in range(1, len(timestamps)):
        gap_minutes = (timestamps.iloc[i] - timestamps.iloc[i - 1]).total_seconds() / 60.0
        if gap_minutes > DROPOUT_GAP_MINUTES:
            orig_idx = indices[i]
            flags.append(AnomalyFlag(
                index=orig_idx,
                timestamp=timestamps.iloc[i],
                column="timestamp",
                anomaly_type="dropout",
                severity=SEVERITY_WARNING,
                description=f"Data gap of {gap_minutes:.1f} min before this reading",
                value=gap_minutes,
            ))
    return flags


def detect_velocity_depth_inconsistency(df: pd.DataFrame) -> List[AnomalyFlag]:
    """Basic hydraulic logic: very high velocity with very low depth is suspicious."""
    flags: List[AnomalyFlag] = []
    if "velocity_mps" not in df.columns or "depth_mm" not in df.columns:
        return flags

    for idx in df.index:
        depth = pd.to_numeric(df.loc[idx, "depth_mm"], errors="coerce")
        velocity = pd.to_numeric(df.loc[idx, "velocity_mps"], errors="coerce")
        if pd.isna(depth) or pd.isna(velocity):
            continue
        if depth < VELOCITY_DEPTH_MIN_DEPTH:
            continue  # Too shallow – sensor may be dry, skip
        # Max expected velocity scales with depth
        expected_max_vel = depth * VELOCITY_DEPTH_MAX_RATIO
        if velocity > expected_max_vel and velocity > 0.5:
            flags.append(AnomalyFlag(
                index=idx,
                timestamp=pd.Timestamp(df.loc[idx, "timestamp"]),
                column="velocity_mps",
                anomaly_type="velocity_depth",
                severity=SEVERITY_WARNING,
                description=(
                    f"Velocity {velocity:.3f} m/s unusually high for depth {depth:.0f} mm "
                    f"(expected ≤{expected_max_vel:.2f} m/s)"
                ),
                value=float(velocity),
            ))
    return flags


def detect_zscore_anomalies(df: pd.DataFrame, columns: List[str]) -> List[AnomalyFlag]:
    """Rolling Z-score anomaly detection using a sliding window."""
    flags: List[AnomalyFlag] = []
    if len(df) < ZSCORE_WINDOW + 1:
        return flags

    dfx = df.sort_values("timestamp").copy()

    for col in columns:
        if col not in dfx.columns:
            continue
        series = pd.to_numeric(dfx[col], errors="coerce")
        rolling_mean = series.rolling(window=ZSCORE_WINDOW, min_periods=max(3, ZSCORE_WINDOW // 4)).mean()
        rolling_std = series.rolling(window=ZSCORE_WINDOW, min_periods=max(3, ZSCORE_WINDOW // 4)).std()

        for i, idx in enumerate(dfx.index):
            val = series.loc[idx]
            mu = rolling_mean.loc[idx]
            sigma = rolling_std.loc[idx]
            if pd.isna(val) or pd.isna(mu) or pd.isna(sigma) or sigma < 1e-9:
                continue
            z = (val - mu) / sigma
            if abs(z) > ZSCORE_THRESHOLD:
                flags.append(AnomalyFlag(
                    index=idx,
                    timestamp=pd.Timestamp(dfx.loc[idx, "timestamp"]),
                    column=col,
                    anomaly_type="zscore",
                    severity=SEVERITY_ANOMALY if abs(z) > ZSCORE_THRESHOLD * 1.3 else SEVERITY_WARNING,
                    description=f"{col} Z-score {z:.2f} (threshold ±{ZSCORE_THRESHOLD})",
                    value=float(val),
                    z_score=float(z),
                ))
    return flags


# ── Main analysis function ─────────────────────────────────────────────────

def run_anomaly_detection(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> AnomalyReport:
    """
    Run all anomaly detectors on *df* and return an :class:`AnomalyReport`.

    Parameters
    ----------
    df:
        DataFrame with at minimum a ``timestamp`` column and one or more
        sensor columns (``depth_mm``, ``velocity_mps``, ``flow_lps``).
    columns:
        Sensor columns to analyse.  Defaults to all available among the
        standard three.
    """
    report = AnomalyReport()

    if df is None or df.empty:
        report.summary = "No data available for analysis"
        return report

    if columns is None:
        columns = [c for c in ("depth_mm", "velocity_mps", "flow_lps") if c in df.columns]

    if not columns:
        report.summary = "No sensor columns found"
        return report

    all_flags: List[AnomalyFlag] = []

    try:
        all_flags += detect_out_of_range(df, columns)
        all_flags += detect_flatline(df, columns)
        all_flags += detect_spikes(df, columns)
        all_flags += detect_dropouts(df)
        all_flags += detect_velocity_depth_inconsistency(df)
        all_flags += detect_zscore_anomalies(df, columns)
    except Exception as exc:
        logger.warning("Anomaly detection error: %s", exc, exc_info=True)

    report.flags = all_flags

    # Count per type (deduplicate index+type for counting)
    seen: set = set()
    for f in all_flags:
        key = (f.index, f.anomaly_type)
        if key not in seen:
            seen.add(key)
            if f.anomaly_type == "flatline":
                report.flatline_count += 1
            elif f.anomaly_type == "spike":
                report.spike_count += 1
            elif f.anomaly_type == "dropout":
                report.dropout_count += 1
            elif f.anomaly_type == "out_of_range":
                report.out_of_range_count += 1
            elif f.anomaly_type == "velocity_depth":
                report.velocity_depth_count += 1
            elif f.anomaly_type == "zscore":
                report.zscore_count += 1

    total_rows = len(df)
    flagged_rows = len(report.flagged_indices())
    report.pct_flagged = (flagged_rows / total_rows * 100) if total_rows else 0.0
    report.pct_valid = 100.0 - report.pct_flagged

    # Confidence score: start at 100, penalise by anomaly fraction and severity
    anomaly_count = sum(1 for f in all_flags if f.severity == SEVERITY_ANOMALY)
    warning_count = sum(1 for f in all_flags if f.severity == SEVERITY_WARNING)
    penalty = min(60, (anomaly_count * 3 + warning_count * 1.5) / max(1, total_rows) * 100)
    report.confidence_score = max(0.0, round(100.0 - penalty, 1))

    if report.confidence_score >= 80:
        report.quality_label = "High"
    elif report.confidence_score >= 50:
        report.quality_label = "Medium"
    else:
        report.quality_label = "Low"

    # Summary text
    if not all_flags:
        report.summary = "No issues detected"
    else:
        parts = []
        if report.flatline_count:
            parts.append(f"{report.flatline_count} flatline reading(s)")
        if report.spike_count:
            parts.append(f"{report.spike_count} spike(s)")
        if report.dropout_count:
            parts.append(f"{report.dropout_count} data gap(s)")
        if report.out_of_range_count:
            parts.append(f"{report.out_of_range_count} out-of-range value(s)")
        if report.velocity_depth_count:
            parts.append(f"{report.velocity_depth_count} velocity/depth inconsistenc(ies)")
        if report.zscore_count:
            parts.append(f"{report.zscore_count} statistical outlier(s)")
        report.summary = "; ".join(parts)

    return report


def apply_overrides(
    report: AnomalyReport,
    overrides: List[Dict],
) -> AnomalyReport:
    """
    Remove flags that have been overridden by an admin.

    Parameters
    ----------
    overrides:
        List of dicts with keys ``index``, ``column``, ``anomaly_type``
        identifying flags to suppress.
    """
    if not overrides:
        return report
    override_keys = {
        (o.get("index"), o.get("column"), o.get("anomaly_type"))
        for o in overrides
    }
    report.flags = [
        f for f in report.flags
        if (f.index, f.column, f.anomaly_type) not in override_keys
    ]
    return report
