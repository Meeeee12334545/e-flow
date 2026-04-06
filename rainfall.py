"""
Rainfall data module for EDS FlowSense (EDS-FS).

Provides:
- search_bom_stations()   — search for BOM rainfall stations near a coordinate
- fetch_bom_rainfall()    — pull data from BOM's public JSON observation feeds
- fetch_open_meteo_rainfall() — fallback: pull hourly precipitation from Open-Meteo
- get_rainfall_for_device()   — high-level helper; caches results in FlowDatabase
"""

from __future__ import annotations

import io
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

import pandas as pd
import requests

if TYPE_CHECKING:
    from database import FlowDatabase

logger = logging.getLogger(__name__)

# ── BOM public resources ───────────────────────────────────────────────────────
# Station list: BOM Climate Data Services – plain-text station catalogue.
# The file is space-delimited with fixed column widths.
BOM_STATION_LIST_URL = (
    "http://www.bom.gov.au/climate/data/lists_by_element/alphaAUS_136.txt"
)

# BOM real-time JSON observation product IDs by state (rainfall product).
# Format: {state_abbrev: (product_id_prefix, product_code)}
BOM_STATE_PRODUCTS: Dict[str, tuple] = {
    "NSW": ("IDN60801", "IDN60801"),
    "VIC": ("IDV60801", "IDV60801"),
    "QLD": ("IDQ60801", "IDQ60801"),
    "SA":  ("IDS60801", "IDS60801"),
    "WA":  ("IDW60801", "IDW60801"),
    "TAS": ("IDT60801", "IDT60801"),
    "NT":  ("IDD60801", "IDD60801"),
    "ACT": ("IDN60801", "IDN60801"),
}

# Open-Meteo API endpoints (free, no auth)
OPEN_METEO_HIST_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_REQUEST_TIMEOUT = 20  # seconds


# ── Haversine helper ──────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two coordinates."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── BOM station search ────────────────────────────────────────────────────────

def _parse_bom_station_list(text: str) -> List[Dict]:
    """Parse the BOM station catalogue text into a list of station dicts."""
    stations: List[Dict] = []
    for line in text.splitlines():
        # Header / blank / separator lines are short or start with non-digit
        line = line.rstrip()
        if len(line) < 70:
            continue
        try:
            # Fixed-width layout (approximately):
            # 0-7   station_id
            # 8-18  site (unused)
            # 18-59 station_name
            # 59-68 state
            # 68-78 latitude
            # 78-88 longitude
            # rest  elevation, district, etc.
            station_id = line[0:8].strip()
            if not station_id.isdigit():
                continue
            station_name = line[18:59].strip()
            state = line[59:68].strip()
            lat_str = line[68:78].strip()
            lon_str = line[78:88].strip()
            latitude = float(lat_str)
            longitude = float(lon_str)
            stations.append(
                {
                    "station_id": station_id,
                    "station_name": station_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "state": state,
                }
            )
        except (ValueError, IndexError):
            continue
    return stations


