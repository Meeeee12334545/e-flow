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
            
            # Extract values from the data
            # Note: The actual extraction depends on how the website structures its data
            # This is a placeholder - adjust based on actual data structure
            
            device_id = "FIT100"
            device_name = "FIT100 Main Inflow Lismore STP"
            
            # Store in database
            scraper.store_measurement(
                device_id=device_id,
                device_name=device_name,
                depth_mm=0.0,
                velocity_mps=0.0,
                flow_lps=0.0,
                allow_storage=True
            )
            
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
