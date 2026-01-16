#!/usr/bin/env python
"""
Continuous monitoring service for the USRIOT monitor.
Runs every 1 minute and only stores data when changes are detected.
"""

import asyncio
import sys
import logging
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from scraper import DataScraper
from database import FlowDatabase
from config import MONITOR_INTERVAL, MONITOR_ENABLED, MONITOR_URL, DEVICES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('monitor.log')
    ]
)
logger = logging.getLogger(__name__)

DEFAULT_TZ = "Australia/Brisbane"


class ContinuousMonitor:
    """Continuous monitoring service."""

    def __init__(self):
        self.db = FlowDatabase()
        self.scraper = DataScraper(self.db)
        self.scheduler = BlockingScheduler()
        self.check_count = 0
        self.update_count = 0
        self.error_count = 0

    async def check_for_updates(self):
        """Check the monitor website for updates every 1 minute."""
        self.check_count += 1
        
        try:
            logger.info(f"[Check #{self.check_count}] Checking for data updates...")
            
            # Get device config with CSS selectors
            device_id = "FIT100"
            device_info = DEVICES.get(device_id, {})
            device_name = device_info.get("name", "FIT100 Main Inflow Lismore STP")
            device_selectors = device_info.get("selectors", None)
            
            # Fetch data from monitor with CSS selectors
            data = await self.scraper.fetch_monitor_data(MONITOR_URL, device_selectors)
            
            if not data:
                logger.warning("Failed to retrieve data from monitor")
                self.error_count += 1
                return
            
            # Extract actual values from the page data
            depth_mm = None
            velocity_mps = None
            flow_lps = None
            
            # Attempt to parse from extracted data - handle both old and new key formats
            page_data = data.get("data", {})
            if isinstance(page_data, dict):
                # Look for depth
                if "depth_mm" in page_data:
                    depth_mm = page_data["depth_mm"]
                    logger.info(f"  Depth: {depth_mm} mm")
                elif "depth" in page_data:
                    try:
                        val = page_data["depth"]
                        if isinstance(val, (int, float)):
                            depth_mm = float(val)
                        else:
                            depth_mm = float(str(val).replace("mm", "").replace("m", "").strip())
                        logger.info(f"  Depth: {depth_mm} mm")
                    except (ValueError, AttributeError, TypeError) as e:
                        logger.warning(f"Could not parse depth value: {page_data.get('depth')} - {e}")
                
                # Look for velocity
                if "velocity_mps" in page_data:
                    velocity_mps = page_data["velocity_mps"]
                    logger.info(f"  Velocity: {velocity_mps} m/s")
                elif "velocity" in page_data:
                    try:
                        val = page_data["velocity"]
                        if isinstance(val, (int, float)):
                            velocity_mps = float(val)
                        else:
                            velocity_mps = float(str(val).replace("mps", "").replace("m/s", "").replace("m", "").strip())
                        logger.info(f"  Velocity: {velocity_mps} m/s")
                    except (ValueError, AttributeError, TypeError) as e:
                        logger.warning(f"Could not parse velocity value: {page_data.get('velocity')} - {e}")
                
                # Look for flow
                if "flow_lps" in page_data:
                    flow_lps = page_data["flow_lps"]
                    logger.info(f"  Flow: {flow_lps} L/s")
                elif "flow" in page_data:
                    try:
                        val = page_data["flow"]
                        if isinstance(val, (int, float)):
                            flow_lps = float(val)
                        else:
                            flow_lps = float(str(val).replace("lps", "").replace("l/s", "").replace("L/s", "").strip())
                        logger.info(f"  Flow: {flow_lps} L/s")
                    except (ValueError, AttributeError, TypeError) as e:
                        logger.warning(f"Could not parse flow value: {page_data.get('flow')} - {e}")
            
            # Only store if we have at least one value
            if depth_mm is not None or velocity_mps is not None or flow_lps is not None:
                stored = self.scraper.store_measurement(
                    device_id=device_id,
                    device_name=device_name,
                    depth_mm=depth_mm,
                    velocity_mps=velocity_mps,
                    flow_lps=flow_lps
                )
                
                if stored:
                    self.update_count += 1
                    logger.info(f"✅ Data updated! (Update #{self.update_count})")
                else:
                    logger.debug("No changes detected from previous measurement")
            else:
                logger.warning("⚠️  Could not extract any data values from the page")
                
        except Exception as e:
            logger.error(f"❌ Error during check: {e}", exc_info=True)
            self.error_count += 1

    def run_check(self):
        """Wrapper to run async check from synchronous scheduler."""
        asyncio.run(self.check_for_updates())

    def start_monitoring(self):
        """Start the continuous monitoring service."""
        if not MONITOR_ENABLED:
            logger.error("Monitoring is disabled in config.py")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 CONTINUOUS MONITOR STARTED")
        logger.info("=" * 60)
        logger.info(f"📍 Target: {MONITOR_URL[:80]}...")
        logger.info(f"⏱️  Interval: Every {MONITOR_INTERVAL} seconds")
        logger.info(f"📊 Database: {self.db.db_path}")
        logger.info("=" * 60)
        logger.info("Monitoring will detect changes and store only new data")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Schedule the job
        self.scheduler.add_job(
            self.run_check,
            IntervalTrigger(seconds=MONITOR_INTERVAL),
            id='monitor_job',
            name='Monitor USRIOT for updates',
            replace_existing=True
        )
        
        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            logger.info("\n" + "=" * 60)
            logger.info("📊 MONITORING STOPPED")
            logger.info("=" * 60)
            logger.info(f"Total checks: {self.check_count}")
            logger.info(f"Data updates: {self.update_count}")
            logger.info(f"Errors: {self.error_count}")
            logger.info("=" * 60)


def main():
    """Main entry point."""
    monitor = ContinuousMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
