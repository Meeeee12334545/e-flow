#!/usr/bin/env python
"""
Continuous monitoring service for the USRIOT monitor.
Runs every MONITOR_INTERVAL seconds and stores data only when changes are detected
unless configured to store all readings.

Production features:
- Automatic retry on failures
- Graceful error recovery
- Health checks and monitoring
- Automatic restart on critical errors
- Rotating log files + stdout logging
"""

import asyncio
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import time
import signal
from datetime import datetime, timedelta
from pathlib import Path
import atexit

try:
    import fcntl  # Unix-only; used for advisory file locking
except ImportError:  # pragma: no cover - non-Unix
    fcntl = None

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from scraper import DataScraper
from database import FlowDatabase
from config import MONITOR_INTERVAL, MONITOR_ENABLED, MONITOR_URL, DEVICES, STORE_ALL_READINGS, EXIT_ON_UNHEALTHY

# Configure logging with rotation
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

file_handler = RotatingFileHandler('monitor.log', maxBytes=10 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(log_formatter)

# Avoid duplicate handlers if reinitialized
if not logger.handlers:
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
logger = logging.getLogger(__name__)

# Constants for reliability
MAX_CONSECUTIVE_ERRORS = 10  # Restart after 10 consecutive failures
MAX_RETRY_ATTEMPTS = 3  # Retry each operation 3 times
RETRY_DELAY = 5  # Seconds between retries
HEALTH_CHECK_INTERVAL = 300  # Health check every 5 minutes

DEFAULT_TZ = "Australia/Brisbane"
LOCK_FILE_PATH = Path(os.getenv("E_FLOW_MONITOR_LOCK", "/tmp/e-flow-monitor.lock"))


class SingletonProcessLock:
    """Advisory file lock to prevent multiple monitor instances.

    Uses fcntl.flock on Unix. If fcntl is unavailable, falls back to
    exclusive file creation semantics.
    """

    def __init__(self, lock_path: Path = LOCK_FILE_PATH):
        self.lock_path = Path(lock_path)
        self.fp = None
        self.locked = False

    def acquire(self) -> bool:
        try:
            # Ensure parent directory exists
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            # Open file for read/write, create if missing
            self.fp = open(self.lock_path, "a+")
            try:
                self.fp.seek(0)
                self.fp.truncate(0)
                self.fp.write(str(os.getpid()))
                self.fp.flush()
            except Exception:
                pass

            if fcntl is not None:
                try:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.locked = True
                    return True
                except BlockingIOError:
                    return False
            else:
                # Fallback: try to create a separate pid file exclusively
                # Note: not race-proof on non-Unix, but best-effort
                if self.lock_path.exists():
                    return False
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.locked = True
                return True
        except Exception:
            return False

    def release(self):
        try:
            if self.fp and fcntl is not None and self.locked:
                try:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            if self.fp:
                try:
                    self.fp.close()
                except Exception:
                    pass
            # Best-effort cleanup of lock file
            try:
                if self.lock_path.exists():
                    self.lock_path.unlink()
            except Exception:
                pass
        finally:
            self.fp = None
            self.locked = False


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
                    flow_lps=flow_lps,
                    allow_storage=True
                )
                
                if stored:
                    self.update_count += 1
                    if STORE_ALL_READINGS:
                        logger.info(f"✅ Reading stored! (Total: #{self.update_count})")
                    else:
                        logger.info(f"✅ Data changed and stored! (Update #{self.update_count})")
                else:
                    logger.info(f"ℹ️  Data unchanged, not stored (Depth={depth_mm}mm, Vel={velocity_mps}m/s, Flow={flow_lps}L/s)")
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
            # If we've exceeded max consecutive errors and exit-on-unhealthy is enabled, terminate to trigger container restart
            if not self.is_healthy and EXIT_ON_UNHEALTHY:
                logger.critical("Container exiting due to prolonged unhealthy state (triggering restart policy)")
                sys.exit(1)

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
        logger.info(f"💾 Storage mode: {'ALL readings (every check)' if STORE_ALL_READINGS else 'CHANGED values only'}")
        logger.info("=" * 60)
        logger.info("✅ Monitoring will detect changes and store only new data" if not STORE_ALL_READINGS else "✅ Monitoring will store EVERY reading (even if unchanged)")
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
    # Acquire singleton lock to prevent multiple instances
    instance_lock = SingletonProcessLock()
    if not instance_lock.acquire():
        try:
            # Try to read existing PID for nicer log
            existing_pid = None
            if LOCK_FILE_PATH.exists():
                try:
                    existing_pid = LOCK_FILE_PATH.read_text().strip()
                except Exception:
                    pass
            logger.error(
                f"Another monitor instance is already running"
                + (f" (PID {existing_pid})" if existing_pid else "")
                + f". Lock file: {LOCK_FILE_PATH}"
            )
        finally:
            return

    # Ensure lock is released on any exit path
    atexit.register(instance_lock.release)

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

    # Explicitly release the lock when leaving main
    try:
        instance_lock.release()
    except Exception:
        pass


if __name__ == "__main__":
    main()
