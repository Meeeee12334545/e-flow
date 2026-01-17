#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import asyncio

# Ensure project root is on path BEFORE importing project modules
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import DataScraper
from database import FlowDatabase
from config import DEVICES, MONITOR_URL

os.environ["SCRAPER_FORCE_REQUESTS"] = "1"

def main():
    print("Starting one-time fetch + store...")
    db = FlowDatabase()
    scraper = DataScraper(db)
    scraper.force_requests = True

    device_id = "FIT100"
    device_info = DEVICES.get(device_id, {})
    selectors = device_info.get("selectors") or {}
    url = device_info.get("url") or MONITOR_URL

    data = asyncio.run(scraper.fetch_monitor_data(url, selectors))
    print("Fetched:", bool(data), data and data.get("data"))

    if data and data.get("data"):
        payload = data["data"]
        stored = scraper.store_measurement(
            device_id=device_id,
            device_name=device_info.get("name", device_id),
            depth_mm=payload.get("depth_mm"),
            velocity_mps=payload.get("velocity_mps"),
            flow_lps=payload.get("flow_lps"),
            allow_storage=True,
        )
        print("Stored:", stored)
    else:
        print("No data to store.")

    from sqlite3 import connect
    con = connect(db.db_path)
    cur = con.cursor()
    cur.execute("select count(*) from measurements")
    count = cur.fetchone()[0]
    cur.execute("select device_id, timestamp, depth_mm, velocity_mps, flow_lps from measurements order by timestamp desc limit 1")
    row = cur.fetchone()
    con.close()
    print("Total measurements:", count)
    print("Latest row:", row)

if __name__ == "__main__":
    main()
