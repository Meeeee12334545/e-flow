import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# Optional Postgres support
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_PG_AVAILABLE = False
try:
    if DATABASE_URL:
        import psycopg2  # type: ignore
        import psycopg2.extras  # type: ignore
        _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

DATABASE_PATH = Path(__file__).parent / "flow_data.db"


class FlowDatabase:
    """Database for storing depth, velocity, and flow data.

    Supports SQLite by default. If `DATABASE_URL` is provided and psycopg2 is
    available, uses Postgres instead so multiple services can share one DB.
    """

    def __init__(self, db_path: str = None):
        self.use_postgres = bool(DATABASE_URL and _PG_AVAILABLE)
        self.db_path = db_path or str(DATABASE_PATH)
        if self.use_postgres:
            self.pg_dsn = DATABASE_URL
        self.init_db()

    def init_db(self):
        """Initialize the database with required tables."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            conn.autocommit = True
            cur = conn.cursor()
            # Enable extension for UUIDs/timestamps if needed; keep minimal here
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    location TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    id SERIAL PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    depth_mm DOUBLE PRECISION,
                    velocity_mps DOUBLE PRECISION,
                    flow_lps DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT fk_device FOREIGN KEY (device_id) REFERENCES devices (device_id)
                )
                """
            )
            # Ensure unique constraint (device_id, timestamp)
            cur.execute(
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uniq_device_time'
                    ) THEN
                        ALTER TABLE measurements ADD CONSTRAINT uniq_device_time UNIQUE (device_id, timestamp);
                    END IF;
                END $$;
                """
            )
            # Index for faster queries
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_timestamp 
                ON measurements (device_id, timestamp DESC);
                """
            )
            cur.close()
            conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create table for device information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create table for measurements
            cursor.execute(
                """
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
                """
            )

            # Create index for faster queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_device_timestamp 
                ON measurements (device_id, timestamp DESC)
                """
            )

            conn.commit()
            conn.close()

    def add_device(self, device_id: str, device_name: str, location: str = None):
        """Add a new device to the database."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO devices (device_id, device_name, location)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (device_id) DO NOTHING
                    """,
                    (device_id, device_name, location),
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO devices (device_id, device_name, location)
                    VALUES (?, ?, ?)
                    """,
                    (device_id, device_name, location),
                )
                conn.commit()
            finally:
                conn.close()

    def add_measurement(self, device_id: str, timestamp: datetime,
                        depth_mm: float = None, velocity_mps: float = None,
                        flow_lps: float = None):
        """Add a measurement record."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO measurements (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (device_id, timestamp) DO NOTHING
                    """,
                    (device_id, timestamp, depth_mm, velocity_mps, flow_lps),
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO measurements 
                    (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (device_id, timestamp, depth_mm, velocity_mps, flow_lps),
                )
                conn.commit()
            finally:
                conn.close()

    def get_measurements(self, device_id: str = None, limit: int = 1000) -> List[Dict]:
        """Retrieve measurements from the database."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                if device_id:
                    cur.execute(
                        """
                        SELECT m.*, d.device_name
                        FROM measurements m
                        JOIN devices d ON m.device_id = d.device_id
                        WHERE m.device_id = %s
                        ORDER BY m.timestamp DESC
                        LIMIT %s
                        """,
                        (device_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT m.*, d.device_name
                        FROM measurements m
                        JOIN devices d ON m.device_id = d.device_id
                        ORDER BY m.timestamp DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if device_id:
                cursor.execute(
                    """
                    SELECT m.*, d.device_name
                    FROM measurements m
                    JOIN devices d ON m.device_id = d.device_id
                    WHERE m.device_id = ?
                    ORDER BY m.timestamp DESC
                    LIMIT ?
                    """,
                    (device_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT m.*, d.device_name
                    FROM measurements m
                    JOIN devices d ON m.device_id = d.device_id
                    ORDER BY m.timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results

    def get_devices(self) -> List[Dict]:
        """Get all registered devices."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute("SELECT * FROM devices ORDER BY device_name")
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM devices ORDER BY device_name")
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results

    def get_device_count(self) -> int:
        """Get total number of devices."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM devices")
                count = cur.fetchone()[0]
                return int(count)
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM devices")
            count = cursor.fetchone()[0]
            conn.close()
            return count

    def get_measurement_count(self) -> int:
        """Get total number of measurements."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute("SELECT COUNT(*) FROM measurements")
                count = cur.fetchone()[0]
                return int(count)
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM measurements")
            count = cursor.fetchone()[0]
            conn.close()
            return count

    def delete_all_data(self):
        """Delete all data from the database (for fresh start)."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM measurements")
                cur.execute("DELETE FROM devices")
                conn.commit()
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM measurements")
            cursor.execute("DELETE FROM devices")
            conn.commit()
            conn.close()


if __name__ == "__main__":
    db = FlowDatabase()
    print(f"Database initialized at {db.db_path}")