def search_bom_stations(
    lat: float,
    lon: float,
    radius_km: float = 100.0,
    limit: int = 10,
) -> List[Dict]:
    """Return up to *limit* BOM rainfall stations within *radius_km* of (lat, lon).

    Fetches the public BOM station catalogue.  Each returned dict has keys:
    station_id, station_name, latitude, longitude, state, distance_km.

    Falls back to an empty list if the BOM catalogue is unreachable.
    """
    try:
        resp = requests.get(BOM_STATION_LIST_URL, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        # BOM serves the file as latin-1 / cp1252
        text = resp.content.decode("latin-1", errors="replace")
        stations = _parse_bom_station_list(text)
    except Exception as exc:
        logger.warning("Could not fetch BOM station list: %s", exc)
        return []

    nearby: List[Dict] = []
    for s in stations:
        try:
            dist = _haversine_km(lat, lon, s["latitude"], s["longitude"])
            if dist <= radius_km:
                s_copy = dict(s)
                s_copy["distance_km"] = round(dist, 2)
                nearby.append(s_copy)
        except Exception:
            continue

    nearby.sort(key=lambda x: x["distance_km"])
    return nearby[:limit]


# ── BOM rainfall fetch ────────────────────────────────────────────────────────

def fetch_bom_rainfall(
    station_id: str,
    state: str,
    date_from: datetime,
    date_to: datetime,
) -> pd.DataFrame:
    """Fetch rainfall observations from BOM's public JSON feed for *station_id*.

    Returns a DataFrame with columns [timestamp, rainfall_mm] indexed by UTC time.
    Returns an empty DataFrame if the station data is unavailable.
    """
    product = BOM_STATE_PRODUCTS.get(state.upper(), ("IDN60801", "IDN60801"))[0]
    # BOM JSON feed URL (current observations — up to ~72 h history):
    url = f"http://www.bom.gov.au/fwo/{product}/{product}.{station_id}.json"
    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT, headers={"User-Agent": "EDS-FS/1.0"})
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("BOM rainfall fetch failed for station %s: %s", station_id, exc)
        return pd.DataFrame(columns=["timestamp", "rainfall_mm"])

    try:
        observations = payload["observations"]["data"]
    except (KeyError, TypeError):
        return pd.DataFrame(columns=["timestamp", "rainfall_mm"])

    records = []
    for obs in observations:
        try:
            # BOM local_date_time_full format: "20240101000000"
            ts_str = obs.get("local_date_time_full", "")
            ts = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            # rain_trace can be "0.0", "Trace" (< 0.2 mm), or numeric string
            rain_raw = obs.get("rain_trace", None)
            if rain_raw in (None, "-", ""):
                rain_mm = None
            elif str(rain_raw).strip().lower() in ("trace",):
                rain_mm = 0.1
            else:
                rain_mm = float(rain_raw)
            records.append({"timestamp": ts, "rainfall_mm": rain_mm})
        except (ValueError, TypeError, KeyError):
            continue

    if not records:
        return pd.DataFrame(columns=["timestamp", "rainfall_mm"])

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["timestamp"] >= date_from) & (df["timestamp"] <= date_to)]
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ── Open-Meteo rainfall fetch ─────────────────────────────────────────────────

