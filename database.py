import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

DATABASE_PATH = Path(__file__).parent / "flow_data.db"


class FlowDatabase:
    """SQLite database for storing depth, velocity, and flow data."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DATABASE_PATH)
        self.init_db()

    def init_db(self):
        """Initialize the database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create table for device information
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                device_name TEXT NOT NULL,
                location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create table for measurements
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                depth_mm REAL,
                velocity_mps REAL,
                flow_lps REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices (device_id),
                UNIQUE(device_id, timestamp)
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_device_timestamp 
            ON measurements (device_id, timestamp DESC)
        """)

        conn.commit()
        conn.close()

    def add_device(self, device_id: str, device_name: str, location: str = None):
        """Add a new device to the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO devices (device_id, device_name, location)
                VALUES (?, ?, ?)
            """, (device_id, device_name, location))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()

    def add_measurement(self, device_id: str, timestamp: datetime, 
                       depth_mm: float = None, velocity_mps: float = None, 
                       flow_lps: float = None):
        """Add a measurement record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO measurements 
                (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, timestamp, depth_mm, velocity_mps, flow_lps))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()

    def get_measurements(self, device_id: str = None, limit: int = 1000) -> List[Dict]:
        """Retrieve measurements from the database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if device_id:
            cursor.execute("""
                SELECT m.*, d.device_name
                FROM measurements m
                JOIN devices d ON m.device_id = d.device_id
                WHERE m.device_id = ?
                ORDER BY m.timestamp DESC
                LIMIT ?
            """, (device_id, limit))
        else:
            cursor.execute("""
                SELECT m.*, d.device_name
                FROM measurements m
                JOIN devices d ON m.device_id = d.device_id
                ORDER BY m.timestamp DESC
                LIMIT ?
            """, (limit,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_devices(self) -> List[Dict]:
        """Get all registered devices."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY device_name")
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_device_count(self) -> int:
        """Get total number of devices."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_measurement_count(self) -> int:
        """Get total number of measurements."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM measurements")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def delete_all_data(self):
        """Delete all data from the database (for fresh start)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM measurements")
        cursor.execute("DELETE FROM devices")
        conn.commit()
        conn.close()


if __name__ == "__main__":
    db = FlowDatabase()
    print(f"Database initialized at {db.db_path}")
