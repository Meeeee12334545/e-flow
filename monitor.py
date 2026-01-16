#!/usr/bin/env python
"""
Continuous monitoring service for the USRIOT monitor.
Runs every 1 minute and only stores data when changes are detected.

PRODUCTION-READY FEATURES:
- Automatic retry on failures
- Graceful error recovery
- Health checks and monitoring
- Automatic restart on critical errors
- Comprehensive logging
"""

import asyncio
import sys
import logging
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from scraper import DataScraper
from database import FlowDatabase
from config import MONITOR_INTERVAL, MONITOR_ENABLED, MONITOR_URL, DEVICES

# Configure logging with rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('monitor.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants for reliability
MAX_CONSECUTIVE_ERRORS = 10  # Restart after 10 consecutive failures
MAX_RETRY_ATTEMPTS = 3  # Retry each operation 3 times
RETRY_DELAY = 5  # Seconds between retries
HEALTH_CHECK_INTERVAL = 300  # Health check every 5 minutes

DEFAULT_TZ = "Australia/Brisbane"


class ContinuousMonitor:
    """Continuous monitoring service with automatic recovery."""

    def __init__(self):
        self.db = FlowDatabase()
        self.scraper = DataScraper(self.db)
        self.scheduler = BlockingScheduler()
        self.check_count = 0
        self.update_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_success_time = datetime.now()
        self.last_health_check = datetime.now()
        self.is_healthy = True
        self._shutdown = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on signals."""
        logger.info("\n🛑 Shutdown signal received, stopping gracefully...")
        self._shutdown = True
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def check_for_updates_with_retry(self):
        """Check for updates with automatic retry logic."""
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                success = await self.check_for_updates()
                if success:
                    self.consecutive_errors = 0
                    self.last_success_time = datetime.now()
                    return True
                else:
                    logger.warning(f"Attempt {attempt}/{MAX_RETRY_ATTEMPTS} failed, retrying in {RETRY_DELAY}s...")
                    if attempt < MAX_RETRY_ATTEMPTS:
                        await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Attempt {attempt}/{MAX_RETRY_ATTEMPTS} error: {e}")
                if attempt < MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY)
        
        # All retries failed
        self.consecutive_errors += 1
        logger.error(f"❌ All {MAX_RETRY_ATTEMPTS} attempts failed. Consecutive errors: {self.consecutive_errors}")
        
        # Check if we need to restart
        if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.critical(f"💥 CRITICAL: {MAX_CONSECUTIVE_ERRORS} consecutive failures! System needs attention!")
            self.is_healthy = False
        
        return False

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
                return False
                
        except Exception as e:
            logger.error(f"❌ Error during check: {e}", exc_info=True)
            self.error_count += 1
            return False
        
        return True

    def perform_health_check(self):
        """Perform system health check."""
        now = datetime.now()
        time_since_last_success = (now - self.last_success_time).total_seconds()
        
        # Log health status every 5 minutes
        if (now - self.last_health_check).total_seconds() >= HEALTH_CHECK_INTERVAL:
            logger.info("=" * 60)
            logger.info("💚 HEALTH CHECK")
            logger.info("=" * 60)
            logger.info(f"Status: {'🟢 HEALTHY' if self.is_healthy else '🔴 UNHEALTHY'}")
            logger.info(f"Total checks: {self.check_count}")
            logger.info(f"Successful updates: {self.update_count}")
            logger.info(f"Total errors: {self.error_count}")
            logger.info(f"Consecutive errors: {self.consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}")
            logger.info(f"Last success: {int(time_since_last_success)}s ago")
            logger.info(f"Success rate: {(self.update_count / max(1, self.check_count) * 100):.1f}%")
            logger.info("=" * 60)
            self.last_health_check = now
        
        # Alert if no success for too long
        if time_since_last_success > 600:  # 10 minutes
            logger.warning(f"⚠️  WARNING: No successful data collection in {int(time_since_last_success)}s")

    def run_check(self):
        """Wrapper to run async check from synchronous scheduler."""
        try:
            asyncio.run(self.check_for_updates_with_retry())
            self.perform_health_check()
        except Exception as e:
            logger.error(f"Critical error in run_check: {e}", exc_info=True)

    def start_monitoring(self):
        """Start the continuous monitoring service with auto-restart capability."""
        if not MONITOR_ENABLED:
            logger.error("Monitoring is disabled in config.py")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 CONTINUOUS MONITOR STARTED (PRODUCTION MODE)")
        logger.info("=" * 60)
        logger.info(f"📍 Target: {MONITOR_URL[:80]}...")
        logger.info(f"⏱️  Interval: Every {MONITOR_INTERVAL} seconds")
        logger.info(f"📊 Database: {self.db.db_path}")
        logger.info(f"🔄 Auto-retry: {MAX_RETRY_ATTEMPTS} attempts per check")
        logger.info(f"💚 Health checks: Every {HEALTH_CHECK_INTERVAL} seconds")
        logger.info(f"🛡️  Max consecutive errors: {MAX_CONSECUTIVE_ERRORS}")
        logger.info("=" * 60)
        logger.info("✅ Monitoring will detect changes and store only new data")
        logger.info("✅ Automatic retry on failures")
        logger.info("✅ Health monitoring enabled")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Run initial check
        logger.info("Running initial data check...")
        self.run_check()
        
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
            pass
        finally:
            logger.info("\n" + "=" * 60)
            logger.info("📊 MONITORING STOPPED")
            logger.info("=" * 60)
            logger.info(f"Total checks: {self.check_count}")
            logger.info(f"Data updates: {self.update_count}")
            logger.info(f"Total errors: {self.error_count}")
            logger.info(f"Final status: {'🟢 HEALTHY' if self.is_healthy else '🔴 UNHEALTHY'}")
            if self.check_count > 0:
                logger.info(f"Success rate: {(self.update_count / self.check_count * 100):.1f}%")
            logger.info("=" * 60)


def main():
    """Main entry point with automatic restart capability."""
    restart_count = 0
    max_restarts = 5
    restart_delay = 60  # seconds
    
    while restart_count < max_restarts:
        try:
            logger.info(f"\n{'🔄 RESTARTING MONITOR ' if restart_count > 0 else ''}(Attempt {restart_count + 1}/{max_restarts})")
            monitor = ContinuousMonitor()
            monitor.start_monitoring()
            
            # If we get here, it's a clean exit
            logger.info("Monitor stopped cleanly")
            break
            
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
            
        except Exception as e:
            restart_count += 1
            logger.error(f"💥 CRITICAL ERROR: {e}", exc_info=True)
            
            if restart_count < max_restarts:
                logger.warning(f"⏳ Waiting {restart_delay}s before restart attempt {restart_count + 1}/{max_restarts}...")
                time.sleep(restart_delay)
            else:
                logger.critical(f"❌ MAX RESTARTS REACHED ({max_restarts}). Monitor requires manual intervention.")
                sys.exit(1)


if __name__ == "__main__":
    main()
