#!/usr/bin/env python
"""
Utility to clean duplicate measurements from the database.

Duplicate prevention relies on change detection in the scraper:
1. Each measurement is hashed (CRC32) based on its values
2. Only measurements with NEW hashes are stored
3. Duplicates (same hash) are skipped

This script helps identify and remove any duplicates that might have been 
stored due to multiple monitor instances or change detection failures.

Usage:
    python clean_duplicates.py          # Show duplicates
    python clean_duplicates.py --fix    # Remove duplicates
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DATABASE_PATH = Path(__file__).parent / "flow_data.db"


def find_duplicates():
    """Find groups of measurements with identical values."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id, device_id, timestamp, 
            depth_mm, velocity_mps, flow_lps,
            ROUND(depth_mm, 1) as d,
            ROUND(velocity_mps, 3) as v,
            ROUND(flow_lps, 1) as f
        FROM measurements
        ORDER BY device_id, timestamp
    """)
    
    rows = cursor.fetchall()
    duplicates_by_device = defaultdict(list)
    
    # Group by device
    for device_id in set(r['device_id'] for r in rows):
        device_rows = [r for r in rows if r['device_id'] == device_id]
        
        # Find consecutive duplicates
        for i in range(len(device_rows) - 1):
            curr = device_rows[i]
            next_row = device_rows[i + 1]
            
            # Check if values are identical (within rounding)
            same_depth = curr['d'] == next_row['d']
            same_velocity = curr['v'] == next_row['v']
            same_flow = curr['f'] == next_row['f']
            
            if same_depth and same_velocity and same_flow:
                duplicates_by_device[device_id].append({
                    'id': next_row['id'],
                    'timestamp': next_row['timestamp'],
                    'values': f"{next_row['depth_mm']:.1f}mm, {next_row['velocity_mps']:.3f}m/s, {next_row['flow_lps']:.1f}L/s"
                })
    
    conn.close()
    return duplicates_by_device


def remove_duplicates():
    """Remove duplicate measurements, keeping only the first of each group."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id FROM measurements m1
        WHERE EXISTS (
            SELECT 1 FROM measurements m2
            WHERE m1.device_id = m2.device_id
            AND m1.timestamp > m2.timestamp
            AND ROUND(m1.depth_mm, 1) = ROUND(m2.depth_mm, 1)
            AND ROUND(m1.velocity_mps, 3) = ROUND(m2.velocity_mps, 3)
            AND ROUND(m1.flow_lps, 1) = ROUND(m2.flow_lps, 1)
            AND m1.created_at > m2.created_at
        )
    """)
    
    duplicate_ids = [row[0] for row in cursor.fetchall()]
    
    if duplicate_ids:
        cursor.execute(f"DELETE FROM measurements WHERE id IN ({','.join('?' * len(duplicate_ids))})", duplicate_ids)
        conn.commit()
        print(f"✅ Removed {len(duplicate_ids)} duplicate records")
    else:
        print("✅ No duplicates found")
    
    conn.close()


if __name__ == "__main__":
    import sys
    
    if not DATABASE_PATH.exists():
        print(f"❌ Database not found at {DATABASE_PATH}")
        exit(1)
    
    print(f"📊 Analyzing database at {DATABASE_PATH}\n")
    
    duplicates = find_duplicates()
    
    if not duplicates:
        print("✅ No duplicates detected!")
        exit(0)
    
    total_dupes = sum(len(v) for v in duplicates.values())
    print(f"⚠️  Found {total_dupes} duplicate measurement(s):\n")
    
    for device_id, dupe_list in duplicates.items():
        print(f"  Device: {device_id}")
        for dup in dupe_list:
            print(f"    - ID {dup['id']}: {dup['timestamp']} ({dup['values']})")
        print()
    
    if "--fix" in sys.argv:
        print("🔧 Removing duplicates...\n")
        remove_duplicates()
    else:
        print("💡 To remove duplicates, run: python clean_duplicates.py --fix")
