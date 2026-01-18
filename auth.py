"""
User Authentication & Access Control Module

Provides role-based access control (RBAC) with user management,
password hashing, and device-to-user assignment.
"""

import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import os

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


class AuthDatabase:
    """User authentication and authorization database."""

    def __init__(self, db_path: str = None):
        self.use_postgres = bool(DATABASE_URL and _PG_AVAILABLE)
        self.db_path = db_path or str(DATABASE_PATH)
        if self.use_postgres:
            self.pg_dsn = DATABASE_URL
        self.init_auth_tables()

    def init_auth_tables(self):
        """Initialize auth-related tables."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            conn.autocommit = True
            cur = conn.cursor()
            
            # Users table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_login TIMESTAMPTZ
                )
                """
            )
            
            # User device assignments
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_devices (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    assigned_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE,
                    UNIQUE (user_id, device_id)
                )
                """
            )
            
            # Session tokens
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                )
                """
            )
            
            # Create indices for faster queries
            cur.execute("CREATE INDEX IF NOT EXISTS idx_username ON users (username)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_devices ON user_devices (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)")
            
            cur.close()
            conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
                """
            )
            
            # User device assignments
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (device_id) REFERENCES devices (device_id),
                    UNIQUE (user_id, device_id)
                )
                """
            )
            
            # Session tokens
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """
            )
            
            # Create indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users (username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_devices ON user_devices (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)")
            
            conn.commit()
            conn.close()

    @staticmethod
    def hash_password(password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password using PBKDF2-SHA256."""
        if salt is None:
            salt = secrets.token_hex(32)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        
        return f"{salt}${password_hash}", salt

    @staticmethod
    def verify_password(password: str, stored_hash: str) -> bool:
        """Verify password against stored hash."""
        try:
            salt = stored_hash.split('$')[0]
            new_hash, _ = AuthDatabase.hash_password(password, salt)
            return hmac.compare_digest(new_hash, stored_hash)
        except Exception:
            return False

    def create_user(self, username: str, email: str, password: str, role: str = "user") -> bool:
        """Create a new user. Returns True if successful."""
        if role not in ["admin", "user"]:
            raise ValueError("Role must be 'admin' or 'user'")
        
        password_hash, _ = self.hash_password(password)
        
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (username, email, password_hash, role),
                )
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                return False
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, email, password_hash, role),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user info if successful."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    "SELECT user_id, username, email, role, active FROM users WHERE username = %s",
                    (username,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                
                user_info = dict(row)
                
                # Check password
                cur.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
                result = cur.fetchone()
                if not result or not self.verify_password(password, result[0]):
                    return None
                
                if not user_info['active']:
                    return None
                
                # Update last login
                cur.execute(
                    "UPDATE users SET last_login = NOW() WHERE username = %s",
                    (username,)
                )
                conn.commit()
                
                return user_info
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT user_id, username, email, password_hash, role, active FROM users WHERE username = ?",
                    (username,)
                )
                row = cursor.fetchone()
                if not row:
                    return None
                
                user_info = dict(row)
                password_hash = user_info.pop('password_hash')
                
                # Verify password
                if not self.verify_password(password, password_hash):
                    return None
                
                if not user_info['active']:
                    return None
                
                # Update last login
                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
                    (username,)
                )
                conn.commit()
                
                return user_info
            finally:
                conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user info by ID."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    "SELECT user_id, username, email, role, active, created_at, last_login FROM users WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT user_id, username, email, role, active, created_at, last_login FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def list_users(self) -> List[Dict]:
        """List all users (admin only)."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    "SELECT user_id, username, email, role, active, created_at, last_login FROM users ORDER BY created_at DESC"
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
            try:
                cursor.execute(
                    "SELECT user_id, username, email, role, active, created_at, last_login FROM users ORDER BY created_at DESC"
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def assign_device_to_user(self, user_id: int, device_id: str) -> bool:
        """Assign a device to a user."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO user_devices (user_id, device_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, device_id) DO NOTHING
                    """,
                    (user_id, device_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO user_devices (user_id, device_id)
                    VALUES (?, ?)
                    """,
                    (user_id, device_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def unassign_device_from_user(self, user_id: int, device_id: str) -> bool:
        """Remove device assignment from user."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    "DELETE FROM user_devices WHERE user_id = %s AND device_id = %s",
                    (user_id, device_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "DELETE FROM user_devices WHERE user_id = ? AND device_id = ?",
                    (user_id, device_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def get_user_devices(self, user_id: int) -> List[str]:
        """Get list of device IDs assigned to user."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT device_id FROM user_devices WHERE user_id = %s ORDER BY assigned_at",
                    (user_id,)
                )
                return [row[0] for row in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT device_id FROM user_devices WHERE user_id = ? ORDER BY assigned_at",
                    (user_id,)
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_device_users(self, device_id: str) -> List[Dict]:
        """Get all users assigned to a device."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    """
                    SELECT u.user_id, u.username, u.email, u.role
                    FROM users u
                    JOIN user_devices ud ON u.user_id = ud.user_id
                    WHERE ud.device_id = %s
                    ORDER BY u.username
                    """,
                    (device_id,)
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT u.user_id, u.username, u.email, u.role
                    FROM users u
                    JOIN user_devices ud ON u.user_id = ud.user_id
                    WHERE ud.device_id = ?
                    ORDER BY u.username
                    """,
                    (device_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def create_session(self, user_id: int, expires_in_hours: int = 24) -> str:
        """Create a session token for user."""
        from datetime import timedelta
        
        session_id = secrets.token_urlsafe(32)
        
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO sessions (session_id, user_id, expires_at)
                    VALUES (%s, %s, NOW() + INTERVAL '%s hours')
                    """,
                    (session_id, user_id, expires_in_hours),
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                expires_at = datetime.now() + timedelta(hours=expires_in_hours)
                cursor.execute(
                    """
                    INSERT INTO sessions (session_id, user_id, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, user_id, expires_at),
                )
                conn.commit()
            finally:
                conn.close()
        
        return session_id

    def get_user_from_session(self, session_id: str) -> Optional[Dict]:
        """Validate session and get user info."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            try:
                cur.execute(
                    """
                    SELECT u.user_id, u.username, u.email, u.role, u.active
                    FROM users u
                    JOIN sessions s ON u.user_id = s.user_id
                    WHERE s.session_id = %s AND s.expires_at > NOW()
                    """,
                    (session_id,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT u.user_id, u.username, u.email, u.role, u.active
                    FROM users u
                    JOIN sessions s ON u.user_id = s.user_id
                    WHERE s.session_id = ? AND s.expires_at > CURRENT_TIMESTAMP
                    """,
                    (session_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def delete_session(self, session_id: str) -> bool:
        """Delete/logout a session."""
        if self.use_postgres:
            conn = psycopg2.connect(self.pg_dsn)
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
                conn.commit()
                return cur.rowcount > 0
            finally:
                cur.close()
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
