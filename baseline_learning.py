"""
Site baseline learning and alarm advisory engine for EDS FlowSense (EDS-FS).

Analyses the long-term history of a monitoring site and produces:
  - Data sufficiency assessment (how much data exists and what analyses are unlocked)
  - Per-variable diurnal profiles (24-hour median / IQR bands)
  - Dry-weather-flow (DWF) diurnal profiles (rainfall-masked)
  - Day-of-week profiles (weekly pattern detection)
  - Full distribution statistics (P5 … P99)
  - Linear trend analysis per variable
  - Data-driven alarm level recommendations at three sensitivity levels

Public API
----------
check_data_sufficiency(df)                          → DataSufficiency
compute_site_baseline(df, device_id)                → SiteBaseline
compute_dwf_diurnal_profile(df, variable, df_rain)  → DiurnalProfile | None
generate_alarm_recommendations(site_baseline)        → List[AlarmRecommendation]
baseline_to_json(site_baseline)                      → str
baseline_from_json(json_str)                         → SiteBaseline
build_intelligence_pdf(device_name, baseline, recs)  → bytes
"""

from __future__ import annotations

import html
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_MIN_READINGS_EARLY = 100           # ≥100 readings + ≥1 day → early analysis
_MIN_DAYS_EARLY     = 1.0
_MIN_READINGS_BASIC = 5_000
_MIN_DAYS_BASIC     = 7
_MIN_DAYS_FULL      = 30
_MIN_DAYS_SEASONAL  = 90

# ── Sensor metadata ────────────────────────────────────────────────────────────
SENSOR_VARIABLES = ["depth_mm", "velocity_mps", "flow_lps"]

_SENSOR_META: Dict[str, Dict] = {
    "depth_mm":     {"label": "Water Depth",   "unit": "mm",  "precision": 1, "directions": ["above", "below"]},
    "velocity_mps": {"label": "Flow Velocity", "unit": "m/s", "precision": 3, "directions": ["above"]},
    "flow_lps":     {"label": "Flow Rate",     "unit": "L/s", "precision": 1, "directions": ["above"]},
}

_LEVEL_LABELS = {
    "low_warning":  "Low Warning",
    "high_warning": "High Warning",
    "critical":     "Critical",
}

_SENSITIVITY_LABELS = {
    "conservative": "Conservative",
    "standard":     "Standard",
    "sensitive":    "Sensitive",
}

_DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DataSufficiency:
    """How much data exists for a device and what analyses are currently possible."""
    total_readings: int
    days_covered: float
    readings_per_day: float
    has_early: bool        # ≥ 1 day & ≥ 100 readings — preliminary stats only
    has_basic: bool        # ≥ 7 days & ≥ 5,000 readings
    has_full: bool         # ≥ 30 days
    has_seasonal: bool     # ≥ 90 days
    status: str            # insufficient | early | basic | full | seasonal
    status_description: str
    next_level_description: str
    estimated_days_to_next: Optional[int]


@dataclass
class DiurnalProfile:
    """Per-hour-of-day statistics for one sensor variable."""
    variable: str
    hours: List[int]         # 0 – 23
    median: List[float]
    p10: List[float]
    p25: List[float]
    p75: List[float]
    p90: List[float]
    counts: List[int]


@dataclass
class DayOfWeekProfile:
    """Per-day-of-week statistics for one sensor variable."""
    variable: str
    days: List[int]          # 0 = Monday … 6 = Sunday
    day_names: List[str]
    median: List[float]
    p25: List[float]
    p75: List[float]
    counts: List[int]


@dataclass
class DistributionStats:
    """Full distribution statistics for one sensor variable."""
    variable: str
    count: int
    mean: float
    std: float
    # Key percentiles — stored as a dict keyed by integer percentile value
    percentiles: Dict[int, float]   # 1, 5, 10, 25, 50, 75, 85, 90, 92, 95, 97, 99
    iqr: float
    data_min: float
    data_max: float


@dataclass
class TrendResult:
    """Linear trend result for one sensor variable over the full dataset."""
    variable: str
    slope_per_day: float      # units per day (positive = increasing over time)
    r_squared: float
    direction: str            # stable | gradual_increase | gradual_decrease |
                              # significant_increase | significant_decrease
    direction_label: str      # human-readable e.g. "Gradual Increase ↑"
    days_covered: float
    slope_description: str    # e.g. "+2.4 mm/day"
    p_value: float            # statistical significance (two-tailed)


@dataclass
class BaselineProfile:
    """Complete learned profile for one sensor variable."""
    variable: str
    distribution: DistributionStats
    diurnal: DiurnalProfile
    dow: DayOfWeekProfile
    trend: TrendResult