def fetch_open_meteo_rainfall(
    lat: float,
    lon: float,
    date_from: datetime,
    date_to: datetime,
) -> pd.DataFrame:
    """Fetch hourly precipitation from Open-Meteo (free, no auth required).

    Automatically picks the historical archive API for past dates and the
    forecast API for future/near-real-time data.

    Returns a DataFrame with columns [timestamp, rainfall_mm].
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    # Open-Meteo archive is available up to ~5 days ago
    archive_cutoff = now_utc - timedelta(days=5)

    # Determine which API(s) to call
    start_str = date_from.strftime("%Y-%m-%d")
    end_str = date_to.strftime("%Y-%m-%d")

    frames: List[pd.DataFrame] = []

    # Historical portion (archive API)
    if date_from.replace(tzinfo=None) <= archive_cutoff:
        hist_end = min(date_to.replace(tzinfo=None), archive_cutoff)
        try:
            resp = requests.get(
                OPEN_METEO_HIST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": date_from.strftime("%Y-%m-%d"),
                    "end_date": hist_end.strftime("%Y-%m-%d"),
                    "hourly": "precipitation",
                    "timezone": "UTC",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            times = data["hourly"]["time"]
            precip = data["hourly"]["precipitation"]
            frames.append(
                pd.DataFrame({"timestamp": pd.to_datetime(times), "rainfall_mm": precip})
            )
        except Exception as exc:
            logger.warning("Open-Meteo historical fetch failed: %s", exc)

    # Forecast/recent portion (forecast API)
    if date_to.replace(tzinfo=None) >= archive_cutoff:
        try:
            past_days = max(0, (now_utc - date_from.replace(tzinfo=None)).days)
            past_days = min(past_days, 16)  # API limit
            resp = requests.get(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "precipitation",
                    "timezone": "UTC",
                    "past_days": past_days,
                    "forecast_days": 3,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            times = data["hourly"]["time"]
            precip = data["hourly"]["precipitation"]
            frames.append(
                pd.DataFrame({"timestamp": pd.to_datetime(times), "rainfall_mm": precip})
            )
        except Exception as exc:
            logger.warning("Open-Meteo forecast fetch failed: %s", exc)

    if not frames:
        return pd.DataFrame(columns=["timestamp", "rainfall_mm"])

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    # Filter to requested range
    df = df[
        (df["timestamp"] >= pd.to_datetime(date_from).tz_localize(None))
        & (df["timestamp"] <= pd.to_datetime(date_to).tz_localize(None))
    ]
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ── Per-device high-level helper ──────────────────────────────────────────────

def get_rainfall_for_device(
    device_id: str,
    db: "FlowDatabase",
    date_from: datetime,
    date_to: datetime,
) -> pd.DataFrame:
    """Return a rainfall DataFrame for *device_id* over the requested period.

    Strategy:
    1. Look up the assigned rainfall station (or fall back to device coordinates).
    2. Check the DB cache for data covering the requested period.
    3. If data is missing, fetch from BOM first, then Open-Meteo as fallback.
    4. Store fresh data in the DB cache before returning.

    Returns a DataFrame with columns [timestamp, rainfall_mm], possibly empty.
    """
    # Resolve data source
    assignment = db.get_device_rainfall_station(device_id)
    device_list = db.get_devices()
    device = next((d for d in device_list if d["device_id"] == device_id), None)

    station_id: Optional[str] = None
    station_state: Optional[str] = None
    device_lat: Optional[float] = None
    device_lon: Optional[float] = None

    if assignment:
        station_id = assignment["station_id"]
        station_state = assignment.get("state")

    if device:
        device_lat = device.get("latitude")
        device_lon = device.get("longitude")

    # ── Try DB cache first ────────────────────────────────────────────────────
    cache_source = station_id or (f"coord_{device_id}" if device_lat else None)
    if cache_source:
        cached_rows = db.get_rainfall_data(
            station_id=cache_source,
            date_from=date_from,
            date_to=date_to,
        )
        if cached_rows:
            df_cache = pd.DataFrame(cached_rows)[["timestamp", "rainfall_mm"]]
            df_cache["timestamp"] = pd.to_datetime(df_cache["timestamp"])
            # Accept cache if it covers at least 80% of the expected hourly slots
            expected_hours = max(1, (date_to - date_from).total_seconds() / 3600)
            if len(df_cache) >= expected_hours * 0.8:
                return df_cache.sort_values("timestamp").reset_index(drop=True)

    # ── Fetch fresh data ──────────────────────────────────────────────────────
    df_fresh = pd.DataFrame(columns=["timestamp", "rainfall_mm"])

    if station_id and station_state:
        df_fresh = fetch_bom_rainfall(station_id, station_state, date_from, date_to)
        if df_fresh.empty:
            logger.info("BOM returned no data for %s, trying Open-Meteo", station_id)

    # Fallback: Open-Meteo via device or station coordinates
    if df_fresh.empty:
        lat = device_lat
        lon = device_lon
        if lat is None and assignment:
            lat = assignment.get("st_lat")
            lon = assignment.get("st_lon")
        if lat is not None and lon is not None:
            df_fresh = fetch_open_meteo_rainfall(lat, lon, date_from, date_to)
        else:
            logger.warning("No coordinates available for rainfall fetch on device %s", device_id)

    # ── Persist to cache ──────────────────────────────────────────────────────
    if not df_fresh.empty and cache_source:
        records = [
            {
                "timestamp": row["timestamp"].isoformat()
                if hasattr(row["timestamp"], "isoformat")
                else str(row["timestamp"]),
                "rainfall_mm": row["rainfall_mm"],
            }
            for _, row in df_fresh.iterrows()
        ]
        try:
            db.save_rainfall_data(station_id=cache_source, records=records)
        except Exception as exc:
            logger.warning("Could not cache rainfall data: %s", exc)

    return df_fresh.sort_values("timestamp").reset_index(drop=True) if not df_fresh.empty else df_fresh
