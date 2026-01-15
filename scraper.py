import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin
import logging

from playwright.async_api import async_playwright, Page
import pytz

from database import FlowDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The website URL - can be parameterized
MONITOR_URL = "https://mp.usriot.com/draw/show.html?lang=en&lightbox=1&highlight=0000ff&layers=1&nav=1&title=FIT100%20Main%20Inflow%20Lismore%20STP&id=97811&link=Lpu7Q2CM3osZ&model=1&cusdeviceNo=0000088831000010&share=48731ec89bf8108b2a451fbffa590da4f0cf419a5623beb7d48c1060e3f0dbe177e28054c26be49bbabca1da5b977e7c16a47891d94f70a08a876d24c55416854700de7cc51a06f8e102798d6ecc39478ef1394a246efa109e6c6358e30a259010a5c403c71756173c90cf1e10ced6fdf54d90881c05559f2c8c5717ee8109210672fa3574a9c04a465bc0df8b9c354da487a7bcb6679a7ec32276ba3610301be80d8c7588ef1797ca01fb6b87e74a8b6e5cd0ac668918d02ae99a7966f57ecf603b63a12d4b0a160d3ac0920254d6836f1e26d244412f82859f7f7b0df7b8406e95ef97a7cb2302a07826d3b8cba81721c5bce1d7e9bf0b01f32d1d0330a44301a1ab0f"

DEFAULT_TZ = "Australia/Brisbane"


class DataScraper:
    """Scrapes depth, velocity, and flow data from the monitor website."""

    def __init__(self, db: FlowDatabase = None):
        self.db = db or FlowDatabase()
        self.tz = pytz.timezone(DEFAULT_TZ)
        self.last_data = {}  # Track last known values for change detection

    def _has_data_changed(self, device_id: str, new_data: Dict) -> bool:
        """
        Check if data has changed compared to last known values.
        Returns True if this is new/changed data, False if it's the same as before.
        """
        if device_id not in self.last_data:
            # First time seeing this device
            self.last_data[device_id] = new_data
            return True
        
        last = self.last_data[device_id]
        
        # Compare depth, velocity, and flow values
        depth_changed = last.get("depth_mm") != new_data.get("depth_mm")
        velocity_changed = last.get("velocity_mps") != new_data.get("velocity_mps")
        flow_changed = last.get("flow_lps") != new_data.get("flow_lps")
        
        has_changed = depth_changed or velocity_changed or flow_changed
        
        if has_changed:
            self.last_data[device_id] = new_data
            logger.info(f"Change detected for {device_id}: D={new_data.get('depth_mm')}mm, V={new_data.get('velocity_mps')}mps, F={new_data.get('flow_lps')}lps")
        else:
            logger.debug(f"No change for {device_id}")
        
        return has_changed

    async def extract_data_from_page(self, page: Page) -> Optional[Dict]:
        """
        Extract depth, velocity, and flow data from the page.
        
        This method looks for data in various formats:
        - JSON in script tags
        - Data attributes
        - Text content
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Try to extract data from the page
            # This is a flexible approach that tries multiple extraction methods
            
            # Method 1: Look for JSON data in script tags
            scripts = await page.query_selector_all("script")
            page_data = {}
            
            for script in scripts:
                try:
                    content = await script.get_attribute("innerHTML")
                    if content and ("depth" in content.lower() or "velocity" in content.lower()):
                        # Try to parse JSON from script content
                        text = content.strip()
                        if text.startswith("{") or text.startswith("["):
                            page_data = json.loads(text)
                            logger.info(f"Extracted JSON data: {page_data}")
                            break
                except Exception as e:
                    continue
            
            # Method 2: Check for data in page attributes or elements
            if not page_data:
                depth_elem = await page.query_selector('[data-depth], [data-value*="depth"], .depth')
                velocity_elem = await page.query_selector('[data-velocity], [data-value*="velocity"], .velocity')
                flow_elem = await page.query_selector('[data-flow], [data-value*="flow"], .flow')
                
                if depth_elem:
                    depth_text = await depth_elem.inner_text()
                    page_data["depth"] = depth_text
                
                if velocity_elem:
                    velocity_text = await velocity_elem.inner_text()
                    page_data["velocity"] = velocity_text
                
                if flow_elem:
                    flow_text = await flow_elem.inner_text()
                    page_data["flow"] = flow_text
            
            # Get the page title (may contain device info)
            title = await page.title()
            
            return {
                "data": page_data,
                "title": title,
                "timestamp": datetime.now(self.tz)
            }
            
        except Exception as e:
            logger.error(f"Error extracting data: {e}")
            return None

    async def fetch_monitor_data(self, url: str = MONITOR_URL) -> Optional[Dict]:
        """Fetch data from the monitor website using Playwright."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                logger.info(f"Loading page: {url}")
                await page.goto(url, wait_until="load", timeout=15000)
                
                # Wait a bit for any dynamic content to load
                await page.wait_for_timeout(2000)
                
                # Extract data
                data = await self.extract_data_from_page(page)
                
                return data
                
            except Exception as e:
                logger.error(f"Error fetching data from monitor: {e}")
                return None
            finally:
                await browser.close()

    def store_measurement(self, device_id: str, device_name: str, 
                         depth_mm: float = None, velocity_mps: float = None, 
                         flow_lps: float = None) -> bool:
        """
        Store a measurement in the database only if data has changed.
        Returns True if stored, False if no change detected.
        """
        new_data = {
            "depth_mm": depth_mm,
            "velocity_mps": velocity_mps,
            "flow_lps": flow_lps
        }
        
        # Check for changes
        if not self._has_data_changed(device_id, new_data):
            return False
        
        self.db.add_device(device_id, device_name)
        self.db.add_measurement(
            device_id=device_id,
            timestamp=datetime.now(self.tz),
            depth_mm=depth_mm,
            velocity_mps=velocity_mps,
            flow_lps=flow_lps
        )
        logger.info(f"✅ Stored measurement for {device_name}: D={depth_mm}mm, V={velocity_mps}mps, F={flow_lps}lps")
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
