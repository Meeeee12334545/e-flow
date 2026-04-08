"""
FlowSense™ Methodology page — engineering reference for EDS FlowSense (EDS-FS).

Documents the analytical methods, algorithms, and standards used throughout
the platform so engineers can evaluate and reproduce any result.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from shared_styles import apply_styles, render_footer
from streamlit_auth import (
    get_sidebar_logo_path,
    init_auth_state,
    is_authenticated,
    login_page,
    render_auth_header,
)

# ── Auth guard ─────────────────────────────────────────────────────────────────
init_auth_state()
if not is_authenticated():
    login_page()
    st.stop()

st.set_page_config(
    page_title="EDS FlowSense | How Does FlowSense™ Work",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()

_ASSETS = Path(__file__).parent.parent / "assets"
st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

with st.sidebar:
    render_auth_header()

# ── Page header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
    <h1 style="margin:0; font-size:1.9rem; font-weight:700; color:#ffffff;">
        How Does FlowSense™ Work
    </h1>
    <p style="margin:0.3rem 0 0; color:rgba(255,255,255,0.85); font-size:0.95rem;">
        Engineering reference: algorithms, thresholds, and standards used in every analysis.
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

st.info(
    "This page documents the analytical methods used by EDS FlowSense™. "
    "All parameters are configurable; defaults are set to industry-standard values "
    "appropriate for wastewater monitoring in accordance with WSAA WSA 02 and general "
    "ISO/IEC hydrological measurement guidance."
)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _section(title: str, anchor: str = "") -> None:
    st.markdown(
        f"<h2 style='color:#2F6B50; border-bottom:2px solid #3A7F5F; "
        f"padding-bottom:6px; margin-top:2rem;'>{title}</h2>",
        unsafe_allow_html=True,
    )


def _param(name: str, default, description: str) -> None:
    st.markdown(
        f"<p style='margin:0.2rem 0 0.5rem; font-size:0.88rem;'>"
        f"<code style='background:#E8F3EE; padding:1px 5px; border-radius:3px; color:#2F6B50;'>"
        f"{name}</code>"
        f"&nbsp; Default: <strong>{default}</strong> — {description}</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data Collection & Quality Assurance
# ═══════════════════════════════════════════════════════════════════════════════
_section("1. Data Collection & Quality Assurance")

st.markdown("""
The monitor service polls each configured device at a configurable interval
(default every 60 seconds) and stores a reading only when the values change
(delta-compression mode) or unconditionally if *store-all-readings* mode is enabled.

Timestamps are stored in UTC and labelled accordingly throughout the platform.
""")

st.markdown("#### 1.1 Anomaly Detection")
st.markdown("""
Six independent anomaly detectors run over every data window presented in the
Reports or Dashboard views.  A composite **confidence score** (0–100) and
**quality label** (High ≥ 80, Medium ≥ 50, Low < 50) are computed from the
weighted sum of anomaly counts relative to the total readings.

| Detector | Method | Default threshold |
|---|---|---|
| **Out-of-range** | Hard physical bounds check | Depth: 0–3 000 mm; Velocity: −5 to 10 m/s; Flow: −500 to 5 000 L/s |
| **Flatline** | Consecutive identical-value run detection | ≥ 12 consecutive identical readings |
| **Spike** | Rate-of-change per minute | Depth: 500 mm/min; Velocity: 5 m/s/min; Flow: 2 000 L/s/min |
| **Dropout** | Timestamp gap detection | Gap > 15 minutes |
| **Hydraulic inconsistency** | Velocity–depth plausibility | Velocity > depth × 0.05 and velocity > 0.5 m/s |
| **Z-score** | Rolling window statistical outlier | Rolling 60-reading window, |Z| > 4.5 |

The confidence score penalty is `min(60, (anomalies × 3 + warnings × 1.5) / N × 100)`
where *N* is the total reading count.
""")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Site Baseline Learning
# ═══════════════════════════════════════════════════════════════════════════════
_section("2. Site Baseline Learning")

st.markdown("""
The baseline engine analyses all stored measurements to build a learned profile
of site-specific behaviour.  Profiles are computed on demand (or nightly by the
auto-retrain scheduler) and cached in the database.

