"""
Application settings helpers for EDS FlowSense.

Thin wrapper around ``AuthDatabase.get_setting`` / ``save_setting`` that
provides typed accessors for well-known keys.  All operations delegate to the
existing auth settings table — no new tables are created.
"""

from __future__ import annotations

from typing import Optional

_DEFAULT_POLLING_INTERVAL = "60"

# Allowed polling interval values (seconds)
POLLING_INTERVAL_OPTIONS = [30, 60, 120, 300]


def get_setting(auth_db, key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a setting from the auth database.

    Returns *default* if the key is not set or an error occurs.
    """
    try:
        value = auth_db.get_setting(key)
        return value if value is not None else default
    except Exception:
        return default


def set_setting(auth_db, key: str, value: str) -> None:
    """Save a setting to the auth database."""
    auth_db.save_setting(key, value)


def get_polling_interval(auth_db) -> int:
    """Return the configured polling interval in seconds (default 60)."""
    val = get_setting(auth_db, "polling_interval", _DEFAULT_POLLING_INTERVAL)
    try:
        interval = int(val)
        if interval in POLLING_INTERVAL_OPTIONS:
            return interval
        return 60
    except (TypeError, ValueError):
        return 60
