#!/usr/bin/env python
"""
Quick test script to verify data extraction from the USRIOT dashboard.
Run this to test if the scraper can extract data properly.
"""

import asyncio
import sys
from scraper import DataScraper
from database import FlowDatabase
from config import MONITOR_URL, DEVICES

async def test_extraction():
    """Test data extraction from the monitor website."""
    print("=" * 60)
    print("🧪 Testing Data Extraction")
    print("=" * 60)
    print(f"📍 Target URL: {MONITOR_URL[:100]}...")
    print()
    
    db = FlowDatabase()
    scraper = DataScraper(db)
    
    print("⏳ Fetching data from website...")
    
    # Get device config with CSS selectors
    device_id = "FIT100"
    device_info = DEVICES.get(device_id, {})
    device_selectors = device_info.get("selectors", None)
    
    data = await scraper.fetch_monitor_data(MONITOR_URL, device_selectors)
    
    if not data:
        print("❌ Failed to fetch data!")
        return False
    
    print("✅ Data fetched successfully!")
    print()
    print("📊 Extracted Data:")
    print("-" * 60)
    
    page_data = data.get("data", {})
    
    if not page_data:
        print("⚠️  No data found in page")
        print(f"   Page title: {data.get('title', 'N/A')}")
        return False
    
    # Show what was extracted
    if "depth" in page_data:
        print(f"✅ Depth: {page_data['depth']} mm")
    else:
        print("⚠️  Depth: Not found")
    
    if "velocity" in page_data:
        print(f"✅ Velocity: {page_data['velocity']} m/s")
    else:
        print("⚠️  Velocity: Not found")
    
    if "flow" in page_data:
        print(f"✅ Flow: {page_data['flow']} L/s")
    else:
        print("⚠️  Flow: Not found")
    
    print()
    print(f"Page Title: {data.get('title', 'N/A')}")
    print()
    
    # Test storing the data
    print("-" * 60)
    print("🔄 Testing data storage...")
    
    device_id = "FIT100"
    device_name = DEVICES[device_id]["name"]
    
    # Extract values properly
    depth_mm = None
    velocity_mps = None
    flow_lps = None
    
    if isinstance(page_data, dict):
        # Check for both old and new key formats
        depth_mm = page_data.get('depth_mm') or page_data.get('depth')
        velocity_mps = page_data.get('velocity_mps') or page_data.get('velocity')
        flow_lps = page_data.get('flow_lps') or page_data.get('flow')
    
    stored = scraper.store_measurement(
        device_id=device_id,
        device_name=device_name,
        depth_mm=depth_mm,
        velocity_mps=velocity_mps,
        flow_lps=flow_lps
    )
    
    if stored:
        print("✅ Data stored successfully!")
    else:
        print("ℹ️  No changes detected or data already in database")
    
    print()
    print("=" * 60)
    print("✅ Test completed!")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_extraction())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
