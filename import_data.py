#!/usr/bin/env python
"""
Alternative data input method for e-flow
Since the website uses heavy JavaScript that's difficult to scrape in this environment,
this provides a way to manually input or import data.

Usage:
  - Put data in CSV format or JSON
  - Run this script to import into the database
  - Format: timestamp, depth_mm, velocity_mps, flow_lps
"""

import sys
import csv
import json
from datetime import datetime
from pathlib import Path

from database import FlowDatabase
from config import DEVICES

def import_csv(csv_file):
    """Import data from CSV file."""
    db = FlowDatabase()
    device_id = "FIT100"
    device_info = DEVICES.get(device_id)
    
    if not device_info:
        print(f"❌ Device {device_id} not found in config")
        return False
    
    db.add_device(device_id, device_info["name"], device_info.get("location", ""))
    
    count = 0
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    timestamp = datetime.fromisoformat(row['timestamp'])
                    depth_mm = float(row['depth_mm']) if row.get('depth_mm') else None
                    velocity_mps = float(row['velocity_mps']) if row.get('velocity_mps') else None
                    flow_lps = float(row['flow_lps']) if row.get('flow_lps') else None
                    
                    db.add_measurement(
                        device_id=device_id,
                        timestamp=timestamp,
                        depth_mm=depth_mm,
                        velocity_mps=velocity_mps,
                        flow_lps=flow_lps
                    )
                    count += 1
                except (ValueError, KeyError) as e:
                    print(f"⚠️  Skipping row: {e}")
                    continue
        
        print(f"✅ Imported {count} records from {csv_file}")
        return True
        
    except FileNotFoundError:
        print(f"❌ File not found: {csv_file}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def import_json(json_file):
    """Import data from JSON file."""
    db = FlowDatabase()
    device_id = "FIT100"
    device_info = DEVICES.get(device_id)
    
    if not device_info:
        print(f"❌ Device {device_id} not found in config")
        return False
    
    db.add_device(device_id, device_info["name"], device_info.get("location", ""))
    
    count = 0
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Handle both list and dict formats
        records = data if isinstance(data, list) else data.get('measurements', [])
        
        for record in records:
            try:
                timestamp = datetime.fromisoformat(record['timestamp'])
                depth_mm = float(record.get('depth_mm')) if record.get('depth_mm') else None
                velocity_mps = float(record.get('velocity_mps')) if record.get('velocity_mps') else None
                flow_lps = float(record.get('flow_lps')) if record.get('flow_lps') else None
                
                db.add_measurement(
                    device_id=device_id,
                    timestamp=timestamp,
                    depth_mm=depth_mm,
                    velocity_mps=velocity_mps,
                    flow_lps=flow_lps
                )
                count += 1
            except (ValueError, KeyError, TypeError) as e:
                print(f"⚠️  Skipping record: {e}")
                continue
        
        print(f"✅ Imported {count} records from {json_file}")
        return True
        
    except FileNotFoundError:
        print(f"❌ File not found: {json_file}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def add_test_data():
    """Add some test data to verify the system works."""
    db = FlowDatabase()
    device_id = "FIT100"
    device_info = DEVICES.get(device_id)
    
    if not device_info:
        print(f"❌ Device {device_id} not found in config")
        return False
    
    db.add_device(device_id, device_info["name"], device_info.get("location", ""))
    
    # Add test measurements
    test_data = [
        {"depth": 150.5, "velocity": 0.45, "flow": 25.3},
        {"depth": 152.3, "velocity": 0.47, "flow": 26.1},
        {"depth": 151.8, "velocity": 0.46, "flow": 25.7},
        {"depth": 153.2, "velocity": 0.48, "flow": 26.5},
        {"depth": 151.5, "velocity": 0.45, "flow": 25.4},
    ]
    
    count = 0
    for data in test_data:
        db.add_measurement(
            device_id=device_id,
            timestamp=datetime.now(),
            depth_mm=data["depth"],
            velocity_mps=data["velocity"],
            flow_lps=data["flow"]
        )
        count += 1
    
    print(f"✅ Added {count} test measurements")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python import_data.py test              # Add test data")
        print("  python import_data.py csv <file>        # Import from CSV")
        print("  python import_data.py json <file>       # Import from JSON")
        print("\nCSV Format (header required):")
        print("  timestamp,depth_mm,velocity_mps,flow_lps")
        print("  2026-01-16T10:00:00,150.5,0.45,25.3")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "test":
        add_test_data()
    elif command == "csv" and len(sys.argv) > 2:
        import_csv(sys.argv[2])
    elif command == "json" and len(sys.argv) > 2:
        import_json(sys.argv[2])
    else:
        print("❌ Invalid arguments")
        sys.exit(1)
