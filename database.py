import sqlite3
import os
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


if __name__ == "__main__":
    db = FlowDatabase()
    print(f"Database initialized at {db.db_path}")
