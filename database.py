import shutil
import sqlite3
import os
import logging
from datetime import datetime, timezone
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

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(Path(__file__).parent / "data" / "flow_data.db")))

_logger = logging.getLogger(__name__)


def _migrate_legacy_db(new_path: str) -> None:
    """One-time migration: copy the legacy root-level flow_data.db to the new
    ``data/flow_data.db`` location if the new path does not yet contain data.

    This handles the case where an existing deployment upgrading from an older
    version of the code (which stored the database in the project root) would
    otherwise start with an empty database and lose all previously collected
    measurements, devices, and user accounts.
    """
    new = Path(new_path)
    if new.exists() and new.stat().st_size > 0:
        return  # New path already has data — nothing to do

    # The legacy default was <project_root>/flow_data.db, one level above
    # the current default <project_root>/data/flow_data.db.
    old = new.parent.parent / "flow_data.db"
    if old.exists() and old.resolve() != new.resolve():
        _logger.info("Migrating legacy database from %s to %s", old, new)
        shutil.copy2(str(old), str(new))
        _logger.info("Legacy database migration complete.")


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
        else:
            # Ensure the data directory exists before SQLite tries to open the file
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            # Migrate from legacy root-level flow_data.db on first run with new path
            _migrate_legacy_db(self.db_path)
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
                    dashboard_url TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            # Migrate existing databases — add dashboard_url if absent
            cur.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS dashboard_url TEXT"
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
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON measurements (timestamp DESC);
                """
            )
            # Anomaly flags table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS anomaly_flags (
                    id SERIAL PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    measurement_timestamp TIMESTAMPTZ NOT NULL,
                    column_name TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT,
                    value DOUBLE PRECISION,
                    z_score DOUBLE PRECISION,
                    overridden BOOLEAN DEFAULT FALSE,
                    override_note TEXT,
                    overridden_by TEXT,
                    overridden_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_anomaly_device_ts
                ON anomaly_flags (device_id, measurement_timestamp DESC);
                """
            )
            # Scheduled reports table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_reports (
                    id SERIAL PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    period_start TIMESTAMPTZ NOT NULL,
                    period_end TIMESTAMPTZ NOT NULL,
                    generated_at TIMESTAMPTZ DEFAULT NOW(),
                    pdf_path TEXT,
                    anomaly_count INTEGER DEFAULT 0,
                    confidence_score DOUBLE PRECISION DEFAULT 100.0,
                    quality_label TEXT DEFAULT 'High',
                    summary TEXT
                )
                """
            )
            # Migrate devices table — add lat/lon and dashboard_url if absent
            cur.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"
            )
            cur.execute(
                "ALTER TABLE devices ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"
            )
            # Rainfall stations cache
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rainfall_stations (
                    station_id TEXT PRIMARY KEY,
                    station_name TEXT NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    state TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            # Rainfall observations cache
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rainfall_data (
                    id SERIAL PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    rainfall_mm DOUBLE PRECISION,
                    UNIQUE(station_id, timestamp)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rainfall_station_ts
                ON rainfall_data (station_id, timestamp DESC);
                """
            )
            # Device → rainfall station assignment
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS device_rainfall_stations (
                    device_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    assigned_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT fk_drs_device FOREIGN KEY (device_id) REFERENCES devices (device_id)
                )
                """
            )
            # Site intelligence: computed baseline snapshots (one per device)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS device_baselines (
                    device_id TEXT PRIMARY KEY,
                    computed_at TIMESTAMPTZ NOT NULL,
                    readings_used INTEGER NOT NULL,
                    days_covered DOUBLE PRECISION NOT NULL,
                    baseline_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            # Site intelligence: recommended alarm levels per device
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS alarm_recommendations (
                    id SERIAL PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    variable TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    level_name TEXT NOT NULL,
                    recommended_value DOUBLE PRECISION NOT NULL,
                    sensitivity TEXT NOT NULL,
                    basis TEXT,
                    estimated_fp_pct DOUBLE PRECISION,
                    status TEXT DEFAULT 'pending',
                    accepted_value DOUBLE PRECISION,
                    reviewed_by TEXT,
                    reviewed_at TIMESTAMPTZ,
                    UNIQUE(device_id, variable, direction, level_name, sensitivity)
                )
                """
            )
            cur.close()
            conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()

            # Enable WAL mode for better concurrency and reliability
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")

            # Create table for device information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    location TEXT,
                    dashboard_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Migrate existing databases — add dashboard_url if absent
            try:
                cursor.execute("ALTER TABLE devices ADD COLUMN dashboard_url TEXT")
            except Exception:
                pass  # Column already exists
            # Add lat/lon columns for map location feature
            try:
                cursor.execute("ALTER TABLE devices ADD COLUMN latitude REAL")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE devices ADD COLUMN longitude REAL")
            except Exception:
                pass

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

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON measurements (timestamp DESC)
                """
            )

            # Anomaly flags table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS anomaly_flags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    measurement_timestamp TIMESTAMP NOT NULL,
                    column_name TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT,
                    value REAL,
                    z_score REAL,
                    overridden INTEGER DEFAULT 0,
                    override_note TEXT,
                    overridden_by TEXT,
                    overridden_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_anomaly_device_ts
                ON anomaly_flags (device_id, measurement_timestamp DESC)
                """
            )

            # Scheduled reports table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pdf_path TEXT,
                    anomaly_count INTEGER DEFAULT 0,
                    confidence_score REAL DEFAULT 100.0,
                    quality_label TEXT DEFAULT 'High',
                    summary TEXT
                )
                """
            )

            # Rainfall stations cache
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rainfall_stations (
                    station_id TEXT PRIMARY KEY,
                    station_name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    state TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Rainfall observations cache
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rainfall_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    rainfall_mm REAL,
                    UNIQUE(station_id, timestamp)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rainfall_station_ts
                ON rainfall_data (station_id, timestamp DESC)
                """
            )

            # Device → rainfall station assignment
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS device_rainfall_stations (
                    device_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices (device_id)
                )
                """
            )

            # Site intelligence: computed baseline snapshots (one per device)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS device_baselines (
                    device_id TEXT PRIMARY KEY,
                    computed_at TIMESTAMP NOT NULL,
                    readings_used INTEGER NOT NULL,
                    days_covered REAL NOT NULL,
                    baseline_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )

            # Site intelligence: recommended alarm levels per device
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alarm_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    variable TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    level_name TEXT NOT NULL,
                    recommended_value REAL NOT NULL,
                    sensitivity TEXT NOT NULL,
                    basis TEXT,
                    estimated_fp_pct REAL,
                    status TEXT DEFAULT 'pending',
                    accepted_value REAL,
                    reviewed_by TEXT,
                    reviewed_at TIMESTAMP,
                    UNIQUE(device_id, variable, direction, level_name, sensitivity)
                )
                """
            )

            conn.commit()
            conn.close()

    def add_device(self, device_id: str, device_name: str, location: str = None,
                   dashboard_url: str = None):
        """Add or update a device in the database.

        Uses an upsert so that re-running ``init_devices`` refreshes the name,
        location and URL for config-defined devices without touching the
        ``created_at`` timestamp.  If ``dashboard_url`` is *None* the existing
        URL is preserved for devices already in the database.
        """
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO devices (device_id, device_name, location, dashboard_url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE SET
                        device_name   = EXCLUDED.device_name,
                        location      = EXCLUDED.location,
                        dashboard_url = COALESCE(EXCLUDED.dashboard_url, devices.dashboard_url)
                    """,
                    (device_id, device_name, location, dashboard_url),
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, device_name, location, dashboard_url)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        device_name   = excluded.device_name,
                        location      = excluded.location,
                        dashboard_url = COALESCE(excluded.dashboard_url, devices.dashboard_url)
                    """,
                    (device_id, device_name, location, dashboard_url),
                )
                conn.commit()
            finally:
                conn.close()

    def add_measurement(self, device_id: str, timestamp: datetime,
                        depth_mm: float = None, velocity_mps: float = None,
                        flow_lps: float = None) -> bool:
        """Add a measurement record. Returns True if a new row was inserted."""
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
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
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
                return cursor.rowcount > 0
            finally:
                conn.close()

    def bulk_add_measurements(self, records: List[Dict]) -> int:
        """Insert multiple measurement records in a single batch operation.

        Each record dict must contain ``device_id``, ``timestamp``, and
        optionally ``depth_mm``, ``velocity_mps``, ``flow_lps``.

        Returns the number of rows actually inserted (duplicates are skipped).
        Returns 0 immediately if *records* is empty.
        """
        if not records:
            return 0
        params = [
            (
                r['device_id'],
                r['timestamp'],
                r.get('depth_mm'),
                r.get('velocity_mps'),
                r.get('flow_lps'),
            )
            for r in records
        ]
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.executemany(
                    """
                    INSERT INTO measurements (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (device_id, timestamp) DO NOTHING
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO measurements
                    (device_id, timestamp, depth_mm, velocity_mps, flow_lps)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    params,
                )
                conn.commit()
                return cursor.rowcount
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
            conn = sqlite3.connect(self.db_path, timeout=30)
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
            conn = sqlite3.connect(self.db_path, timeout=30)
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
            conn = sqlite3.connect(self.db_path, timeout=30)
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
            conn = sqlite3.connect(self.db_path, timeout=30)
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
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM measurements")
            cursor.execute("DELETE FROM devices")
            conn.commit()
            conn.close()

    def delete_device(self, device_id: str) -> bool:
        """Delete a device and all its associated data.

        Removes rain gauge assignments, anomaly flags, scheduled reports, and
        measurements for the device before removing the device record itself.

        Returns True on success, False if an error occurred.
        """
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM device_rainfall_stations WHERE device_id = %s", (device_id,))
                cur.execute("DELETE FROM anomaly_flags WHERE device_id = %s", (device_id,))
                cur.execute("DELETE FROM scheduled_reports WHERE device_id = %s", (device_id,))
                cur.execute("DELETE FROM measurements WHERE device_id = %s", (device_id,))
                cur.execute("DELETE FROM devices WHERE device_id = %s", (device_id,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                conn.execute("DELETE FROM device_rainfall_stations WHERE device_id = ?", (device_id,))
                conn.execute("DELETE FROM anomaly_flags WHERE device_id = ?", (device_id,))
                conn.execute("DELETE FROM scheduled_reports WHERE device_id = ?", (device_id,))
                conn.execute("DELETE FROM measurements WHERE device_id = ?", (device_id,))
                conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()

    def flush_db(self):
        """Force a WAL checkpoint to ensure all data is written to the main database file.

        Call this after a batch of writes (e.g. at the end of a monitor cycle) to guarantee
        that data is visible to other processes and is not only in the WAL file.
        """
        if self.use_postgres:
            return  # Postgres handles durability natively
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.commit()
        finally:
            conn.close()

    # ── Anomaly flags ──────────────────────────────────────────────────────

    def save_anomaly_flags(self, device_id: str, flags: List[Dict]) -> int:
        """Persist anomaly flags for a device.  Replaces existing flags for the
        same device so that re-running detection on the same window is idempotent.

        Each *flags* dict must have:
          measurement_timestamp, column_name, anomaly_type, severity, description
        and optionally: value, z_score.

        Returns the number of rows inserted.
        """
        if not flags:
            return 0
        params = [
            (
                device_id,
                f["measurement_timestamp"],
                f["column_name"],
                f["anomaly_type"],
                f["severity"],
                f.get("description", ""),
                f.get("value"),
                f.get("z_score"),
            )
            for f in flags
        ]
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.executemany(
                    """
                    INSERT INTO anomaly_flags
                        (device_id, measurement_timestamp, column_name, anomaly_type,
                         severity, description, value, z_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO anomaly_flags
                        (device_id, measurement_timestamp, column_name, anomaly_type,
                         severity, description, value, z_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def get_anomaly_flags(
        self,
        device_id: str,
        include_overridden: bool = False,
        limit: int = 500,
    ) -> List[Dict]:
        """Retrieve anomaly flags for a device, newest first."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                if include_overridden:
                    cur.execute(
                        """
                        SELECT * FROM anomaly_flags
                        WHERE device_id = %s
                        ORDER BY measurement_timestamp DESC
                        LIMIT %s
                        """,
                        (device_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM anomaly_flags
                        WHERE device_id = %s AND overridden = FALSE
                        ORDER BY measurement_timestamp DESC
                        LIMIT %s
                        """,
                        (device_id, limit),
                    )
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if include_overridden:
                cursor.execute(
                    """
                    SELECT * FROM anomaly_flags
                    WHERE device_id = ?
                    ORDER BY measurement_timestamp DESC
                    LIMIT ?
                    """,
                    (device_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM anomaly_flags
                    WHERE device_id = ? AND overridden = 0
                    ORDER BY measurement_timestamp DESC
                    LIMIT ?
                    """,
                    (device_id, limit),
                )
            results = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return results

    def override_anomaly_flag(
        self,
        flag_id: int,
        override_note: str,
        overridden_by: str,
    ) -> bool:
        """Mark an anomaly flag as overridden by an admin."""
        now = datetime.now(timezone.utc)
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE anomaly_flags
                    SET overridden = TRUE, override_note = %s,
                        overridden_by = %s, overridden_at = %s
                    WHERE id = %s
                    """,
                    (override_note, overridden_by, now, flag_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE anomaly_flags
                    SET overridden = 1, override_note = ?,
                        overridden_by = ?, overridden_at = ?
                    WHERE id = ?
                    """,
                    (override_note, overridden_by, now.isoformat(), flag_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    # ── Scheduled / generated reports ─────────────────────────────────────

    def save_report_record(
        self,
        device_id: str,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
        pdf_path: Optional[str] = None,
        anomaly_count: int = 0,
        confidence_score: float = 100.0,
        quality_label: str = "High",
        summary: str = "",
    ) -> int:
        """Store metadata for a generated report. Returns the new record id."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO scheduled_reports
                        (device_id, report_type, period_start, period_end,
                         pdf_path, anomaly_count, confidence_score, quality_label, summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (device_id, report_type, period_start, period_end,
                     pdf_path, anomaly_count, confidence_score, quality_label, summary),
                )
                new_id = cur.fetchone()[0]
                conn.commit()
                return new_id
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO scheduled_reports
                        (device_id, report_type, period_start, period_end,
                         pdf_path, anomaly_count, confidence_score, quality_label, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, report_type,
                     period_start.isoformat() if isinstance(period_start, datetime) else period_start,
                     period_end.isoformat() if isinstance(period_end, datetime) else period_end,
                     pdf_path, anomaly_count, confidence_score, quality_label, summary),
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def get_report_records(self, device_id: str = None, limit: int = 50) -> List[Dict]:
        """Retrieve generated report records, newest first."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                if device_id:
                    cur.execute(
                        """
                        SELECT * FROM scheduled_reports
                        WHERE device_id = %s
                        ORDER BY generated_at DESC LIMIT %s
                        """,
                        (device_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM scheduled_reports ORDER BY generated_at DESC LIMIT %s",
                        (limit,),
                    )
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if device_id:
                cursor.execute(
                    """
                    SELECT * FROM scheduled_reports
                    WHERE device_id = ?
                    ORDER BY generated_at DESC LIMIT ?
                    """,
                    (device_id, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM scheduled_reports ORDER BY generated_at DESC LIMIT ?",
                    (limit,),
                )
            results = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return results

    # ── Rainfall / location methods ────────────────────────────────────────

    def update_device_location(self, device_id: str, latitude: float, longitude: float) -> bool:
        """Persist lat/lon coordinates for a device. Returns True on success."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE devices SET latitude = %s, longitude = %s WHERE device_id = %s",
                    (latitude, longitude, device_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE devices SET latitude = ?, longitude = ? WHERE device_id = ?",
                    (latitude, longitude, device_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def save_rainfall_stations(self, stations: List[Dict]) -> int:
        """Upsert a list of rainfall station records.

        Each dict must have: station_id, station_name, latitude, longitude.
        Optionally: state.
        Returns number of rows inserted/updated.
        """
        if not stations:
            return 0
        params = [
            (
                s["station_id"],
                s["station_name"],
                s["latitude"],
                s["longitude"],
                s.get("state"),
            )
            for s in stations
        ]
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.executemany(
                    """
                    INSERT INTO rainfall_stations (station_id, station_name, latitude, longitude, state, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (station_id) DO UPDATE SET
                        station_name = EXCLUDED.station_name,
                        latitude     = EXCLUDED.latitude,
                        longitude    = EXCLUDED.longitude,
                        state        = EXCLUDED.state,
                        updated_at   = NOW()
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO rainfall_stations (station_id, station_name, latitude, longitude, state)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(station_id) DO UPDATE SET
                        station_name = excluded.station_name,
                        latitude     = excluded.latitude,
                        longitude    = excluded.longitude,
                        state        = excluded.state,
                        updated_at   = CURRENT_TIMESTAMP
                    """,
                    params,
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def get_nearest_stations(self, latitude: float, longitude: float, limit: int = 10) -> List[Dict]:
        """Return up to *limit* cached rainfall stations ordered by distance from (lat, lon).

        Distance is computed in-Python via Haversine after fetching all cached stations.
        """
        import math

        def _haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute("SELECT * FROM rainfall_stations")
                rows = [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rainfall_stations")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()

        for row in rows:
            row["distance_km"] = _haversine(latitude, longitude, row["latitude"], row["longitude"])
        rows.sort(key=lambda r: r["distance_km"])
        return rows[:limit]

    def set_device_rainfall_station(self, device_id: str, station_id: str) -> bool:
        """Assign a rainfall station to a device (upsert). Returns True on success."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO device_rainfall_stations (device_id, station_id)
                    VALUES (%s, %s)
                    ON CONFLICT (device_id) DO UPDATE SET
                        station_id  = EXCLUDED.station_id,
                        assigned_at = NOW()
                    """,
                    (device_id, station_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO device_rainfall_stations (device_id, station_id)
                    VALUES (?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        station_id  = excluded.station_id,
                        assigned_at = CURRENT_TIMESTAMP
                    """,
                    (device_id, station_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def get_device_rainfall_station(self, device_id: str) -> Optional[Dict]:
        """Return the rainfall station assigned to *device_id*, or None."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    """
                    SELECT drs.*, rs.station_name, rs.latitude AS st_lat, rs.longitude AS st_lon, rs.state
                    FROM device_rainfall_stations drs
                    LEFT JOIN rainfall_stations rs ON drs.station_id = rs.station_id
                    WHERE drs.device_id = %s
                    """,
                    (device_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT drs.*, rs.station_name, rs.latitude AS st_lat, rs.longitude AS st_lon, rs.state
                    FROM device_rainfall_stations drs
                    LEFT JOIN rainfall_stations rs ON drs.station_id = rs.station_id
                    WHERE drs.device_id = ?
                    """,
                    (device_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            except sqlite3.OperationalError:
                return None
            finally:
                conn.close()

    def save_rainfall_data(self, station_id: str, records: List[Dict]) -> int:
        """Insert rainfall observations for a station. Skips duplicates.

        Each record dict must have: timestamp, rainfall_mm.
        Returns number of rows inserted.
        """
        if not records:
            return 0
        params = [(station_id, r["timestamp"], r.get("rainfall_mm")) for r in records]
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.executemany(
                    """
                    INSERT INTO rainfall_data (station_id, timestamp, rainfall_mm)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (station_id, timestamp) DO NOTHING
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO rainfall_data (station_id, timestamp, rainfall_mm)
                    VALUES (?, ?, ?)
                    """,
                    params,
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def get_rainfall_data(
        self,
        station_id: str,
        date_from: datetime = None,
        date_to: datetime = None,
        limit: int = 5000,
    ) -> List[Dict]:
        """Retrieve cached rainfall observations for *station_id*.

        Optionally filtered by *date_from* / *date_to* (inclusive).
        """
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                if date_from and date_to:
                    cur.execute(
                        """
                        SELECT * FROM rainfall_data
                        WHERE station_id = %s AND timestamp >= %s AND timestamp <= %s
                        ORDER BY timestamp ASC LIMIT %s
                        """,
                        (station_id, date_from, date_to, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM rainfall_data
                        WHERE station_id = %s
                        ORDER BY timestamp DESC LIMIT %s
                        """,
                        (station_id, limit),
                    )
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if date_from and date_to:
                cursor.execute(
                    """
                    SELECT * FROM rainfall_data
                    WHERE station_id = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC LIMIT ?
                    """,
                    (
                        station_id,
                        date_from.isoformat() if isinstance(date_from, datetime) else date_from,
                        date_to.isoformat() if isinstance(date_to, datetime) else date_to,
                        limit,
                    ),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM rainfall_data
                    WHERE station_id = ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (station_id, limit),
                )
            results = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return results


    # ── Site intelligence: baselines & alarm recommendations ─────────────────

    def save_device_baseline(
        self,
        device_id: str,
        computed_at: str,
        readings_used: int,
        days_covered: float,
        baseline_json: str,
        status: str,
    ) -> bool:
        """Upsert the computed baseline snapshot for a device. Returns True on success."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO device_baselines
                        (device_id, computed_at, readings_used, days_covered, baseline_json, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE SET
                        computed_at   = EXCLUDED.computed_at,
                        readings_used = EXCLUDED.readings_used,
                        days_covered  = EXCLUDED.days_covered,
                        baseline_json = EXCLUDED.baseline_json,
                        status        = EXCLUDED.status
                    """,
                    (device_id, computed_at, readings_used, days_covered, baseline_json, status),
                )
                conn.commit()
                return True
            except Exception:
                _logger.warning("save_device_baseline (postgres) failed", exc_info=True)
                conn.rollback()
                return False
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            try:
                conn.execute(
                    """
                    INSERT INTO device_baselines
                        (device_id, computed_at, readings_used, days_covered, baseline_json, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        computed_at   = excluded.computed_at,
                        readings_used = excluded.readings_used,
                        days_covered  = excluded.days_covered,
                        baseline_json = excluded.baseline_json,
                        status        = excluded.status
                    """,
                    (device_id, computed_at, readings_used, days_covered, baseline_json, status),
                )
                conn.commit()
                return True
            except Exception:
                _logger.warning("save_device_baseline (sqlite) failed", exc_info=True)
                conn.rollback()
                return False
            finally:
                conn.close()

    def get_device_baseline(self, device_id: str) -> Optional[Dict]:
        """Return the stored baseline row for *device_id*, or None if not found."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    "SELECT * FROM device_baselines WHERE device_id = %s",
                    (device_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT * FROM device_baselines WHERE device_id = ?",
                    (device_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            except sqlite3.OperationalError:
                return None
            finally:
                conn.close()

    def save_alarm_recommendations(
        self,
        device_id: str,
        recommendations: List[Dict],
    ) -> int:
        """Upsert alarm recommendations for a device.

        Each dict must have: variable, direction, level_name, recommended_value,
        sensitivity.  Optionally: basis, estimated_fp_pct.

        Existing rows for the same (device_id, variable, direction, level_name,
        sensitivity) are reset to ``status='pending'`` with the new values so
        that a fresh recompute clears stale acceptances.

        Returns the number of rows upserted.
        """
        if not recommendations:
            return 0
        params = [
            (
                device_id,
                r["variable"],
                r["direction"],
                r["level_name"],
                r["recommended_value"],
                r["sensitivity"],
                r.get("basis", ""),
                r.get("estimated_fp_pct"),
            )
            for r in recommendations
        ]
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.executemany(
                    """
                    INSERT INTO alarm_recommendations
                        (device_id, variable, direction, level_name, recommended_value,
                         sensitivity, basis, estimated_fp_pct, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    ON CONFLICT (device_id, variable, direction, level_name, sensitivity)
                    DO UPDATE SET
                        recommended_value = EXCLUDED.recommended_value,
                        basis             = EXCLUDED.basis,
                        estimated_fp_pct  = EXCLUDED.estimated_fp_pct,
                        status            = 'pending',
                        accepted_value    = NULL,
                        reviewed_by       = NULL,
                        reviewed_at       = NULL
                    """,
                    params,
                )
                conn.commit()
                return cur.rowcount
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO alarm_recommendations
                        (device_id, variable, direction, level_name, recommended_value,
                         sensitivity, basis, estimated_fp_pct, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    ON CONFLICT(device_id, variable, direction, level_name, sensitivity)
                    DO UPDATE SET
                        recommended_value = excluded.recommended_value,
                        basis             = excluded.basis,
                        estimated_fp_pct  = excluded.estimated_fp_pct,
                        status            = 'pending',
                        accepted_value    = NULL,
                        reviewed_by       = NULL,
                        reviewed_at       = NULL
                    """,
                    params,
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def get_alarm_recommendations(
        self,
        device_id: str,
        sensitivity: Optional[str] = None,
    ) -> List[Dict]:
        """Return alarm recommendations for *device_id*, optionally filtered by sensitivity."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                if sensitivity:
                    cur.execute(
                        """
                        SELECT * FROM alarm_recommendations
                        WHERE device_id = %s AND sensitivity = %s
                        ORDER BY variable, direction, level_name
                        """,
                        (device_id, sensitivity),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM alarm_recommendations
                        WHERE device_id = %s
                        ORDER BY variable, sensitivity, direction, level_name
                        """,
                        (device_id,),
                    )
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                if sensitivity:
                    cursor.execute(
                        """
                        SELECT * FROM alarm_recommendations
                        WHERE device_id = ? AND sensitivity = ?
                        ORDER BY variable, direction, level_name
                        """,
                        (device_id, sensitivity),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM alarm_recommendations
                        WHERE device_id = ?
                        ORDER BY variable, sensitivity, direction, level_name
                        """,
                        (device_id,),
                    )
                return [dict(r) for r in cursor.fetchall()]
            except sqlite3.OperationalError:
                return []
            finally:
                conn.close()

    def update_alarm_recommendation_status(
        self,
        rec_id: int,
        status: str,
        reviewed_by: str,
        accepted_value: Optional[float] = None,
    ) -> bool:
        """Update the status of a single alarm recommendation row.

        *status* should be ``'accepted'`` or ``'dismissed'``.
        Returns True if a row was updated.
        """
        now = datetime.now(timezone.utc)
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE alarm_recommendations
                    SET status = %s, reviewed_by = %s, reviewed_at = %s, accepted_value = %s
                    WHERE id = %s
                    """,
                    (status, reviewed_by, now, accepted_value, rec_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path, timeout=30)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE alarm_recommendations
                    SET status = ?, reviewed_by = ?, reviewed_at = ?, accepted_value = ?
                    WHERE id = ?
                    """,
                    (status, reviewed_by, now.isoformat(), accepted_value, rec_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()


if __name__ == "__main__":
    db = FlowDatabase()
    print(f"Database initialized at {db.db_path}")