#### Data sufficiency levels

| Level | Minimum data | Analyses unlocked |
|---|---|---|
| **Insufficient** | < 1 day or < 100 readings | None |
| **Early** | ≥ 1 day and ≥ 100 readings | Preliminary stats, diurnal profile (with caveats) |
| **Basic** | ≥ 7 days and ≥ 5 000 readings | Full profiles, alarm recommendations |
| **Full** | ≥ 30 days | Day-of-week profiles, trend analysis |
| **Seasonal** | ≥ 90 days | Seasonal trend analysis, high-confidence recommendations |
""")

st.markdown("#### 2.1 Distribution Statistics")
st.markdown("""
For each sensor variable (depth, velocity, flow), the full empirical distribution
is computed from all non-null readings:

- Key percentiles: P1, P5, P10, P25, P50, P75, P85, P90, P92, P95, P97, P99
- Inter-quartile range (IQR) = P75 − P25
- Mean and standard deviation
- Data minimum and maximum
""")

st.markdown("#### 2.2 Diurnal Profile")
st.markdown("""
Readings are grouped by UTC hour-of-day (0–23).  For each hour, the median,
P10, P25, P75 and P90 are computed from all readings in that hour.  The profile
reveals daily usage patterns such as morning peak flows or overnight low-flow
periods.

**All-data diurnal** uses every reading regardless of weather conditions.  
**Dry-weather flow (DWF) diurnal** filters out readings where the rainfall
in the same hourly period (1-hour bucket) exceeds 0.1 mm/hr (WMO measurable-rain threshold),
removing the wet-weather I/I signal and producing a cleaner baseline for alarm design.
Periods with missing rainfall data are treated as dry (no-rain assumed);
engineers should verify rainfall data coverage before relying on this profile.
""")

st.markdown("#### 2.3 Day-of-Week Profile")
st.markdown("""
Readings are grouped by day of week (Monday = 0).  Median and IQR are computed
per day.  Significant differences between weekdays and weekends indicate
catchment-specific usage patterns (e.g., commercial vs residential behaviour)
that should inform alarm scheduling.
""")

st.markdown("#### 2.4 Trend Analysis")
st.markdown("""
Ordinary least-squares (OLS) linear regression is fitted to the time series
of each sensor variable using `scipy.stats.linregress`.

| Output | Meaning |
|---|---|
| **Slope** | Change per day (positive = increasing) |
| **R²** | Proportion of variance explained by the linear model |
| **p-value** | Two-tailed significance; p < 0.05 = statistically significant trend |

Trend labels:
- **Stable**: normalised slope < 0.001 of std/day, or p > 0.05
- **Gradual increase/decrease**: significant but modest slope
- **Significant increase/decrease**: R² > 0.3 and normalised slope > 1%/day

A significant upward depth trend may indicate sewer blockage or infrastructure
change.  A significant downward velocity trend may indicate sediment build-up.
""")

st.markdown("#### 2.5 Continuous Learning (Auto-Retrain)")
st.markdown("""
The monitor service runs a nightly background job (every 24 hours) that
automatically recomputes baselines for all devices with sufficient data.
Devices whose baseline was computed within the last 20 hours are skipped to
avoid redundant computation.  Alarm recommendations are refreshed at the same time.

Manual recomputation is always available via the **Compute Baselines** button
on the Site Intelligence page.
""")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Alarm Level Recommendations
# ═══════════════════════════════════════════════════════════════════════════════
_section("3. Alarm Level Recommendations")

st.markdown("""
Alarm thresholds are derived statistically from the site's own history.
Three sensitivity levels are provided — engineers should choose the level
appropriate to the consequence of a missed alarm vs. the cost of false alarms.

| Sensitivity | Low Warning | High Warning | Critical (above) |
|---|---|---|---|
| **Conservative** | P95 | P99 | P99 + 2 × IQR |
| **Standard** | P90 + 0.25 × IQR | P95 + 0.5 × IQR | P99 + 1 × IQR |
| **Sensitive** | P85 | P92 | P97 |

