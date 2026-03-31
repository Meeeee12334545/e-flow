#!/usr/bin/env python
"""
Data ingestion script for scheduled/automated data collection.
Can be run manually or scheduled via cron/GitHub Actions.
"""

import asyncio
import sys
import logging
from datetime import datetime
import pytz

from scraper import DataScraper
from database import FlowDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_TZ = "Australia/Brisbane"


async def ingest_data():
    """Main data ingestion function."""
    logger.info("=" * 50)
    logger.info("Starting Flow Data Ingestion")
    logger.info("=" * 50)
    
    db = FlowDatabase()
    scraper = DataScraper(db)
    
    try:
        logger.info("Fetching data from monitor...")
        data = await scraper.fetch_monitor_data()
        
        if data:
            logger.info(f"Data retrieved successfully: {data}")
            
            # Extract values from the monitor data payload
            payload = data.get("data", {})
            device_id = "FIT100"
            device_name = "FIT100 Main Inflow Lismore STP"
            depth_mm = payload.get("depth_mm") or payload.get("depth")
            velocity_mps = payload.get("velocity_mps") or payload.get("velocity")
            flow_lps = payload.get("flow_lps") or payload.get("flow")

            logger.info(f"Parsed values from monitor payload: depth_mm={depth_mm}, velocity_mps={velocity_mps}, flow_lps={flow_lps}")

            # Store in database (allow_storage required for monitor mode)
            stored = scraper.store_measurement(
                device_id=device_id,
                device_name=device_name,
                depth_mm=depth_mm,
                velocity_mps=velocity_mps,
                flow_lps=flow_lps,
                allow_storage=True
            )

            if stored:
                logger.info("✅ Data ingestion stored a new record")
            else:
                logger.info("ℹ️ Data ingestion did not store (duplicate/no-change or no-values)")
            
            logger.info("✅ Data ingestion completed successfully")
            logger.info(f"Total devices: {db.get_device_count()}")
            logger.info(f"Total measurements: {db.get_measurement_count()}")
            return 0
        else:
            logger.warning("❌ Failed to retrieve data from monitor")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Error during data ingestion: {e}", exc_info=True)
        return 1
    finally:
        logger.info("=" * 50)
        logger.info("Data ingestion completed")
        logger.info("=" * 50)


if __name__ == "__main__":
    exit_code = asyncio.run(ingest_data())
    sys.exit(exit_code)
