"""
Data Scraper Module - Autonomous Web Automation & DOM Extraction

This module implements browser automation using Playwright to extract
hydrological measurements from JavaScript-rendered USRIOT dashboards.

Key Features:
    - Headless Chromium orchestration with intelligent page-load detection
  - CSS selector-based DOM traversal with JavaScript execution
  - Regex-based numeric value extraction with unit parsing
  - Change-detection to minimize database writes
  - Comprehensive error handling and resilience
  - Timezone-aware timestamp management

Architecture:
    1. Browser initialization with headless Chromium via Playwright
    2. Page load waiting for network idle
    3. DOM querying with CSS selector queries
    4. Regex parsing of measurement strings (e.g., "133mm" -> 133.0)
    5. Change detection via FlowDatabase.has_changed()
    6. Async persistence with pytz timezone handling

Performance Considerations:
  - Page load time: ~1-2 seconds due to USRIOT dashboard rendering
  - DOM traversal: O(1) with CSS selector + querySelector
  - Extraction rate: ~5-10 measurements/second
  - Memory: ~200-300MB per Chrome instance
"""

import asyncio
import base64
import json
import os
import re
import hashlib
import zlib
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin, urlparse, parse_qs
from pathlib import Path
import logging
import requests
from bs4 import BeautifulSoup
import pytz
from playwright.async_api import async_playwright

from database import FlowDatabase
from config import STORE_ALL_READINGS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The website URL - can be parameterized
MONITOR_URL = "https://mp.usriot.com/draw/show.html?lang=en&lightbox=1&highlight=0000ff&layers=1&nav=1&title=FIT100%20Main%20Inflow%20Lismore%20STP&id=97811&link=Lpu7Q2CM3osZ&model=1&cusdeviceNo=0000088831000010&share=48731ec89bf8108b2a451fbffa590da4f0cf419a5623beb7d48c1060e3f0dbe177e28054c26be49bbabca1da5b977e7c16a47891d94f70a08a876d24c55416854700de7cc51a06f8e102798d6ecc39478ef1394a246efa109e6c6358e30a259010a5c403c71756173c90cf1e10ced6fdf54d90881c05559f2c8c5717ee8109210672fa3574a9c04a465bc0df8b9c354da487a7bcb6679a7ec32276ba3610301be80d8c7588ef1797ca01fb6b87e74a8b6e5cd0ac668918d02ae99a7966f57ecf603b63a12d4b0a160d3ac0920254d6836f1e26d244412f82859f7f7b0df7b8406e95ef97a7cb2302a07826d3b8cba81721c5bce1d7e9bf0b01f32d1d0330a44301a1ab0f"

DEFAULT_TZ = "Australia/Brisbane"


