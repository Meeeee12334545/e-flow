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
from config import MONITOR_INTERVAL, MONITOR_ENABLED, MONITOR_URL

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
        """Check the monitor website for updates."""
        self.check_count += 1
        
        try:
            logger.info(f"[Check #{self.check_count}] Checking for data updates...")
            
            # Fetch data from monitor
            data = await self.scraper.fetch_monitor_data(MONITOR_URL)
            
            if not data:
                logger.warning("Failed to retrieve data from monitor")
                self.error_count += 1
                return
            
            # Parse and store if changed
            device_id = "FIT100"
            device_name = "FIT100 Main Inflow Lismore STP"
            
            # Try to extract actual values from the page data
            # For now using placeholder values - adjust based on actual data structure
            depth_mm = 0.0
            velocity_mps = 0.0
            flow_lps = 0.0
            
            # Attempt to parse from extracted data
            page_data = data.get("data", {})
            if isinstance(page_data, dict):
                if "depth" in page_data:
                    try:
                        depth_mm = float(str(page_data["depth"]).replace("mm", "").strip())
                    except (ValueError, AttributeError):
                        pass
                
                if "velocity" in page_data:
                    try:
                        velocity_mps = float(str(page_data["velocity"]).replace("mps", "").strip())
                    except (ValueError, AttributeError):
                        pass
                
                if "flow" in page_data:
                    try:
                        flow_lps = float(str(page_data["flow"]).replace("lps", "").strip())
                    except (ValueError, AttributeError):
                        pass
            
            # Store if changed
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
                logger.info("No changes detected")
                
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
