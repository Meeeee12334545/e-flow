import asyncio
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from urllib.parse import urljoin
import logging
import requests
from bs4 import BeautifulSoup
import pytz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

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

    async def fetch_monitor_data(self, url: str = MONITOR_URL, device_selectors: Dict = None) -> Optional[Dict]:
        """Fetch data from the monitor website using Selenium and JavaScript selectors."""
        driver = None
        try:
            logger.info(f"Loading page with Selenium: {url[:80]}...")
            
            # Setup Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Launch browser with auto-managed chromedriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Load the page
            driver.get(url)
            
            # Wait for page to load
            logger.info("Waiting for page to load...")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Give JavaScript time to render data
            driver.implicitly_wait(3)
            
            page_data = {}
            
            # Extract data using CSS selectors with JavaScript if provided
            if device_selectors:
                for key, selector in device_selectors.items():
                    try:
                        # Use querySelector to find element
                        js_code = f"""
                        var elem = document.querySelector('{selector}');
                        return elem ? elem.textContent.trim() : null;
                        """
                        text = driver.execute_script(js_code)
                        
                        if text:
                            # Extract numeric value
                            numbers = re.findall(r'\d+\.?\d*', text)
                            if numbers:
                                page_data[key] = float(numbers[0])
                                logger.info(f"✅ Extracted {key}: {page_data[key]} (from '{text}')")
                            else:
                                logger.warning(f"⚠️  No numbers found in {key}: '{text}'")
                        else:
                            logger.warning(f"⚠️  Selector not found for {key}: {selector}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️  Error extracting {key}: {e}")
            else:
                # Fallback: try to find elements by common patterns
                logger.info("No selectors provided, attempting pattern matching...")
                try:
                    spans = driver.find_elements(By.TAG_NAME, "span")
                    for span in spans[:100]:  # Check first 100 spans
                        try:
                            text = span.text.strip()
                            if text:
                                if "depth" in text.lower():
                                    nums = re.findall(r'\d+\.?\d*', text)
                                    if nums:
                                        page_data['depth_mm'] = float(nums[0])
                                elif "velocity" in text.lower():
                                    nums = re.findall(r'\d+\.?\d*', text)
                                    if nums:
                                        page_data['velocity_mps'] = float(nums[0])
                                elif "flow" in text.lower():
                                    nums = re.findall(r'\d+\.?\d*', text)
                                    if nums:
                                        page_data['flow_lps'] = float(nums[0])
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Error in fallback extraction: {e}")
            
            # Get page title
            title = driver.title
            
            logger.info(f"Extracted data: {page_data}")
            
            return {
                "data": page_data,
                "title": title,
                "timestamp": datetime.now(self.tz)
            }
            
        except TimeoutException:
            logger.error("Timeout waiting for page to load")
            return None
        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)
            return None
        finally:
            if driver:
                driver.quit()

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