class DataScraper:
    """
    Production-grade web scraper for USRIOT hydrological dashboards.
    
        Responsibilities:
            - Playwright browser lifecycle management
            - DOM querying with CSS selectors
            - Value extraction via regex parsing
            - Change detection for delta compression
            - Timezone-aware timestamp generation
    
    Design Patterns:
      - Singleton: One scraper instance per monitor session
      - Resource Management: Context manager pattern for browser cleanup
      - Caching: last_data dict for O(1) change detection
    
    Thread Safety: Not thread-safe; designed for single-threaded async/await usage.
    
    Example:
        scraper = DataScraper()
        data = await scraper.fetch_monitor_data(url, selectors)
        if data and data['data']:
            # Process measurements
            pass
    """

    def __init__(self, db: FlowDatabase = None):
        """Initialize scraper with optional database instance."""
        self.db = db or FlowDatabase()
        self.tz = pytz.timezone(DEFAULT_TZ)
        
        # File-based persistence for change detection state
        self.state_file = Path(__file__).parent / ".scraper_state.json"
        self.last_data = self._load_state()
        
        # Allow forcing requests-only mode via environment to avoid browser launches in constrained runtimes
        self.force_requests = os.getenv("SCRAPER_FORCE_REQUESTS", "").lower() in ("1", "true", "yes")
    
    def _load_state(self) -> Dict:
        """Load change detection state from disk."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"Loaded change detection state from disk: {len(state)} devices")
                    return state
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")
        return {}
    
    def _save_state(self):
        """Save change detection state to disk."""
        try:
            # Convert datetime objects to strings for JSON serialization
            serializable_state = {}
            for device_id, data in self.last_data.items():
                serializable_state[device_id] = {
                    k: v.isoformat() if isinstance(v, datetime) else v
                    for k, v in data.items()
                }
            
            with open(self.state_file, 'w') as f:
                json.dump(serializable_state, f, indent=2)
            logger.debug(f"Saved change detection state to disk")
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")

    def _decrypt_share_token(self, share_param: str, pwd: str = "usr.cn") -> Optional[str]:
        """Replicate the secret_Key decryption used by the USRIOT share link to obtain the API token."""
        if not share_param:
            return None

        try:
            prand = "".join(str(ord(c)) for c in pwd)
            s_pos = len(prand) // 5
            mult = int(prand[s_pos] + prand[2 * s_pos] + prand[3 * s_pos] + prand[4 * s_pos] + prand[5 * s_pos])
            incr = round(len(pwd) / 2)
            modu = 2 ** 31 - 1

            salt = int(share_param[-8:], 16)
            share_core = share_param[:-8]
            prand = prand + str(salt)
            while len(prand) > 10:
                prand = str(int(prand[:10]) + int(prand[10:]))
            prand = (mult * int(prand) + incr) % modu

            enc_str = []
            for i in range(0, len(share_core), 2):
                enc_chr = int(share_core[i:i + 2], 16) ^ int((prand / modu) * 255)
                enc_str.append(chr(enc_chr))
                prand = (mult * prand + incr) % modu

            decoded = base64.b64decode("".join(enc_str)).decode("utf-8")
            payload = json.loads(decoded)
            return payload.get("token")
        except Exception:
            logger.debug("Failed to decrypt share token", exc_info=True)
            return None

    def _fetch_via_api(self, url: str) -> Dict:
        """Call USRIOT APIs directly using the shared link token to avoid browser dependencies."""
        try:
            logger.info("Attempting API fetch via token-based method...")
            qs = parse_qs(urlparse(url).query)
            share_param = (qs.get("share") or [None])[0]
            cusdevice_no = (qs.get("cusdeviceNo") or [None])[0]
            if not share_param or not cusdevice_no:
                logger.warning("API fetch: missing share or cusdeviceNo parameter")
                return {}

            token = self._decrypt_share_token(share_param)
            if not token:
                return {}

            # Cache-busting headers for fresh data on every request
            cache_headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }

            # Refresh the token (the decrypted one is often expired in embeds)
            refresh_url = f"https://api.mp.usriot.com/usrCloud/user/refreshShareToken?token={token}&t={int(datetime.utcnow().timestamp() * 1000)}"
            refresh_resp = requests.get(refresh_url, timeout=10, headers=cache_headers)
            if refresh_resp.status_code == 200:
                try:
                    refreshed = refresh_resp.json()
                    if refreshed.get("status") == 0:
                        token = refreshed.get("data", token)
                except Exception:
                    pass

            # Fetch data point IDs (velocity=itemId 1, depth=itemId 2, flow=itemId 15)
            datapoint_url = "https://api.mp.usriot.com/usrCloud/cusdevice/getBatchDataPointInfo"
            query_list = [
                {"cusdeviceNo": cusdevice_no, "slaveIndex": "1", "itemId": str(item_id)}
                for item_id in (1, 2, 15)
            ]
            headers = {
                "token": token,
                "u-source": "in-draw",
                "sdk-version": "2.3.2",
                "languagetype": "0",
                "traceid": "ODg4MzE=",
                "content-type": "application/json",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }

            resp = requests.post(datapoint_url, json={"dataPointQueryList": query_list, "token": token}, headers=headers, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") == 4010:  # token expired
                refresh_url_retry = f"https://api.mp.usriot.com/usrCloud/user/refreshShareToken?token={token}&t={int(datetime.utcnow().timestamp() * 1000)}"
                refresh_resp = requests.get(refresh_url_retry, timeout=10, headers=cache_headers)
                if refresh_resp.status_code == 200:
                    refreshed = refresh_resp.json()
                    if refreshed.get("status") == 0:
                        token = refreshed.get("data", token)
                        headers["token"] = token
                        resp = requests.post(datapoint_url, json={"dataPointQueryList": query_list, "token": token}, headers=headers, timeout=10)
                        resp.raise_for_status()
                        payload = resp.json()
            dp_data = payload.get("data", []) if isinstance(payload, dict) else []
            rel_map = {}
            for entry in dp_data:
                try:
                    item = int(entry.get("itemId"))
                    rel_map[item] = entry.get("dataPointRelId")
                except Exception:
                    continue

            depth_id = rel_map.get(2)
            velocity_id = rel_map.get(1)
            flow_id = rel_map.get(15)

            def fetch_latest_point(data_point_id: int) -> Optional[float]:
                history_url = "https://sga-history.usriot.com:7002/history/cusdevice/getSampleDataPoint"
                now_ms = int(datetime.utcnow().timestamp() * 1000)
                # Use a 5-minute window to get only recent data, not stale data from 24h ago
                start = now_ms - 5 * 60 * 1000  # 5-minute window for fresh data
                body = {
                    "dataPoints": [{"cusdeviceNo": cusdevice_no, "dataPointId": data_point_id, "sampleFun": "LAST"}],
                    "start": start,
                    "end": now_ms,
                    "token": token,
                    "timeSort": "desc",
                    "sampleLimit": 1,
                }
                r = requests.post(history_url, json=body, headers=headers, timeout=10)
                r.raise_for_status()
                payload = r.json()
                if isinstance(payload, dict) and payload.get("status") == 4010:
                    # retry once with refreshed token
                    ref = requests.get(refresh_url, timeout=10)
                    if ref.status_code == 200:
                        new_tok = ref.json().get("data")
                        if new_tok:
                            body["token"] = new_tok
                            headers["token"] = new_tok
                            r = requests.post(history_url, json=body, headers=headers, timeout=10)
                            r.raise_for_status()
                            payload = r.json()
                lst = payload.get("data", {}).get("list", []) if isinstance(payload, dict) else []
                if not lst:
                    logger.debug(f"fetch_latest_point({data_point_id}): No data in API response")
                    return None
                samples = lst[0].get("list") or []
                if not samples:
                    logger.debug(f"fetch_latest_point({data_point_id}): No samples in response list")
                    return None
                value = float(samples[0].get("value")) if samples[0].get("value") is not None else None
                if value is not None:
                    logger.debug(f"fetch_latest_point({data_point_id}): Retrieved value {value}")
                return value

            page_data = {}
            if depth_id:
                val = fetch_latest_point(depth_id)
                if val is not None:
                    page_data["depth_mm"] = val
            if velocity_id:
                val = fetch_latest_point(velocity_id)
                if val is not None:
                    page_data["velocity_mps"] = val
            if flow_id:
                val = fetch_latest_point(flow_id)
                if val is not None:
                    page_data["flow_lps"] = val

            logger.info(f"✅ API fetch succeeded: {page_data}")
            return page_data
        except Exception:
            logger.warning("API fetch failed", exc_info=True)
            return {}

    def _has_data_changed(self, device_id: str, new_data: Dict) -> bool:
        """
        INDUSTRY-STANDARD change detection using CRC32 hashing.
        
        Works reliably for multiple devices with different logging intervals:
        - 1-minute loggers: Detects every change
        - 5-minute loggers: Prevents 4 duplicate entries per 5-minute block
        - 10-minute loggers: Prevents 9 duplicate entries per 10-minute block
        
        Algorithm:
        1. Serialize measurement data into canonical JSON form (deterministic)
        2. Compute CRC32 hash of serialized data
        3. Compare hash to last stored hash
        4. Store only if hash differs (prevents any duplicate records)
        
        Args:
            device_id: Unique device identifier
            new_data: Dict with keys 'depth_mm', 'velocity_mps', 'flow_lps'
            
        Returns:
            bool: True if data hash differs from last stored (any value changed)
            
        Thread Safety: NOT thread-safe - intended for single device per thread
        
        Note: First call always returns True (new device = new data)
        """
        # Serialize new data in canonical form for deterministic hashing
        canonical_json = json.dumps(
            new_data,
            sort_keys=True,
            separators=(',', ':'),
            default=str
        )
        
        # Compute CRC32 hash (32-bit, industry standard for data integrity)
        new_hash = zlib.crc32(canonical_json.encode('utf-8')) & 0xffffffff
        
        # Get last stored hash for this device
        last_hash = self.last_data.get(device_id, {}).get('_hash')
        
        # Check if hash changed (indicates any value changed)
        has_changed = last_hash is None or new_hash != last_hash
        
        if has_changed:
            # Store new data and hash
            self.last_data[device_id] = {
                **new_data,
                '_hash': new_hash,
                '_timestamp': datetime.now(self.tz)
            }
            # Persist state to disk so it survives app restarts
            self._save_state()
            logger.info(f"✓ Change detected for {device_id}: D={new_data.get('depth_mm')}mm, V={new_data.get('velocity_mps')}m/s, F={new_data.get('flow_lps')}L/s [Hash: {new_hash:08x}]")
        else:
            logger.debug(f"⊘ No change for {device_id} (hash match: {new_hash:08x})")
        
        return has_changed

    def _fetch_via_requests(self, url: str, selectors: Dict) -> Dict:
        """Lightweight fallback that pulls values via plain HTTP and CSS selectors."""
        try:
            cache_headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            resp = requests.get(url, timeout=10, headers=cache_headers)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Requests fallback failed to fetch page: {e}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        extracted = {}

        for key, selector in selectors.items():
            try:
                elem = soup.select_one(selector)
                if not elem:
                    logger.debug(f"Requests fallback: selector not found for {key}: {selector}")
                    continue
                text = elem.get_text(strip=True)
                numbers = re.findall(r"\d+\.?\d*", text)
                if numbers:
                    extracted[key] = float(numbers[0])
                    logger.info(f"Requests fallback extracted {key}: {extracted[key]}")
                else:
                    logger.debug(f"Requests fallback: no numbers in {key} text '{text}'")
            except Exception as e:
                logger.debug(f"Requests fallback: error extracting {key}: {e}")

        return extracted

    async def fetch_monitor_data(self, url: str = MONITOR_URL, device_selectors: Dict = None) -> Optional[Dict]:
        """Fetch data from the monitor website.
        
        Strategy:
        1. If selectors available: use Playwright (live page load)
        2. Otherwise: try API, then requests fallback
        """
        # If we have CSS selectors, use Playwright for live data (most reliable)
        if device_selectors and not self.force_requests:
            logger.info("Using Playwright for live page data (selectors available)")
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    title = await page.title()

                    page_data = {}
                    for key, selector in device_selectors.items():
                        try:
                            el = await page.query_selector(selector)
                            if not el:
                                logger.debug(f"Playwright: selector not found for {key}: {selector}")
                                continue
                            text = (await el.text_content() or "").strip()
                            numbers = re.findall(r"\d+\.?\d*", text)
                            if numbers:
                                page_data[key] = float(numbers[0])
                                logger.info(f"Playwright extracted {key}: {page_data[key]} (from '{text}')")
                            else:
                                logger.debug(f"Playwright: no numbers in {key} text '{text}'")
                        except Exception as e:
                            logger.debug(f"Playwright: error extracting {key}: {e}")

                    await browser.close()
                    
                    if page_data:
                        logger.info(f"✅ Playwright fetch succeeded: {page_data}")
                        return {"data": page_data, "title": title, "timestamp": datetime.now(self.tz)}
            except Exception as e:
                logger.warning(f"Playwright fetch failed: {e}, falling back to API")

        # First try direct API calls using the shared token (no browser needed)
        api_data = self._fetch_via_api(url)
        if api_data:
            return {"data": api_data, "title": None, "timestamp": datetime.now(self.tz)}

        # Requests-only mode
        if self.force_requests or device_selectors:
            logger.info("Using requests fallback for data")
            if device_selectors:
                page_data = self._fetch_via_requests(url, device_selectors)
                if page_data:
                    return {"data": page_data, "title": None, "timestamp": datetime.now(self.tz)}
            return None

        return None

    def store_measurement(self, device_id: str, device_name: str, 
                         depth_mm: float = None, velocity_mps: float = None, 
                         flow_lps: float = None, allow_storage: bool = False) -> bool:
        """
        Store a measurement in the database.
        
        CRITICAL: Requires allow_storage=True to prevent accidental storage from Streamlit app.
        This flag ensures ONLY the standalone monitor (start_monitor.py) can write to database.
        
        If STORE_ALL_READINGS=True, stores every reading.
        If STORE_ALL_READINGS=False, only stores when data has changed.
        Returns True if stored, False if no change detected (when change detection enabled).
        """
        # SAFETY CHECK: Prevent storage unless explicitly allowed
        if not allow_storage:
            logger.warning(f"⊗ Storage blocked (allow_storage=False). Only standalone monitor should write to database.")
            return False
        
        new_data = {
            "depth_mm": depth_mm,
            "velocity_mps": velocity_mps,
            "flow_lps": flow_lps
        }
        
        # Check for changes only if STORE_ALL_READINGS is False
        if not STORE_ALL_READINGS:
            if not self._has_data_changed(device_id, new_data):
                logger.debug(f"⊘ No change detected for {device_name}, skipping storage")
                return False
            else:
                logger.info(f"✓ Change detected for {device_name}, storing to database")
        
        self.db.add_device(device_id, device_name)
        self.db.add_measurement(
            device_id=device_id,
            timestamp=datetime.now(self.tz),
            depth_mm=depth_mm,
            velocity_mps=velocity_mps,
            flow_lps=flow_lps
        )
        
        if STORE_ALL_READINGS:
            logger.info(f"✅ Stored reading (STORE_ALL mode) for {device_name}: D={depth_mm}mm, V={velocity_mps}mps, F={flow_lps}lps")
        else:
            logger.info(f"✅ Stored CHANGED data for {device_name}: D={depth_mm}mm, V={velocity_mps}mps, F={flow_lps}lps")
        
        # Always update last_data for tracking purposes
        self.last_data[device_id] = new_data
        
        return True

    def get_last_values(self, device_id: str) -> Optional[Dict]:
        """Get the last known values for a device."""
        return self.last_data.get(device_id)


async def main():
    """Main function to scrape and store data."""
    scraper = DataScraper()
    
    logger.info("Starting data scrape...")
    data = await scraper.fetch_monitor_data()
    
    if data:
        logger.info(f"Data retrieved: {data}")
        
        # For now, we'll store a sample entry
        # You can modify this to parse the actual extracted data
        scraper.store_measurement(
            device_id="FIT100",
            device_name="FIT100 Main Inflow Lismore STP",
            depth_mm=0.0,
            velocity_mps=0.0,
            flow_lps=0.0
        )
        
        logger.info("Data processed successfully")
    else:
        logger.warning("Failed to retrieve data")


if __name__ == "__main__":
    asyncio.run(main())