**Below-threshold alarms** (depth only, dry-sensor / zero-flow detection):

| Sensitivity | Low Warning |
|---|---|
| Conservative | P5 |
| Standard | P10 (low warning), P5 (high warning), P5 − 0.5 × IQR (critical) |
| Sensitive | P25 |

**Estimated false-positive rate** is the approximate percentage of normal
readings that would exceed each threshold under stable operating conditions.
These are indicative values based on the empirical distribution.

> **Important:** These are data-driven recommendations only. Always validate
> against operational knowledge and site-specific requirements before
> implementation. Alarm recommendations are not available at the Early stage
> (< 7 days of data) as the sample is insufficient for statistical reliability.
""")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Rainfall & Inflow/Infiltration Analysis
# ═══════════════════════════════════════════════════════════════════════════════
_section("4. Rainfall & Inflow/Infiltration (I/I) Analysis")

st.markdown("""
Rainfall data is sourced from the Australian Bureau of Meteorology (BOM) JSON
observation feeds for the nearest assigned station, with Open-Meteo ERA5
reanalysis as a fallback.  Data is cached in the local database.

#### 4.1 Rain Event Detection
""")
_param("Rainfall threshold", "0.1 mm/hr", "WMO minimum measurable-rain threshold (WMO No. 8)")
_param("Merge gap", "3 hours", "Dry intervals shorter than this are bridged into one event")
_param("Post-rain window", "6 hours", "Flow is monitored this long after rain ends for I/I response")

st.markdown("""
#### 4.2 Dry-Weather Flow (DWF) Baseline
""")
_param("Lookback window", "7 days", "Only data within this rolling window is used for baseline")
_param("Dry threshold", "0.1 mm/hr", "Hourly rainfall at or below this is classified as dry")
_param("Min dry readings", "10", "Minimum dry-period readings to compute a baseline; falls back to overall median")

st.markdown("""
The baseline is the **median of dry-weather readings** trimmed to the P10–P90
range to exclude outliers.

#### 4.3 Antecedent Precipitation Index (API)

The Linsley (1958) exponential decay model tracks accumulated moisture at the
start of each rain event:

$$\\text{API}(t) = P(t) + k^{\\Delta t} \\cdot \\text{API}(t-1)$$

where:
- $P(t)$ — hourly rainfall (mm)
- $k = 0.85$ per day — decay coefficient (~6–7 day half-life); converted to the
  sub-daily timestep as $k_{\\text{hourly}} = 0.85^{1/24}$
- $\\Delta t$ — timestep in days

**Antecedent Moisture Condition (AMC) classification:**

| AMC class | API range | Expected I/I sensitivity |
|---|---|---|
| **I  — Dry** | ≤ 12 mm | Low; soils and pipe voids unsaturated |
| **II — Moist** | 12–28 mm | Moderate |
| **III — Wet** | > 28 mm | High; pipe surrounds saturated, groundwater elevated |

A wetter AMC increases the confidence score for any detected I/I flag and
triggers a separate recommendation when events occur under AMC-III conditions.

#### 4.4 Eckhardt Baseflow Separation

The **Eckhardt (2005) recursive digital filter** decomposes total sewer flow
into two components:

- **Baseflow** (slow) — represents steady groundwater **infiltration** through
  deteriorated pipe joints, cracks, and defective manhole seals.
- **Quickflow** (fast) — total flow minus baseflow; represents rapid surface
  **inflow** from stormwater cross-connections, roof drainage, or open
  manhole lids.

Filter equation (Eckhardt, Hydrological Processes, 2005):

$$b(i) = \\frac{(1-\\text{BFI}_{\\max})\\,\\alpha\\,b(i-1) + (1-\\alpha)\\,\\text{BFI}_{\\max}\\,Q(i)}{1 - \\alpha\\,\\text{BFI}_{\\max}}$$

where:
- $\\alpha$ — baseflow recession constant (calibrated at daily scale: 0.925;
  converted to sub-daily as $\\alpha_{\\text{hourly}} = 0.925^{\\Delta t/24}$)