@dataclass
class AlarmRecommendation:
    """A single recommended alarm threshold derived from site data."""
    variable: str
    variable_label: str
    direction: str            # above | below
    level_name: str           # low_warning | high_warning | critical
    level_label: str
    recommended_value: float
    unit: str
    sensitivity: str          # conservative | standard | sensitive
    sensitivity_label: str
    basis: str                # plain-English derivation
    estimated_fp_pct: float   # estimated false-positive rate (%)


@dataclass
class SiteBaseline:
    """Top-level learned baseline for one monitoring site."""
    device_id: str
    computed_at: str          # ISO 8601 UTC timestamp
    readings_used: int
    days_covered: float
    sufficiency: DataSufficiency
    profiles: Dict[str, BaselineProfile]   # keyed by variable name
    status: str               # mirrors sufficiency.status


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _sanitize_for_json(obj):
    """Recursively replace NaN/inf floats with None for safe JSON serialisation."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def baseline_to_json(baseline: SiteBaseline) -> str:
    """Serialise a SiteBaseline to a compact JSON string.

    NaN and inf float values are replaced with ``null`` before encoding so
    the result is always valid JSON (handles early-stage sparse profiles).
    """
    return json.dumps(_sanitize_for_json(asdict(baseline)))


def _json_default(obj):
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def baseline_from_json(json_str: str) -> Optional[SiteBaseline]:
    """Deserialise a SiteBaseline from a JSON string. Returns None on failure."""
    try:
        d = json.loads(json_str)
        # Reconstruct nested dataclasses from dict — handle schema additions gracefully
        suf_d = d["sufficiency"]
        # Backward-compat: older baselines pre-date the has_early field
        suf_d.setdefault("has_early", suf_d.get("has_basic", False))
        suf = DataSufficiency(**suf_d)
        profiles: Dict[str, BaselineProfile] = {}
        for var, pd_dict in d.get("profiles", {}).items():
            dist_d = pd_dict["distribution"]
            dist_d["percentiles"] = {int(k): v for k, v in dist_d["percentiles"].items()}
            dist = DistributionStats(**dist_d)
            diurnal = DiurnalProfile(**pd_dict["diurnal"])
            dow = DayOfWeekProfile(**pd_dict["dow"])
            trend = TrendResult(**pd_dict["trend"])
            profiles[var] = BaselineProfile(
                variable=var,
                distribution=dist,
                diurnal=diurnal,
                dow=dow,
                trend=trend,
            )
        return SiteBaseline(
            device_id=d["device_id"],
            computed_at=d["computed_at"],
            readings_used=d["readings_used"],
            days_covered=d["days_covered"],
            sufficiency=suf,
            profiles=profiles,
            status=d["status"],
        )
    except Exception as exc:
        logger.warning("baseline_from_json failed: %s", exc)
        return None


# ── Core analysis functions ───────────────────────────────────────────────────

def check_data_sufficiency(df: pd.DataFrame) -> DataSufficiency:
    """Return a DataSufficiency summary for *df*.

    *df* must contain a ``timestamp`` column (any format accepted by pd.to_datetime).

    Status progression:
        insufficient → early (≥1 day, ≥100 readings) → basic (≥7 days, ≥5 000 readings)
                     → full (≥30 days) → seasonal (≥90 days)
    """
    empty = DataSufficiency(
        total_readings=0, days_covered=0.0, readings_per_day=0.0,
        has_early=False, has_basic=False, has_full=False, has_seasonal=False,
        status="insufficient",
        status_description=(
            "No data is available for this device yet. Start data collection to enable site intelligence analysis."
        ),
        next_level_description=(
            f"Collect at least 1 day and {_MIN_READINGS_EARLY:,} readings to unlock early-stage analysis."
        ),
        estimated_days_to_next=None,
    )

    if df is None or df.empty or "timestamp" not in df.columns:
        return empty

    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dropna()
    if len(ts) < 2:
        return empty

    total = len(df)
    days = (ts.max() - ts.min()).total_seconds() / 86400.0
    rpd = total / max(days, 0.01)

    has_early    = days >= _MIN_DAYS_EARLY and total >= _MIN_READINGS_EARLY
    has_basic    = days >= _MIN_DAYS_BASIC and total >= _MIN_READINGS_BASIC
    has_full     = days >= _MIN_DAYS_FULL
    has_seasonal = days >= _MIN_DAYS_SEASONAL

    if has_seasonal:
        status = "seasonal"
        status_desc = (
            f"Excellent — {days:.0f} days of data ({total:,} readings) enables full seasonal "
            f"trend analysis and highly accurate alarm recommendations."
        )
        next_desc = "All analysis levels are unlocked. Recommendations will improve as more data is collected."
        days_to_next = None
    elif has_full:
        status = "full"
        status_desc = (
            f"Full diurnal and weekly pattern analysis is available with {days:.0f} days of data "
            f"({total:,} readings)."
        )
        days_needed = max(1, int(_MIN_DAYS_SEASONAL - days))
        next_desc = f"Collect {days_needed} more days to unlock seasonal trend analysis."
        days_to_next = days_needed
    elif has_basic:
        status = "basic"
        status_desc = (
            f"Basic statistical analysis is available with {days:.0f} days of data ({total:,} readings). "
            f"Alarm recommendations are available but will improve with more data."
        )
        days_needed = max(1, int(_MIN_DAYS_FULL - days))
        next_desc = f"Collect {days_needed} more days to unlock full diurnal pattern analysis."
        days_to_next = days_needed
    elif has_early:
        status = "early"
        days_needed = max(1, int(_MIN_DAYS_BASIC - days))
        readings_needed = max(0, _MIN_READINGS_BASIC - total)
        status_desc = (
            f"Early-stage analysis available — {total:,} readings covering {days:.1f} day(s). "
            f"Preliminary diurnal profiles and statistics are shown with caveats. "
            f"Alarm threshold recommendations require at least {_MIN_DAYS_BASIC} days and "
            f"{_MIN_READINGS_BASIC:,} readings for statistical reliability."
        )
        if rpd > 0:
            days_to_next = max(days_needed, max(1, int(readings_needed / rpd)))
            next_desc = (
                f"At the current collection rate ({rpd:.0f} readings/day), basic analysis will be "
                f"available in approximately {days_to_next} more day(s)."
            )
        else:
            days_to_next = days_needed
            next_desc = f"Collect {days_needed} more days to unlock basic analysis."
    else:
        status = "insufficient"
        days_needed = max(1, int(_MIN_DAYS_EARLY - days + 1))
        readings_needed = max(0, _MIN_READINGS_EARLY - total)
        status_desc = (
            f"Insufficient data — {total:,} readings covering {days:.1f} days. "
            f"A minimum of 1 day and {_MIN_READINGS_EARLY:,} readings is required for early analysis."
        )
        if rpd > 0:
            days_to_next = max(days_needed, max(1, int(readings_needed / rpd)))
            next_desc = (
                f"At the current collection rate ({rpd:.0f} readings/day), early analysis will be "
                f"available in approximately {days_to_next} more day(s)."
            )
        else:
            days_to_next = None
            next_desc = "Start data collection to enable analysis."

    return DataSufficiency(
        total_readings=total,
        days_covered=round(days, 2),
        readings_per_day=round(rpd, 1),
        has_early=has_early,
        has_basic=has_basic,
        has_full=has_full,
        has_seasonal=has_seasonal,
        status=status,
        status_description=status_desc,
        next_level_description=next_desc,
        estimated_days_to_next=days_to_next,
    )


def _safe_pct(arr: np.ndarray, pct: float) -> float:
    if len(arr) == 0:
        return float("nan")
    return float(np.nanpercentile(arr, pct))


def _compute_distribution(series: pd.Series, variable: str) -> DistributionStats:
    clean = pd.to_numeric(series, errors="coerce").dropna().values
    if len(clean) == 0:
        pcts = {p: float("nan") for p in (1, 5, 10, 25, 50, 75, 85, 90, 92, 95, 97, 99)}
        return DistributionStats(
            variable=variable, count=0, mean=float("nan"), std=float("nan"),
            percentiles=pcts, iqr=float("nan"),
            data_min=float("nan"), data_max=float("nan"),
        )
    pct_keys = [1, 5, 10, 25, 50, 75, 85, 90, 92, 95, 97, 99]
    pcts = {p: float(np.nanpercentile(clean, p)) for p in pct_keys}
    iqr = pcts[75] - pcts[25]
    return DistributionStats(
        variable=variable,
        count=len(clean),
        mean=float(np.mean(clean)),
        std=float(np.std(clean)),
        percentiles=pcts,
        iqr=float(iqr),
        data_min=float(np.min(clean)),
        data_max=float(np.max(clean)),
    )


def _compute_diurnal_profile(df: pd.DataFrame, variable: str) -> DiurnalProfile:
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    s  = pd.to_numeric(df[variable], errors="coerce")
    mask = ts.notna() & s.notna()
    hour_series = ts[mask].dt.hour
    val_series  = s[mask]

    median_l, p10_l, p25_l, p75_l, p90_l, cnt_l = [], [], [], [], [], []
    for h in range(24):
        v = val_series[hour_series == h].values
        if len(v) > 0:
            median_l.append(float(np.median(v)))
            p10_l.append(_safe_pct(v, 10))
            p25_l.append(_safe_pct(v, 25))
            p75_l.append(_safe_pct(v, 75))
            p90_l.append(_safe_pct(v, 90))
            cnt_l.append(len(v))
        else:
            for lst in (median_l, p10_l, p25_l, p75_l, p90_l):
                lst.append(float("nan"))
            cnt_l.append(0)

    return DiurnalProfile(
        variable=variable,
        hours=list(range(24)),
        median=median_l, p10=p10_l, p25=p25_l, p75=p75_l, p90=p90_l,
        counts=cnt_l,
    )


def compute_dwf_diurnal_profile(
    df: pd.DataFrame,
    variable: str,
    df_rainfall: Optional[pd.DataFrame] = None,
    dry_cap_mm: float = 0.1,
) -> Optional[DiurnalProfile]:
    """Compute a dry-weather-flow (DWF) diurnal profile for *variable*.

    Filters the dataset to periods where hourly rainfall ≤ *dry_cap_mm*
    (WMO measurable-rain threshold) before computing the profile.  This
    removes wet-weather I/I signal from the baseline.

    If *df_rainfall* is not provided, or has fewer dry periods than 24 × 3
    (minimum three readings per hour), falls back to the full-dataset profile.

    Returns None if there are fewer than 24 readings after dry filtering.
    """
    if variable not in df.columns:
        return None

    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    s  = pd.to_numeric(df[variable], errors="coerce")

    if df_rainfall is not None and not df_rainfall.empty and "rainfall_mm" in df_rainfall.columns:
        # Convert rainfall timestamps to UTC-naive for merging
        rain_ts = pd.to_datetime(df_rainfall["timestamp"], errors="coerce")
        if rain_ts.dt.tz is not None:
            rain_ts = rain_ts.dt.tz_convert("UTC").dt.tz_localize(None)

        # Build an hourly dry/wet mask
        rain_hourly = (
            df_rainfall.assign(_t=rain_ts)
            .set_index("_t")
            .sort_index()["rainfall_mm"]
            .resample("1h")
            .sum()
        )
        # Strip flow timestamps for comparison
        flow_ts_naive = ts.copy()
        if flow_ts_naive.dt.tz is not None:
            flow_ts_naive = flow_ts_naive.dt.tz_convert("UTC").dt.tz_localize(None)

        # Forward-fill hourly rainfall sum onto each flow reading.
        # Gaps in the rainfall record are treated as zero (no rain data = assume dry).
        # Flow readings during periods of missing rainfall data are therefore
        # *included* in the dry-weather filter; engineers should verify rainfall
        # data coverage before relying on this profile.
        flow_hours = flow_ts_naive.dt.floor("1h")
        rain_for_flow = flow_hours.map(rain_hourly).fillna(0.0)
        dry_mask = (ts.notna()) & (s.notna()) & (rain_for_flow <= dry_cap_mm)
    else:
        dry_mask = ts.notna() & s.notna()

    hour_series = ts[dry_mask].dt.hour
    val_series  = s[dry_mask]

    if len(val_series) < 24:
        return None

    median_l, p10_l, p25_l, p75_l, p90_l, cnt_l = [], [], [], [], [], []
    for h in range(24):
        v = val_series[hour_series == h].values
        if len(v) > 0:
            median_l.append(float(np.median(v)))
            p10_l.append(_safe_pct(v, 10))
            p25_l.append(_safe_pct(v, 25))
            p75_l.append(_safe_pct(v, 75))
            p90_l.append(_safe_pct(v, 90))
            cnt_l.append(len(v))
        else:
            for lst in (median_l, p10_l, p25_l, p75_l, p90_l):
                lst.append(np.nan)
            cnt_l.append(0)

    return DiurnalProfile(
        variable=variable,
        hours=list(range(24)),
        median=median_l, p10=p10_l, p25=p25_l, p75=p75_l, p90=p90_l,
        counts=cnt_l,
    )


def _compute_dow_profile(df: pd.DataFrame, variable: str) -> DayOfWeekProfile:
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    s  = pd.to_numeric(df[variable], errors="coerce")
    mask = ts.notna() & s.notna()
    dow_series = ts[mask].dt.dayofweek  # 0=Monday
    val_series = s[mask]

    median_l, p25_l, p75_l, cnt_l = [], [], [], []
    for d in range(7):
        v = val_series[dow_series == d].values
        if len(v) > 0:
            median_l.append(float(np.median(v)))
            p25_l.append(_safe_pct(v, 25))
            p75_l.append(_safe_pct(v, 75))
            cnt_l.append(len(v))
        else:
            for lst in (median_l, p25_l, p75_l):
                lst.append(float("nan"))
            cnt_l.append(0)

    return DayOfWeekProfile(
        variable=variable,
        days=list(range(7)),
        day_names=_DOW_NAMES,
        median=median_l, p25=p25_l, p75=p75_l, counts=cnt_l,
    )


def _compute_trend(df: pd.DataFrame, variable: str) -> TrendResult:
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    s  = pd.to_numeric(df[variable], errors="coerce")
    mask = ts.notna() & s.notna()
    ts_clean = ts[mask]
    s_clean  = s[mask]

    unit = _SENSOR_META.get(variable, {}).get("unit", "")

    insufficient = TrendResult(
        variable=variable, slope_per_day=0.0, r_squared=0.0, p_value=1.0,
        direction="stable", direction_label="Stable (insufficient data)",
        days_covered=0.0, slope_description="N/A",
    )
    if len(s_clean) < 20:
        return insufficient

    t0 = ts_clean.min()
    t_days = ((ts_clean - t0).dt.total_seconds() / 86400.0).values
    v = s_clean.values
    days_covered = float(t_days.max())

    # Use scipy for regression to get p-value as well
    result = scipy_stats.linregress(t_days, v)
    slope   = float(result.slope)
    r2      = float(result.rvalue ** 2)
    p_value = float(result.pvalue)

    v_std = float(np.std(v))
    norm = abs(slope) / max(v_std, 1e-10)  # normalised slope: fraction of std per day

    if norm < 0.001 or p_value > 0.05:
        direction = "stable"
        direction_label = "Stable"
    elif slope > 0:
        if r2 > 0.3 and norm > 0.01:
            direction = "significant_increase"
            direction_label = "Significant Increase ↑↑"
        else:
            direction = "gradual_increase"
            direction_label = "Gradual Increase ↑"
    else:
        if r2 > 0.3 and norm > 0.01:
            direction = "significant_decrease"
            direction_label = "Significant Decrease ↓↓"
        else:
            direction = "gradual_decrease"
            direction_label = "Gradual Decrease ↓"

    prec = _SENSOR_META.get(variable, {}).get("precision", 3)
    if abs(slope) >= 1:
        slope_str = f"{slope:+.{prec}f} {unit}/day"
    elif abs(slope) >= 0.001:
        slope_str = f"{slope:+.{max(prec, 3)}f} {unit}/day"
    else:
        slope_str = f"{slope:+.2e} {unit}/day"

    return TrendResult(
        variable=variable,
        slope_per_day=slope,
        r_squared=round(r2, 4),
        p_value=round(p_value, 6),
        direction=direction,
        direction_label=direction_label,
        days_covered=round(days_covered, 1),
        slope_description=slope_str,
    )


# ── Main entry points ─────────────────────────────────────────────────────────

def compute_site_baseline(df: pd.DataFrame, device_id: str) -> SiteBaseline:
    """Compute a full SiteBaseline for *device_id* from measurement DataFrame *df*.

    *df* must contain at minimum a ``timestamp`` column and one or more of
    ``depth_mm``, ``velocity_mps``, ``flow_lps``.

    Always returns a SiteBaseline even if data is insufficient — callers should
    check ``baseline.sufficiency.status`` before trusting the profile statistics.

    Early-stage analysis (has_early, not yet has_basic) computes distribution
    statistics and a preliminary diurnal profile with fewer than 7 days of data.
    Alarm recommendations are only generated when has_basic is True.
    """
    sufficiency = check_data_sufficiency(df)
    profiles: Dict[str, BaselineProfile] = {}

    # Compute profiles whenever we have early-stage data or better.
    # For early-stage we require only 20 readings per variable.
    min_readings_for_profile = 20 if not sufficiency.has_basic else 100
    if sufficiency.has_early:
        available_vars = [v for v in SENSOR_VARIABLES if v in df.columns]
        for var in available_vars:
            series = pd.to_numeric(df[var], errors="coerce")
            if series.notna().sum() < min_readings_for_profile:
                continue
            try:
                dist    = _compute_distribution(series, var)
                diurnal = _compute_diurnal_profile(df, var)
                dow     = _compute_dow_profile(df, var)
                trend   = _compute_trend(df, var)
                profiles[var] = BaselineProfile(
                    variable=var,
                    distribution=dist,
                    diurnal=diurnal,
                    dow=dow,
                    trend=trend,
                )
            except Exception as exc:
                logger.warning("Failed to compute profile for %s: %s", var, exc)

    return SiteBaseline(
        device_id=device_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        readings_used=sufficiency.total_readings,
        days_covered=sufficiency.days_covered,
        sufficiency=sufficiency,
        profiles=profiles,
        status=sufficiency.status,
    )


# ── Alarm recommendation engine ───────────────────────────────────────────────

def generate_alarm_recommendations(
    site_baseline: SiteBaseline,
    sensitivities: Optional[List[str]] = None,
) -> List[AlarmRecommendation]:
    """Produce data-driven alarm level recommendations from a computed SiteBaseline.

    For each variable and sensitivity level, three alarm levels are produced:
    ``low_warning``, ``high_warning``, and ``critical``.  Depth additionally
    gets below-threshold alarms (dry-sensor / zero-flow detection).

    Parameters
    ----------
    site_baseline:
        A :class:`SiteBaseline` returned by :func:`compute_site_baseline`.
    sensitivities:
        Subset of ``["conservative", "standard", "sensitive"]`` to generate.
        Defaults to all three.

    Returns
    -------
    List of :class:`AlarmRecommendation` objects.  Empty if the baseline has
    insufficient data.
    """
    if sensitivities is None:
        sensitivities = ["conservative", "standard", "sensitive"]

    recs: List[AlarmRecommendation] = []

    if not site_baseline.profiles:
        return recs

    days  = site_baseline.days_covered
    total = site_baseline.readings_used

    for variable, profile in site_baseline.profiles.items():
        dist = profile.distribution
        if dist.count < 100:
            continue

        meta    = _SENSOR_META.get(variable, {})
        unit    = meta.get("unit", "")
        label   = meta.get("label", variable)
        prec    = meta.get("precision", 2)
        dirs    = meta.get("directions", ["above"])
        pct     = dist.percentiles
        iqr     = dist.iqr

        basis_suffix = f"derived from {dist.count:,} readings over {days:.0f} days"

        def _fmt(v: float) -> str:
            return f"{v:.{prec}f}"

        def _rec(direction, level_name, value, basis, fp_pct, sensitivity):
            return AlarmRecommendation(
                variable=variable,
                variable_label=label,
                direction=direction,
                level_name=level_name,
                level_label=_LEVEL_LABELS[level_name],
                recommended_value=round(value, prec),
                unit=unit,
                sensitivity=sensitivity,
                sensitivity_label=_SENSITIVITY_LABELS[sensitivity],
                basis=basis,
                estimated_fp_pct=fp_pct,
            )

        for sens in sensitivities:
            if "above" in dirs:
                if sens == "standard":
                    lw  = pct[90] + 0.25 * iqr
                    hw  = pct[95] + 0.50 * iqr
                    crt = pct[99] + iqr
                    recs.append(_rec("above", "low_warning", lw, sensitivity=sens,
                        basis=(
                            f"P90 ({_fmt(pct[90])} {unit}) + 0.25×IQR ({_fmt(0.25*iqr)} {unit})"
                            f" = {_fmt(lw)} {unit}; {basis_suffix}"
                        ), fp_pct=8.0))
                    recs.append(_rec("above", "high_warning", hw, sensitivity=sens,
                        basis=(
                            f"P95 ({_fmt(pct[95])} {unit}) + 0.5×IQR ({_fmt(0.5*iqr)} {unit})"
                            f" = {_fmt(hw)} {unit}; {basis_suffix}"
                        ), fp_pct=3.0))
                    recs.append(_rec("above", "critical", crt, sensitivity=sens,
                        basis=(
                            f"P99 ({_fmt(pct[99])} {unit}) + 1×IQR ({_fmt(iqr)} {unit})"
                            f" = {_fmt(crt)} {unit}; {basis_suffix}"
                        ), fp_pct=0.5))

                elif sens == "conservative":
                    lw  = pct[95]
                    hw  = pct[99]
                    crt = pct[99] + 2.0 * iqr
                    recs.append(_rec("above", "low_warning", lw, sensitivity=sens,
                        basis=f"P95 ({_fmt(lw)} {unit}); minimal false positives; {basis_suffix}",
                        fp_pct=3.0))
                    recs.append(_rec("above", "high_warning", hw, sensitivity=sens,
                        basis=f"P99 ({_fmt(hw)} {unit}); very rare exceedance in normal operation; {basis_suffix}",
                        fp_pct=0.5))
                    recs.append(_rec("above", "critical", crt, sensitivity=sens,
                        basis=(
                            f"P99 ({_fmt(pct[99])} {unit}) + 2×IQR ({_fmt(2*iqr)} {unit})"
                            f" = {_fmt(crt)} {unit}; extreme outlier threshold; {basis_suffix}"
                        ), fp_pct=0.1))

                else:  # sensitive
                    lw  = pct[85]
                    hw  = pct[92]
                    crt = pct[97]
                    recs.append(_rec("above", "low_warning", lw, sensitivity=sens,
                        basis=f"P85 ({_fmt(lw)} {unit}); early warning with higher sensitivity; {basis_suffix}",
                        fp_pct=15.0))
                    recs.append(_rec("above", "high_warning", hw, sensitivity=sens,
                        basis=f"P92 ({_fmt(hw)} {unit}); elevated concern threshold; {basis_suffix}",
                        fp_pct=8.0))
                    recs.append(_rec("above", "critical", crt, sensitivity=sens,
                        basis=f"P97 ({_fmt(crt)} {unit}); high-sensitivity critical threshold; {basis_suffix}",
                        fp_pct=3.0))

            # Below-threshold alarms for depth only (dry-sensor / zero-flow detection)
            if variable == "depth_mm" and "below" in dirs:
                if sens == "standard":
                    lw_b   = max(0.0, pct[10])
                    hw_b   = max(0.0, pct[5])
                    crt_b  = max(0.0, pct[5] - 0.5 * iqr)
                    recs.append(_rec("below", "low_warning", lw_b, sensitivity=sens,
                        basis=(
                            f"P10 ({_fmt(pct[10])} {unit}); readings below this may indicate"
                            f" very low flow or sensor near dry-out; {basis_suffix}"
                        ), fp_pct=10.0))
                    recs.append(_rec("below", "high_warning", hw_b, sensitivity=sens,
                        basis=(
                            f"P5 ({_fmt(pct[5])} {unit}); consistently low depth; "
                            f"verify sensor is not obstructed or dry; {basis_suffix}"
                        ), fp_pct=5.0))
                    recs.append(_rec("below", "critical", crt_b, sensitivity=sens,
                        basis=(
                            f"P5 ({_fmt(pct[5])} {unit}) − 0.5×IQR ({_fmt(0.5*iqr)} {unit})"
                            f" = {_fmt(crt_b)} {unit}; strong indicator of dry sensor or surcharge; {basis_suffix}"
                        ), fp_pct=1.0))
                elif sens == "conservative":
                    lw_b = max(0.0, pct[5])
                    recs.append(_rec("below", "low_warning", lw_b, sensitivity=sens,
                        basis=f"P5 ({_fmt(lw_b)} {unit}); conservative dry-sensor threshold; {basis_suffix}",
                        fp_pct=3.0))
                else:  # sensitive
                    lw_b = max(0.0, pct[25])
                    recs.append(_rec("below", "low_warning", lw_b, sensitivity=sens,
                        basis=f"P25 ({_fmt(lw_b)} {unit}); sensitive low-flow detection; {basis_suffix}",
                        fp_pct=25.0))

    return recs


# ── PDF report ────────────────────────────────────────────────────────────────

def build_intelligence_pdf(
    device_name: str,
    baseline: SiteBaseline,
    recommendations: List[AlarmRecommendation],
    sensitivity_filter: Optional[str] = "standard",
) -> bytes:
    """Generate a professional PDF alarm advisory report using reportlab.

    Returns empty bytes if reportlab is not available.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable,
        )
        from reportlab.lib import colors as rl_colors
    except ImportError:
        return b""

    buf = io.BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN   = 20 * mm
    USABLE_W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    C_GREEN      = rl_colors.HexColor("#3A7F5F")
    C_DARK_GREEN = rl_colors.HexColor("#2F6B50")
    C_LIGHT_GREEN= rl_colors.HexColor("#E8F3EE")
    C_TEXT       = rl_colors.HexColor("#4A4A4A")
    C_MUTED      = rl_colors.HexColor("#6b7280")
    C_BORDER     = rl_colors.HexColor("#D9D9D9")
    C_ROW_ALT    = rl_colors.HexColor("#F9FAF9")
    C_WARNING    = rl_colors.HexColor("#F4B400")
    C_DANGER     = rl_colors.HexColor("#D93025")
    C_SUCCESS    = rl_colors.HexColor("#4CAF50")

    base  = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=base["Title"],
        fontSize=20, textColor=C_GREEN, spaceAfter=4, fontName="Helvetica-Bold")
    h2_style = ParagraphStyle("H2", parent=base["Heading2"],
        fontSize=13, textColor=C_DARK_GREEN, spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
    body_style = ParagraphStyle("Body", parent=base["Normal"],
        fontSize=9, textColor=C_TEXT, spaceAfter=4, fontName="Helvetica")
    small_style = ParagraphStyle("Small", parent=base["Normal"],
        fontSize=8, textColor=C_MUTED, fontName="Helvetica")
    footer_style = ParagraphStyle("Footer", parent=small_style,
        alignment=TA_CENTER, spaceBefore=4)

    def _tbl(data, col_widths=None, extra_styles=None):
        t = Table(data, colWidths=col_widths)
        styles = [
            ("BACKGROUND",    (0, 0), (-1, 0), C_LIGHT_GREEN),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_DARK_GREEN),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, C_ROW_ALT]),
            ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
            ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]
        if extra_styles:
            styles.extend(extra_styles)
        t.setStyle(TableStyle(styles))
        return t

    story = []
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    story.append(Paragraph("EDS FlowSense™ Site Intelligence Report", title_style))
    story.append(Paragraph(f"Alarm Advisory for: <b>{html.escape(device_name)}</b>", body_style))
    story.append(Paragraph(f"Generated: {generated_at}", small_style))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GREEN, spaceAfter=10))

    # ── Summary card ─────────────────────────────────────────────────────────
    story.append(Paragraph("Data Readiness Summary", h2_style))
    suf = baseline.sufficiency
    status_labels = {
        "insufficient": "Insufficient Data",
        "basic":        "Basic Analysis",
        "full":         "Full Analysis",
        "seasonal":     "Seasonal Analysis",
    }
    summary_rows = [
        ["Metric", "Value"],
        ["Site / Device", html.escape(device_name)],
        ["Analysis Status", status_labels.get(baseline.status, baseline.status.title())],
        ["Total Readings", f"{suf.total_readings:,}"],
        ["Data Coverage", f"{suf.days_covered:.1f} days"],
        ["Collection Rate", f"{suf.readings_per_day:.0f} readings / day"],
        ["Baseline Computed", baseline.computed_at[:10]],
    ]
    story.append(_tbl(summary_rows, col_widths=[65*mm, USABLE_W - 65*mm]))
    story.append(Spacer(1, 6*mm))

    # ── Trend summary ─────────────────────────────────────────────────────────
    if baseline.profiles:
        story.append(Paragraph("Trend Summary", h2_style))
        trend_rows = [["Variable", "Direction", "Slope", "R²", "p-value"]]
        for var, prof in baseline.profiles.items():
            t = prof.trend
            var_label = _SENSOR_META.get(var, {}).get("label", var)
            trend_rows.append([
                var_label,
                t.direction_label,
                t.slope_description,
                f"{t.r_squared:.3f}",
                f"{t.p_value:.4f}",
            ])
        col_w = [45*mm, 50*mm, 38*mm, 18*mm, 19*mm]
        story.append(_tbl(trend_rows, col_widths=col_w))
        story.append(Spacer(1, 6*mm))

    # ── Alarm recommendations ─────────────────────────────────────────────────
    filtered = [r for r in recommendations
                if sensitivity_filter is None or r.sensitivity == sensitivity_filter]

    if filtered:
        sens_label = _SENSITIVITY_LABELS.get(sensitivity_filter, sensitivity_filter or "All")
        story.append(Paragraph(f"Recommended Alarm Levels — {sens_label} Sensitivity", h2_style))
        story.append(Paragraph(
            "The following alarm thresholds are derived from statistical analysis of the site's "
            "historical data. They represent data-driven suggestions; site engineers should "
            "review and adjust based on operational knowledge before implementation.",
            body_style,
        ))
        story.append(Spacer(1, 3*mm))

        rec_rows = [["Variable", "Alarm Level", "Direction", "Threshold", "Est. FP Rate", "Basis"]]
        extra_styles = []
        for i, r in enumerate(filtered, start=1):
            level_colour = {
                "low_warning":  C_WARNING,
                "high_warning": rl_colors.HexColor("#E65100"),
                "critical":     C_DANGER,
            }.get(r.level_name, C_TEXT)
            # Word-aware truncation: break at last space within 90 chars
            basis_text = r.basis
            if len(basis_text) > 90:
                cut = basis_text[:90].rsplit(" ", 1)[0]
                basis_text = cut + "…"
            rec_rows.append([
                r.variable_label,
                r.level_label,
                r.direction.title(),
                f"{r.recommended_value:.{_SENSOR_META.get(r.variable, {}).get('precision', 2)}f} {r.unit}",
                f"≈{r.estimated_fp_pct:.0f}%",
                basis_text,
            ])
            extra_styles.append(("TEXTCOLOR", (1, i), (1, i), level_colour))
            extra_styles.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

        col_w2 = [32*mm, 28*mm, 18*mm, 24*mm, 18*mm, USABLE_W - 32*mm - 28*mm - 18*mm - 24*mm - 18*mm]
        story.append(_tbl(rec_rows, col_widths=col_w2, extra_styles=extra_styles))
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            "Est. FP Rate = estimated percentage of normal readings that would trigger this alarm.",
            small_style,
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER))
    story.append(Paragraph("EDS FlowSense™ — Hydrological Intelligence Platform", footer_style))

    doc.build(story)
    return buf.getvalue()
