import asyncio
import json
import os
import re
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
        Extract depth, velocity, and flow data from the USRIOT dashboard.
        
        The dashboard loads data dynamically via JavaScript.
        We'll look for:
        1. JSON data in window objects
        2. Common data attributes
        3. Text content in specific elements
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
            
            # Wait additional time for charts/data to fully render
            await page.wait_for_timeout(3000)
            
            page_data = {}
            
            # Method 1: Try to get data from JavaScript window object
            try:
                # Attempt to extract data from various window properties
                window_data = await page.evaluate("""
                    () => {
                        const data = {};
                        
                        // Look for common data containers in USRIOT
                        if (window.chartData) data.chartData = window.chartData;
                        if (window.deviceData) data.deviceData = window.deviceData;
                        if (window.sensorData) data.sensorData = window.sensorData;
                        if (window.__data) data.__data = window.__data;
                        if (window.config) data.config = window.config;
                        
                        return data;
                    }
                """)
                
                if window_data and any(window_data.values()):
                    page_data['window'] = window_data
                    logger.debug(f"Extracted window data: {window_data}")
            except Exception as e:
                logger.debug(f"Could not extract window data: {e}")
            
            # Method 2: Look for data in all text content on page
            # Get all visible text and look for patterns with numbers
            try:
                body_text = await page.inner_text("body")
                
                # Look for common patterns in the text
                import re
                
                # Pattern for depth values (e.g., "Depth: 150.5 mm" or "150.5mm")
                depth_match = re.search(r'(?:depth|D)[\s:]*(\d+\.?\d*)\s*(?:mm|m)(?:\s|$)', body_text, re.IGNORECASE)
                if depth_match:
                    try:
                        page_data['depth'] = float(depth_match.group(1))
                        logger.debug(f"Found depth: {page_data['depth']} mm")
                    except ValueError:
                        pass
                
                # Pattern for velocity values (e.g., "Velocity: 0.5 m/s")
                velocity_match = re.search(r'(?:velocity|V)[\s:]*(\d+\.?\d*)\s*(?:m/s|mps|m)?(?:\s|$)', body_text, re.IGNORECASE)
                if velocity_match:
                    try:
                        page_data['velocity'] = float(velocity_match.group(1))
                        logger.debug(f"Found velocity: {page_data['velocity']} m/s")
                    except ValueError:
                        pass
                
                # Pattern for flow values (e.g., "Flow: 25.5 L/s" or "25.5 lps")
                flow_match = re.search(r'(?:flow|F)[\s:]*(\d+\.?\d*)\s*(?:L/s|lps|l/s)(?:\s|$)', body_text, re.IGNORECASE)
                if flow_match:
                    try:
                        page_data['flow'] = float(flow_match.group(1))
                        logger.debug(f"Found flow: {page_data['flow']} L/s")
                    except ValueError:
                        pass
                        
            except Exception as e:
                logger.debug(f"Error extracting from body text: {e}")
            
            # Method 3: Look for elements with specific data attributes or classes
            try:
                elements = await page.query_selector_all('[data-value], [data-metric], span, div')
                
                for elem in elements[:50]:  # Check first 50 elements to avoid performance issues
                    try:
                        text = await elem.inner_text()
                        text_lower = text.lower()
                        
                        # Check for depth indicators
                        if any(x in text_lower for x in ['depth', 'd:', 'depth:']):
                            # Extract numbers from the text
                            nums = re.findall(r'\d+\.?\d*', text)
                            if nums and 'depth' not in page_data:
                                page_data['depth'] = float(nums[0])
                        
                        # Check for velocity indicators  
                        if any(x in text_lower for x in ['velocity', 'v:', 'velocity:']):
                            nums = re.findall(r'\d+\.?\d*', text)
                            if nums and 'velocity' not in page_data:
                                page_data['velocity'] = float(nums[0])
                        
                        # Check for flow indicators
                        if any(x in text_lower for x in ['flow', 'f:', 'flow:']):
                            nums = re.findall(r'\d+\.?\d*', text)
                            if nums and 'flow' not in page_data:
                                page_data['flow'] = float(nums[0])
                                
                    except Exception as e:
                        continue
                        
            except Exception as e:
                logger.debug(f"Error querying elements: {e}")
            
            # Get the page title (may contain device info)
            title = await page.title()
            
            logger.info(f"Extracted data: {page_data}")
            
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