- $\\text{BFI}_{\\max}$ — maximum long-term baseflow index (default: **0.50** for
  combined sewers); engineers should calibrate this against dry-weather flow
  records from the specific catchment

**Quickflow fraction** at each event peak is reported as an indicator of the
dominant pathway: values approaching 1.0 indicate predominantly surface inflow;
lower values indicate a significant infiltration (baseflow) component.
""")

_param("Eckhardt α (daily)", "0.925", "Baseflow recession constant — literature value for perennial streams; adjust for site conditions")
_param("BFI_max", "0.50", "Maximum baseflow index for combined sewer applications")

st.markdown("""
#### 4.5 I/I Detection and Severity

Flow exceeding the DWF baseline by the I/I multiplier triggers a flag.
""")
_param("I/I multiplier", "1.5×", "Flow exceeding baseline × this triggers an I/I flag")

st.markdown("""
| Severity | Response ratio |
|---|---|
| Low | 1.5× – 1.75× |
| Medium | 1.75× – 2.5× |
| High | 2.5× – 4× |
| Critical | > 4× |

**Excess flow volume** (m³) is computed by integrating the flow above the
DWF baseline over the full event monitoring window, providing a volumetric
measure of the extraneous flow entering the sewer per event.

**Lag time** (rain start → peak flow) distinguishes the dominant entry pathway:
- < 1 hour: direct surface inflow — likely open manhole lids or cross-connections
- 1–2 hours: rapid inflow — stormwater or roof drainage connections
- > 6 hours: groundwater infiltration — structural pipe or manhole defects

#### 4.6 Recession Coefficient Analysis

The post-peak falling limb is fitted with an exponential decay:

$$Q(t) = Q_{\\text{peak}} \\cdot \\exp(-k \\cdot (t - t_{\\text{peak}}))$$

OLS regression on $\\ln(Q/Q_{\\text{peak}})$ versus time yields the recession
coefficient $k$ (hr⁻¹):

| Recession type | k (hr⁻¹) | Interpretation |
|---|---|---|
| **Fast** | ≥ 0.10 | Flow drains quickly — consistent with direct surface inflow |
| **Moderate** | 0.02–0.10 | Mixed response |
| **Slow** | < 0.02 | Prolonged elevated flow — consistent with groundwater infiltration |

#### 4.7 Multi-Factor Confidence Score

The confidence score (0–100) combines three sources of evidence:

1. **Z-score** of peak flow relative to the full distribution:
   `base = clip(50 + Z × 10, 10, 100)`
2. **API boost** — wetter antecedent conditions add up to +8 points
   (Wet: +8, Moist: +4, Dry: 0)
3. **Ratio penalty** — events with response ratio < 1.5× × 1.2 are penalised
   −10 points to reduce false positives near the threshold

#### 4.8 Flow–Rainfall Correlation

Both time series are resampled to 1-hour buckets (rainfall summed, flow averaged).

**Pearson correlation** (linear, parametric, Pearson 1895):
""")
_param("Null hypothesis", "r = 0", "Two-tailed test; p < 0.05 = statistically significant linear association")

st.markdown("""
**95% confidence interval** for Pearson r is computed via the Fisher Z
transformation (Fisher, 1915):
$z = \\tanh^{-1}(r)$, CI: $z \\pm 1.96/\\sqrt{n-3}$, back-transformed.

**Spearman rank correlation** (ρ) is computed as a complementary non-parametric
measure — robust to non-linear relationships and resistant to flow outliers
(Helsel & Hirsch, 2002, USGS TWRI Book 4, Chapter A3).

A **lagged cross-correlation** search (0–24 hours) identifies the lag at which
rainfall most strongly predicts future flow.

| Quality label | |r| (Pearson) |
|---|---|
| None | < 0.2 |
| Weak | 0.2 – 0.4 |
| Moderate | 0.4 – 0.7 |
| Strong | ≥ 0.7 |
""")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. Advanced Hydraulic Analysis
# ═══════════════════════════════════════════════════════════════════════════════
_section("5. Advanced Hydraulic Capacity Analysis")

st.markdown(r"""
#### 5.1 Manning's Equation — Full-Bore Capacity

