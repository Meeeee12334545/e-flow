#!/usr/bin/env python3
"""
Simple health check for e-flow monitor.

Exit codes:
 0 = healthy (recent data present)
 1 = unhealthy (no recent data / DB missing / error)

Criteria:
 - DB exists and is readable
 - Latest measurement timestamp within HEALTH_MAX_AGE seconds (default: 900)
"""
import os
import sys
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", "flow_data.db")
MAX_AGE_SECS = int(os.getenv("HEALTH_MAX_AGE", "900"))

def main():
    status = {
        "db_path": DB_PATH,
        "healthy": False,
        "reason": None,
        "latest_timestamp": None,
        "now": datetime.now(timezone.utc).isoformat(),
        "max_age_secs": MAX_AGE_SECS,
    }

    try:
        if not os.path.exists(DB_PATH):
            status["reason"] = "database_missing"
            print(json.dumps(status))
            sys.exit(1)

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT MAX(timestamp) FROM measurements")
        row = cur.fetchone()
        conn.close()

        if not row or not row[0]:
            status["reason"] = "no_measurements"
            print(json.dumps(status))
            sys.exit(1)

        latest_str = row[0]
        status["latest_timestamp"] = latest_str

        # Try to parse as ISO or SQLite default format
        try:
            # SQLite may store naive localtime; treat as UTC conservatively
            latest = datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
        except Exception:
            # Fallback: try generic parsing
            latest = datetime.strptime(latest_str, "%Y-%m-%d %H:%M:%S")
            latest = latest.replace(tzinfo=timezone.utc)

        age = (datetime.now(timezone.utc) - latest).total_seconds()
        if age <= MAX_AGE_SECS:
            status["healthy"] = True
            status["reason"] = "ok"
            print(json.dumps(status))
            sys.exit(0)
        else:
            status["reason"] = f"stale:{int(age)}s"
            print(json.dumps(status))
            sys.exit(1)

    except Exception as e:
        status["reason"] = f"error:{e}"
        print(json.dumps(status))
        sys.exit(1)

if __name__ == "__main__":
    main()
