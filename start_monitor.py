#!/usr/bin/env python3
"""
Simple standalone monitor that runs every 60 seconds.
ONLY run this script ONCE - never run multiple instances.

Usage:
    python start_monitor.py

This will:
- Fetch data every 60 seconds
- Only store when values change (using persistent state)
- Log all activity to console
- Run until you stop it with Ctrl+C

IMPORTANT: Do NOT run this while the Streamlit app is running with MONITOR_ENABLED=True
"""

import asyncio
import time
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import DataScraper
from database import FlowDatabase
from config import DEVICES, MONITOR_URL
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global shutdown_flag
    print("\n\n🛑 Shutdown signal received. Stopping monitor...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Main monitor loop."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Standalone Monitor")
    logger.info("=" * 60)
    logger.info("Interval: 60 seconds")
    logger.info("Change detection: ENABLED (persistent state)")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Create persistent scraper and database instances
    db = FlowDatabase()
    scraper = DataScraper(db)
    
    check_count = 0
    
    while not shutdown_flag:
        try:
            check_count += 1
            logger.info(f"\n[Check #{check_count}] Fetching data at {datetime.now().strftime('%H:%M:%S')}...")
            
            # Get device info
            device_id = "FIT100"
            device_info = DEVICES.get(device_id, {})
            device_name = device_info.get("name", "FIT100 Main Inflow Lismore STP")
            device_selectors = device_info.get("selectors")
            url = device_info.get("url") or MONITOR_URL
            
            # Fetch data
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                data = loop.run_until_complete(scraper.fetch_monitor_data(url, device_selectors))
            finally:
                loop.close()
            
            if data and data.get("data"):
                payload = data.get("data", {})
                depth_mm = payload.get("depth_mm")
                velocity_mps = payload.get("velocity_mps")
                flow_lps = payload.get("flow_lps")
                
                logger.info(f"  Fetched: D={depth_mm}mm, V={velocity_mps}m/s, F={flow_lps}L/s")
                
                if depth_mm is not None or velocity_mps is not None or flow_lps is not None:
                    stored = scraper.store_measurement(
                        device_id=device_id,
                        device_name=device_name,
                        depth_mm=depth_mm,
                        velocity_mps=velocity_mps,
                        flow_lps=flow_lps,
                        allow_storage=True  # Explicitly allow storage from standalone monitor
                    )
                    
                    if stored:
                        logger.info(f"  ✅ STORED (values changed)")
                    else:
                        logger.info(f"  ⊗ SKIPPED (no change)")
                else:
                    logger.warning("  ⚠️  No valid data extracted")
            else:
                logger.warning("  ⚠️  Failed to fetch data from device")
            
            # Wait 60 seconds before next check
            if not shutdown_flag:
                logger.info(f"  Waiting 60 seconds until next check...")
                for _ in range(60):
                    if shutdown_flag:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"  ❌ Error: {e}", exc_info=True)
            if not shutdown_flag:
                logger.info("  Waiting 60 seconds before retry...")
                time.sleep(60)
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Monitor stopped gracefully")
    logger.info(f"Total checks performed: {check_count}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