For a circular pipe of internal diameter *D* (m) flowing full:

$$Q_{full} = \frac{1}{n} \cdot A \cdot R^{2/3} \cdot S^{1/2}$$

where:
- $A = \pi D^2 / 4$ — cross-sectional area (m²)
- $R = D / 4$ — hydraulic radius for a full circular section (m)
- $S$ — longitudinal slope (dimensionless, = slope % ÷ 100)
- $n$ — Manning's roughness coefficient
""")

_param("Manning's n", "0.013", "Smooth concrete / vitrified clay sewer (WSAA WSA 02 reference value)")
_param("Default slope", "0.50 %", "Typical minimum design grade (1:200)")

st.markdown("""
#### 5.2 Pipe Utilisation

`Utilisation (%) = measured_flow_lps / Q_full_lps × 100`

#### 5.3 Surcharge Risk Classification
""")

st.markdown("""
| Risk level | Trigger condition |
|---|---|
| **Low** | Peak utilisation < 70% |
| **Moderate** | Peak utilisation 70–90% |
| **High** | Peak ≥ 90% or ≥ 2 surcharge events detected |
| **Critical** | Peak ≥ 100% or ≥ 5 surcharge events detected |

A **surcharge event** is a contiguous period where utilisation exceeds 90%
of the theoretical full-bore capacity.

> **Note:** Manning's equation assumes steady, uniform flow in a straight
> prismatic channel.  In practice, sewer hydraulics are affected by
> transitions, bends, manholes, and backwater effects.  Results should be
> validated against a full hydraulic model and as-built survey data.
> Slope and roughness are the dominant parameters — confirm these values
> from as-built drawings before relying on the capacity estimate.
""")

# ═══════════════════════════════════════════════════════════════════════════════
# 6. References
# ═══════════════════════════════════════════════════════════════════════════════
_section("6. References & Standards")

st.markdown("""
| Reference | Relevance |
|---|---|
| **WSAA WSA 02-2014** Water Services Association of Australia — *Sewerage Code of Australia* | Manning's n values for sewer pipes; design grades |
| **ISO 15747:2011** — *Measurement of liquid flow in closed conduits* | General flow measurement principles |
| **WMO No. 8** — *Guide to Meteorological Instruments and Methods of Observation* | Rainfall measurement and minimum threshold (0.1 mm/hr) |
| **Melbourne Water Design Guidelines** | Sewer capacity and surcharge risk definitions |
| **Eckhardt, K. (2005)** "How to construct recursive digital baseflow separation filters." *Hydrological Processes*, 19(2):507–515. | Baseflow separation filter (α, BFI_max parameters) |
| **Linsley, R.K., Kohler, M.A. & Paulhus, J.L.H. (1958)** *Hydrology for Engineers.* McGraw-Hill. | Antecedent Precipitation Index (API) exponential decay model |
| **Helsel, D.R. & Hirsch, R.M. (2002)** *Statistical Methods in Water Resources.* USGS TWRI Book 4, Chapter A3. | Spearman rank correlation for hydrological data; non-parametric methods |
| **Fisher, R.A. (1915)** "Frequency distribution of the values of the correlation coefficient." *Biometrika*, 10:507–521. | Fisher Z transformation for Pearson r confidence intervals |
| **Pearson, K. (1895)** "Notes on regression and inheritance in the case of two parents." *Proceedings of the Royal Society of London*, 58:240–242. | Pearson product-moment correlation coefficient |
| **Scipy `stats.linregress`** | OLS trend regression and recession coefficient implementation |
| **Scipy `stats.pearsonr`, `stats.spearmanr`** | Pearson and Spearman correlation with significance tests |
| **Open-Meteo ERA5 API** | Fallback gridded rainfall data |
| **Australian BOM JSON feeds** | Primary observed rainfall data (real-time station network) |

---
""")

render_footer()
