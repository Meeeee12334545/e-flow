"""
Rainfall analysis and AI Inflow/Infiltration (I/I) detection module for EDS FlowSense (EDS-FS).

Implements hydrological methods to the highest professional standards, including:
- WMO rain event detection and merging
- Antecedent Precipitation Index (API) — Linsley exponential decay model
- Eckhardt (2005) recursive digital filter for baseflow separation
- Recession coefficient analysis (falling-limb exponential fit)
- Lagged cross-correlation with Pearson and Spearman statistics
- I/I severity classification with multi-factor confidence scoring

Public API
----------
compute_antecedent_precipitation_index(df_rainfall)         → pd.Series
compute_dry_weather_baseline(df_flow, df_rainfall)          → float
detect_rain_events(df_rainfall, threshold_mm)               → List[RainEvent]
detect_inflow_infiltration(df_flow, df_rainfall, baseline)  → RainfallResponse
compute_flow_rainfall_correlation(df_flow, df_rainfall)     → FlowRainfallCorrelation | None
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

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
_DEFAULT_RAIN_THRESHOLD_MM  = 1.0    # industry-standard event threshold (mm/hr); BOM/ARR 2019
_DEFAULT_II_MULTIPLIER      = 1.5    # flow > baseline × this → I/I flag
_DRY_DAY_PRECIP_CAP_MM      = 1.0   # hourly mm/hr ≤ this → classified as dry (consistent with event threshold)
_BASELINE_LOOKBACK_DAYS     = 7     # rolling window for dry-weather baseline
_MIN_DRY_READINGS           = 10    # min dry readings to compute baseline
_EVENT_MERGE_GAP_HOURS      = 6     # merge rain events closer than this many hours (ARR 2019)
_POST_RAIN_WINDOW_HOURS     = 24    # hours after rain stops to monitor flow (WSAA WSA 02 standard)
_Z_SCORE_CONFIDENCE_SCALE   = 10.0  # maps z-score to 0-100 confidence boost
_INFLOW_LAG_THRESHOLD_HOURS = 2     # lag ≤ this → direct inflow; > this → infiltration

# Antecedent Precipitation Index (API) — Linsley et al. exponential decay
_API_DECAY_DAILY            = 0.85  # per-day decay coefficient (~6-7 day half-life)

# Eckhardt (2005) recursive digital filter for baseflow separation
_ECKHARDT_ALPHA_DAILY       = 0.925  # baseflow recession constant (per day, daily calibration)
_ECKHARDT_BFI_MAX           = 0.50   # max baseflow index for combined sewer applications

# Unit conversion
_LITERS_PER_CUBIC_METER     = 1000.0  # L → m³ conversion factor

# Statistics
_FISHER_Z_CLIP              = 0.9999  # clamp |r| away from ±1 before arctanh
_Z_SCORE_95_CI              = 1.96    # z-score for 95% confidence interval (two-tailed)


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
    # ── Advanced hydrology fields (may be 0.0 / None when data is insufficient) ──
    excess_volume_m3: float = 0.0          # total flow above baseline during event window (m³)
    api_value: float = 0.0                 # Antecedent Precipitation Index at event start (mm)
    api_class: str = ""                    # Dry / Moist / Wet (AMC-I/II/III)
    quickflow_lps: float = 0.0             # peak quickflow (above baseflow) at event peak
    baseflow_at_peak_lps: float = 0.0     # estimated baseflow at event peak
    quickflow_fraction: float = 0.0        # fraction of peak flow above baseflow (0-1)
    recession_k: Optional[float] = None   # exponential recession coefficient (hr⁻¹)
    recession_type: str = ""              # Fast (<0.1/hr) / Moderate / Slow (>0.01/hr)


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
    # ── Summary hydrology metrics ──
    mean_baseflow_fraction: float = 0.0   # average baseflow / total flow across all I/I events
    mean_api_at_events: float = 0.0       # average API at event starts
    dominant_pathway: str = ""            # Inflow / Infiltration / Mixed (based on lag analysis)


# ── Antecedent Precipitation Index (API) ─────────────────────────────────────

def compute_antecedent_precipitation_index(
    df_rainfall: pd.DataFrame,
    decay_daily: float = _API_DECAY_DAILY,
) -> pd.Series:
    """Compute the Antecedent Precipitation Index (API) at each hourly timestep.

    Uses the Linsley (1958) exponential decay model::

        API(t) = P(t) + k^Δt × API(t-1)

    where k is the daily decay coefficient and Δt is the timestep in days.
    A higher API indicates wetter antecedent soil conditions, which increases
    the likelihood and magnitude of I/I response to a given rainfall event.

    API is classified into three Antecedent Moisture Conditions (AMC):

    - **AMC-I  (Dry)**:   API ≤ 12 mm — low initial abstraction, less I/I expected
    - **AMC-II (Moist)**: API 12–28 mm — moderate conditions
    - **AMC-III (Wet)**:  API > 28 mm  — saturated soils, high I/I risk

    Parameters
    ----------
    df_rainfall : DataFrame with columns [timestamp, rainfall_mm]
    decay_daily : per-day exponential decay coefficient (default: 0.85)

    Returns
    -------
    pd.Series indexed by timestamp containing API values (mm).
    Returns an empty Series if input data is insufficient.
    """
    if df_rainfall is None or df_rainfall.empty or "rainfall_mm" not in df_rainfall.columns:
        return pd.Series(dtype=float)

    df = df_rainfall[["timestamp", "rainfall_mm"]].copy()
    df["timestamp"] = _to_utc_naive(df["timestamp"])
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").set_index("timestamp")
    df["rainfall_mm"] = pd.to_numeric(df["rainfall_mm"], errors="coerce").fillna(0.0)

    # Resample to regular hourly grid (sum precipitation per hour)
    rain_h = df["rainfall_mm"].resample("1h").sum().fillna(0.0)

    if rain_h.empty:
        return pd.Series(dtype=float)

    # Compute per-hour decay factor from daily coefficient
    decay_hourly = decay_daily ** (1.0 / 24.0)

    api = np.zeros(len(rain_h))
    rain_vals = rain_h.values
    for i in range(1, len(rain_vals)):
        api[i] = rain_vals[i] + decay_hourly * api[i - 1]

    return pd.Series(api, index=rain_h.index, name="api_mm")


def _api_class(api_value: float) -> str:
    """Classify API value into AMC-I/II/III (Dry / Moist / Wet)."""
    if api_value > 28.0:
        return "Wet"
    if api_value > 12.0:
        return "Moist"
    return "Dry"


# ── Eckhardt baseflow separation ──────────────────────────────────────────────

def _separate_baseflow_eckhardt(
    flow_series: pd.Series,
    alpha_daily: float = _ECKHARDT_ALPHA_DAILY,
    bfi_max: float = _ECKHARDT_BFI_MAX,
    timestep_hours: float = 1.0,
) -> pd.Series:
    """Eckhardt (2005) recursive digital filter for baseflow separation.

    Separates the total sewer flow into:
    - **Baseflow** (slow component): represents steady infiltration from
      groundwater seeping through pipe joints, deteriorated manholes, and
      defective connections. Baseflow responds slowly to rainfall.
    - **Quickflow** (fast component): total flow minus baseflow; represents
      rapid inflow from direct surface connections, cross-connections, and
      stormwater entry.

    Filter equation (Eckhardt, 2005, Hydrological Processes)::

        b(i) = ((1 - BFI_max) × α × b(i-1) + (1 - α) × BFI_max × Q(i))
               / (1 - α × BFI_max)

    where α is the sub-daily recession constant converted from the daily
    calibration value::

        α_hourly = α_daily^(Δt_days)

    Parameters
    ----------
    flow_series : pd.Series of flow rates (L/s), evenly spaced
    alpha_daily : baseflow recession constant (daily calibration, default 0.925)
    bfi_max     : maximum baseflow index for this catchment type (default 0.50
                  for combined sewer applications)
    timestep_hours : timestep of the input series in hours

    Returns
    -------
    pd.Series of baseflow values (L/s), same index as input.
    """
    if flow_series is None or flow_series.empty:
        return pd.Series(dtype=float)

    q = flow_series.values.astype(float)
    # Clamp negatives to zero (can occur with calibration noise)
    q = np.maximum(q, 0.0)

    # Convert alpha to the sub-daily timestep
    alpha = alpha_daily ** (timestep_hours / 24.0)

    denominator = 1.0 - alpha * bfi_max
    b = np.zeros_like(q)
    b[0] = q[0] * bfi_max  # initialise at BFI_max fraction of initial flow

    for i in range(1, len(q)):
        b_raw = ((1.0 - bfi_max) * alpha * b[i - 1] + (1.0 - alpha) * bfi_max * q[i]) / denominator
        b[i] = min(b_raw, q[i])  # baseflow cannot exceed total flow

    return pd.Series(b, index=flow_series.index, name="baseflow_lps")


# ── Recession coefficient analysis ───────────────────────────────────────────

def _compute_recession_coefficient(
    flow_window: pd.Series,
    peak_time: pd.Timestamp,
) -> Optional[float]:
    """Fit an exponential decay to the post-peak recession limb.

    Models the falling limb as::

        Q(t) = Q_peak × exp(-k × (t - t_peak))

    so k (hr⁻¹) is found by log-linearising: ln(Q/Q_peak) = -k × Δt.
    OLS is applied to the recession limb data.

    Parameters
    ----------
    flow_window : pd.Series of flow values with a DatetimeIndex
    peak_time   : timestamp of the peak flow

    Returns
    -------
    k coefficient (hr⁻¹), or None if the recession cannot be estimated
    (e.g. fewer than 3 post-peak readings or monotonically non-decreasing).
    """
    if flow_window is None or flow_window.empty:
        return None

    flow_window = flow_window.dropna()
    recession = flow_window[flow_window.index >= peak_time].copy()

    if len(recession) < 3:
        return None

    q_peak = recession.iloc[0]
    if q_peak <= 0:
        return None

    # Use only the falling portion (monotonically non-increasing window)
    falling = [q_peak]
    for q in recession.iloc[1:]:
        if q <= falling[-1]:
            falling.append(q)
        else:
            break  # stop at the first re-rise

    if len(falling) < 3:
        return None

    # Time in hours from peak
    t_hours = np.arange(len(falling), dtype=float)
    log_ratio = np.log(np.array(falling) / q_peak)

    # OLS: log_ratio = -k * t  (no intercept)
    k_est, _, r_val, _, _ = scipy_stats.linregress(t_hours, log_ratio)
    k = -k_est  # make positive for "decay rate"

    if k <= 0 or np.isnan(k):
        return None

    return round(float(k), 5)


def _recession_type(k: Optional[float]) -> str:
    """Classify recession coefficient into Fast / Moderate / Slow."""
    if k is None:
        return ""
    if k >= 0.10:
        return "Fast"
    if k >= 0.02:
        return "Moderate"
    return "Slow"


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

    Applies a multi-method hydrology workflow for each detected rain event:

    1. **Event window extraction** — flow from event start to
       *post_rain_hours* after rain ends.
    2. **Antecedent Precipitation Index (API)** — quantifies soil/pipe
       saturation at the event start; wetter antecedent conditions increase
       expected I/I severity.
    3. **Eckhardt baseflow separation** — decomposes flow into slow
       infiltration (baseflow) and fast inflow (quickflow) components.
    4. **Recession coefficient analysis** — fits an exponential decay to
       the falling limb to classify response type (Fast / Moderate / Slow).
    5. **Multi-factor confidence scoring** — combines Z-score, API class,
       and response ratio into a calibrated 0–100 confidence score.
    6. **Excess volume** — integrates flow above baseline over the event
       window to quantify total extraneous flow volume.

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
        df_r_ctx = df_rainfall[["timestamp", "rainfall_mm"]].copy()
        df_r_ctx["timestamp"] = _to_utc_naive(df_r_ctx["timestamp"])
        df_r_ctx["is_wet"] = df_r_ctx["rainfall_mm"].fillna(0) >= rain_threshold_mm
        result.wet_period_count = int(df_r_ctx["is_wet"].sum())
        result.dry_period_count = int((~df_r_ctx["is_wet"]).sum())

    # ── Pre-compute API series ──────────────────────────────────────────────
    api_series = compute_antecedent_precipitation_index(df_rainfall)

    # ── Pre-compute Eckhardt baseflow on the full flow series ───────────────
    df_f_indexed = df_f.set_index("timestamp").sort_index()
    flow_h = df_f_indexed["flow_lps"].resample("1h").mean().interpolate(limit=2)
    baseflow_h = _separate_baseflow_eckhardt(flow_h)

    # ── Detect events ───────────────────────────────────────────────────────
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

    # ── Analyse each event ──────────────────────────────────────────────────
    ii_flags: List[IIFlag] = []
    flow_std = float(df_f["flow_lps"].std())

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

        # ── API at event start ──────────────────────────────────────────
        api_val = 0.0
        if not api_series.empty:
            api_at_start = api_series[api_series.index <= event.start]
            if not api_at_start.empty:
                api_val = float(api_at_start.iloc[-1])
        api_cls = _api_class(api_val)

        # ── Baseflow / quickflow at peak ────────────────────────────────
        bf_at_peak = 0.0
        qf_at_peak = 0.0
        qf_fraction = 0.0
        if not baseflow_h.empty:
            bf_window = baseflow_h[
                (baseflow_h.index >= event.start) & (baseflow_h.index <= monitor_end)
            ]
            if not bf_window.empty:
                # Baseflow at peak: nearest hourly value to peak_time
                diffs = (bf_window.index - peak_time).total_seconds()
                bf_idx = int(np.abs(diffs).argmin())
                bf_at_peak = float(bf_window.iloc[bf_idx])
                qf_at_peak = max(0.0, peak_flow - bf_at_peak)
                qf_fraction = qf_at_peak / peak_flow if peak_flow > 0 else 0.0

        # ── Excess flow volume above baseline ───────────────────────────
        excess_vol_m3 = 0.0
        win_sorted = window.sort_values("timestamp")
        if len(win_sorted) >= 2:
            excess = (win_sorted["flow_lps"] - baseline).clip(lower=0.0)
            dt_s = (
                win_sorted["timestamp"]
                .diff()
                .dt.total_seconds()
                .fillna(0.0)
            )
            excess_vol_m3 = round(float((excess * dt_s).sum()) / _LITERS_PER_CUBIC_METER, 2)  # L/s × s → L → m³

        # ── Recession coefficient ────────────────────────────────────────
        flow_win_idx = df_f_indexed["flow_lps"].loc[
            (df_f_indexed.index >= event.start) & (df_f_indexed.index <= monitor_end)
        ]
        rec_k = _compute_recession_coefficient(flow_win_idx, peak_time)
        rec_type = _recession_type(rec_k)

        # ── Multi-factor confidence score ────────────────────────────────
        # Base: Z-score of peak relative to full distribution
        z = (peak_flow - baseline) / flow_std if flow_std > 0 else 0.0
        confidence = min(100.0, 50.0 + z * _Z_SCORE_CONFIDENCE_SCALE)

        # API boost: wetter antecedent conditions raise confidence for I/I
        api_boost = {"Wet": 8.0, "Moist": 4.0, "Dry": 0.0}.get(api_cls, 0.0)
        confidence = min(100.0, confidence + api_boost)

        # Ratio penalty: very low ratios near threshold are less reliable
        if response_ratio < ii_multiplier * 1.2:
            confidence = max(10.0, confidence - 10.0)

        confidence = max(10.0, confidence)

        if response_ratio >= ii_multiplier:
            sev = _severity_from_ratio(response_ratio)
            pathway = (
                "groundwater infiltration"
                if lag_h > _INFLOW_LAG_THRESHOLD_HOURS
                else "direct inflow"
            )
            desc = (
                f"Flow rose to {peak_flow:.1f} L/s ({response_ratio:.1f}× baseline) "
                f"{lag_h:.1f} h after rain started "
                f"({event.total_mm:.1f} mm over {event.duration_hours:.1f} h). "
                f"Excess volume: {excess_vol_m3:.2f} m³. "
                f"Likely pathway: {pathway}. "
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
                    excess_volume_m3=excess_vol_m3,
                    api_value=round(api_val, 2),
                    api_class=api_cls,
                    quickflow_lps=round(qf_at_peak, 2),
                    baseflow_at_peak_lps=round(bf_at_peak, 2),
                    quickflow_fraction=round(qf_fraction, 3),
                    recession_k=rec_k,
                    recession_type=rec_type,
                )
            )

    result.ii_flags = ii_flags

    # ── Overall quality assessment ──────────────────────────────────────────
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

        # ── Summary pathway determination ───────────────────────────────
        inflow_count = sum(1 for f in ii_flags if f.lag_hours <= _INFLOW_LAG_THRESHOLD_HOURS)
        infilt_count = len(ii_flags) - inflow_count
        if inflow_count > 0 and infilt_count > 0:
            result.dominant_pathway = "Mixed"
        elif inflow_count >= infilt_count:
            result.dominant_pathway = "Inflow"
        else:
            result.dominant_pathway = "Infiltration"

        # ── Summary hydrology metrics ───────────────────────────────────
        qf_fractions = [f.quickflow_fraction for f in ii_flags if f.quickflow_fraction > 0]
        if qf_fractions:
            result.mean_baseflow_fraction = round(1.0 - float(np.mean(qf_fractions)), 3)
        api_vals = [f.api_value for f in ii_flags]
        if api_vals:
            result.mean_api_at_events = round(float(np.mean(api_vals)), 2)

        # ── Recommendations ─────────────────────────────────────────────
        critical_flags = [f for f in ii_flags if f.severity in ("critical", "high")]
        if critical_flags:
            result.recommendations.append(
                f"{len(critical_flags)} high/critical I/I event(s) detected "
                f"(peak ratio up to {max_ratio:.1f}×). "
                "Prioritise CCTV inspection and manhole surveys in the catchment. "
                "Consider smoke or dye testing to identify direct inflow connections."
            )
        medium_flags = [f for f in ii_flags if f.severity == "medium"]
        if medium_flags:
            result.recommendations.append(
                f"{len(medium_flags)} moderate I/I event(s) detected. "
                "Increase monitoring frequency around rain events and review "
                "any recent sewer rehabilitation or maintenance activity."
            )
        low_flags = [f for f in ii_flags if f.severity == "low"]
        if low_flags:
            result.recommendations.append(
                f"{len(low_flags)} low-level I/I response(s) detected. "
                "Within acceptable range under the observed rainfall intensities; "
                "continue routine monitoring."
            )

        lags = [f.lag_hours for f in ii_flags]
        if lags:
            avg_lag = float(np.mean(lags))
            if avg_lag < 1.0:
                result.recommendations.append(
                    f"Very short mean lag time ({avg_lag:.1f} h) is consistent with "
                    "direct surface inflow — likely stormwater cross-connections or "
                    "open manhole lids. Inspect surface inlets in the sub-catchment."
                )
            elif avg_lag <= _INFLOW_LAG_THRESHOLD_HOURS:
                result.recommendations.append(
                    f"Short mean lag ({avg_lag:.1f} h) indicates rapid inflow response. "
                    "Inspect for stormwater or roof-drainage connections to the sewer."
                )
            elif avg_lag > 6.0:
                result.recommendations.append(
                    f"Long mean lag time ({avg_lag:.1f} h) is characteristic of "
                    "groundwater infiltration through defective pipe joints or "
                    "deteriorated manhole seals. Prioritise pipe condition assessment."
                )

        # API-based recommendation
        wet_events = [f for f in ii_flags if f.api_class == "Wet"]
        if wet_events:
            result.recommendations.append(
                f"{len(wet_events)} I/I event(s) occurred under wet antecedent conditions "
                f"(API > 28 mm) — the sewer catchment shows elevated saturation sensitivity. "
                "Groundwater table monitoring is recommended near the affected reach."
            )

        # Recession-based recommendation
        fast_rec = [f for f in ii_flags if f.recession_type == "Fast"]
        slow_rec = [f for f in ii_flags if f.recession_type == "Slow"]
        if fast_rec:
            result.recommendations.append(
                f"{len(fast_rec)} event(s) showed a fast recession response "
                f"(k ≥ 0.10 hr⁻¹), indicating that elevated flows drain quickly — "
                "consistent with direct surface inflow rather than sustained infiltration."
            )
        if slow_rec:
            result.recommendations.append(
                f"{len(slow_rec)} event(s) showed a slow recession response "
                f"(k < 0.02 hr⁻¹), indicating prolonged elevated flow after rain — "
                "consistent with groundwater infiltration through structural defects."
            )
    else:
        result.quality_label = "High"
        result.confidence_score = 85.0
        result.recommendations.append(
            f"{len(events)} rainfall event(s) detected but no significant I/I responses found. "
            "Sewer appears tight under the observed rainfall conditions. "
            "Continue monitoring to build a longer event record."
        )

    return result


# ── Flow–Rainfall Correlation ─────────────────────────────────────────────────

@dataclass
class FlowRainfallCorrelation:
    """Cross-correlation analysis between flow rate and rainfall."""
    pearson_r: float               # instantaneous (lag-0) Pearson correlation
    r_squared: float               # R² at lag-0
    p_value: float                 # two-tailed p-value for lag-0 Pearson test
    best_lag_hours: float          # lag (hours) that maximises |cross-correlation|
    correlation_at_best_lag: float
    sample_size: int               # number of matched hourly samples
    quality_label: str             # None / Weak / Moderate / Strong
    interpretation: str            # plain-English summary
    spearman_r: float = 0.0        # Spearman rank correlation (lag-0, robust to non-linearity)
    p_value_spearman: float = 1.0  # two-tailed p-value for Spearman test
    pearson_ci_low: float = 0.0    # 95% CI lower bound for Pearson r (Fisher z transform)
    pearson_ci_high: float = 0.0   # 95% CI upper bound for Pearson r (Fisher z transform)


def compute_flow_rainfall_correlation(
    df_flow: pd.DataFrame,
    df_rainfall: pd.DataFrame,
    max_lag_hours: int = 24,
) -> Optional[FlowRainfallCorrelation]:
    """Compute Pearson and Spearman correlations and cross-correlation between
    flow and rainfall.

    Both time series are resampled to 1-hour buckets (rainfall summed,
    flow averaged).  A lagged cross-correlation search finds the lag
    (0–*max_lag_hours* hours) at which rainfall best predicts future flow.

    Additionally computes:
    - **Spearman rank correlation** — robust to non-linear relationships and
      resistant to outliers; recommended as a complementary metric alongside
      Pearson (Helsel & Hirsch, 2002, USGS TWRI Book 4).
    - **95% confidence interval for Pearson r** using the Fisher Z
      transformation (Fisher, 1915).

    Parameters
    ----------
    df_flow : DataFrame with columns [timestamp, flow_lps]
    df_rainfall : DataFrame with columns [timestamp, rainfall_mm]
    max_lag_hours : upper bound for the lag search (hours)

    Returns
    -------
    FlowRainfallCorrelation, or None if there is insufficient data
    (fewer than 10 matched hourly pairs).
    """
    if df_flow is None or df_flow.empty or "flow_lps" not in df_flow.columns:
        return None
    if df_rainfall is None or df_rainfall.empty or "rainfall_mm" not in df_rainfall.columns:
        return None

    # Convert and clean
    df_f = df_flow[["timestamp", "flow_lps"]].copy()
    df_f["timestamp"] = _to_utc_naive(df_f["timestamp"])
    df_f = df_f.dropna(subset=["timestamp", "flow_lps"]).set_index("timestamp").sort_index()

    df_r = df_rainfall[["timestamp", "rainfall_mm"]].copy()
    df_r["timestamp"] = _to_utc_naive(df_r["timestamp"])
    df_r = df_r.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()

    # Resample both to hourly (sum rainfall, mean flow)
    flow_h = df_f["flow_lps"].resample("1h").mean().dropna()
    rain_h = df_r["rainfall_mm"].resample("1h").sum()

    # Align on common index
    combined = pd.DataFrame({"flow": flow_h, "rain": rain_h}).dropna()
    if len(combined) < 10:
        return None

    flow_vals = combined["flow"].values
    rain_vals = combined["rain"].values
    n = len(flow_vals)

    # ── Pearson correlation (lag-0) ─────────────────────────────────────────
    r, p_value = scipy_stats.pearsonr(rain_vals, flow_vals)
    r_sq = r ** 2

    # 95% confidence interval via Fisher Z transformation
    # z = arctanh(r), CI: z ± 1.96 / sqrt(n-3), then back-transform
    if n > 3:
        z_fisher = np.arctanh(np.clip(r, -_FISHER_Z_CLIP, _FISHER_Z_CLIP))
        se = 1.0 / np.sqrt(n - 3)
        ci_low = float(np.tanh(z_fisher - _Z_SCORE_95_CI * se))
        ci_high = float(np.tanh(z_fisher + _Z_SCORE_95_CI * se))
    else:
        ci_low = float(r)
        ci_high = float(r)

    # ── Spearman rank correlation (lag-0) ───────────────────────────────────
    spearman_r, p_value_sp = scipy_stats.spearmanr(rain_vals, flow_vals)

    # ── Lagged cross-correlation ────────────────────────────────────────────
    best_lag = 0
    best_corr = abs(r)
    for lag in range(1, min(max_lag_hours + 1, n - 1)):
        try:
            r_lag, _ = scipy_stats.pearsonr(rain_vals[:-lag], flow_vals[lag:])
            if abs(r_lag) > best_corr:
                best_corr = abs(r_lag)
                best_lag = lag
        except Exception:
            break

    # ── Quality label (based on Pearson |r| at lag-0) ──────────────────────
    abs_r = abs(r)
    if abs_r >= 0.7:
        quality = "Strong"
    elif abs_r >= 0.4:
        quality = "Moderate"
    elif abs_r >= 0.2:
        quality = "Weak"
    else:
        quality = "None"

    # ── Plain-English interpretation ────────────────────────────────────────
    direction = "positive" if r >= 0 else "negative"
    sig_str = "p < 0.001" if p_value < 0.001 else f"p = {p_value:.3f}"
    sp_sig_str = "p < 0.001" if p_value_sp < 0.001 else f"p = {p_value_sp:.3f}"

    interp_parts = [
        f"Pearson r = {r:.3f} ({quality.lower()} {direction} correlation, "
        f"R² = {r_sq:.3f}, {sig_str}; "
        f"95% CI [{ci_low:.3f}, {ci_high:.3f}]). "
        f"Spearman ρ = {spearman_r:.3f} ({sp_sig_str})."
    ]
    if best_lag == 0:
        interp_parts.append(
            "Flow responds with no measurable lag — consistent with direct surface "
            "inflow or a very short hydraulic travel time in the catchment."
        )
    else:
        pathway = "inflow" if best_lag <= _INFLOW_LAG_THRESHOLD_HOURS else "groundwater infiltration"
        interp_parts.append(
            f"Flow is most strongly correlated with rainfall {best_lag} hour(s) earlier "
            f"(cross-correlation {best_corr:.3f}) — consistent with {pathway} response."
        )

    return FlowRainfallCorrelation(
        pearson_r=round(float(r), 4),
        r_squared=round(float(r_sq), 4),
        p_value=round(float(p_value), 6),
        best_lag_hours=float(best_lag),
        correlation_at_best_lag=round(float(best_corr), 4),
        sample_size=n,
        quality_label=quality,
        interpretation=" ".join(interp_parts),
        spearman_r=round(float(spearman_r), 4),
        p_value_spearman=round(float(p_value_sp), 6),
        pearson_ci_low=round(ci_low, 4),
        pearson_ci_high=round(ci_high, 4),
    )

