# E-Flow Authentication & User Management

## Overview

The e-flow system now includes a complete role-based access control (RBAC) system with:

- ✅ User authentication (login/signup)
- ✅ Role-based access (Admin/User)
- ✅ Device assignment management
- ✅ Session-based authentication
- ✅ Secure password hashing (PBKDF2-SHA256)

## Architecture

### Database Schema

#### Users Table
```sql
users (
    user_id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    role TEXT ('admin', 'user'),
    active BOOLEAN,
    created_at TIMESTAMP,
    last_login TIMESTAMP
)
```

#### User-Device Assignments
```sql
user_devices (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    device_id TEXT,
    assigned_at TIMESTAMP,
    UNIQUE(user_id, device_id)
)
```

#### Sessions
```sql
sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at TIMESTAMP,
    expires_at TIMESTAMP
)
```

## User Roles

### Admin Role
- Create new users
- Assign/unassign devices to users
- View all users and devices
- Manage user assignments
- Full access to admin panel

### User Role
- View assigned devices only
- Access dashboard for assigned meters
- View profile and session info
- Cannot manage other users or devices

## Getting Started

### Initial Setup

1. **First Admin User (Manual)**

```python
from auth import AuthDatabase

auth_db = AuthDatabase()

# Create first admin user
auth_db.create_user(
    username="admin",
    email="admin@example.com",
    password="secure_password_123",
    role="admin"
)
```

2. **Running the Application**

```bash
streamlit run app.py
```

First time:
- Click "Sign Up" to create a regular user account, OR
- Use the first admin account to create users

### User Workflows

#### As Admin:

1. Log in with admin credentials
2. Click "Admin Panel" in sidebar (or navigate to `/admin`)
3. **Create Users:**
   - Enter username, email, password
   - Select role (admin/user)
   - Click "Create User"

4. **Assign Devices:**
   - Go to "Assignments" tab
   - Select user and device
   - Click "Assign Device"
   - User can now access that device in the dashboard

#### As Regular User:

1. Sign up for account or wait for admin to create one
2. Log in to dashboard
3. Select your assigned device from dropdown
4. View meter data
5. Go to "My Profile" to see all assigned devices

## Configuration

### Environment Variables

```bash
# Database (optional - defaults to SQLite)
DATABASE_URL="postgresql://user:password@localhost/e_flow"

# Auth settings
AUTH_SESSION_TIMEOUT=24  # hours (default)
```

### Password Requirements

- Minimum 8 characters
- Uses PBKDF2-SHA256 with 100,000 iterations
- Session-based with 24-hour default expiration

## Security Features

1. **Password Hashing:**
   - PBKDF2-SHA256 with random salt
   - 100,000 iterations
   - Constant-time comparison

2. **Session Management:**
   - Secure token generation (32 bytes)
   - Expiration timestamps
   - Database-backed sessions

3. **Access Control:**
   - Device visibility filtered by user role
   - Admins see all devices
   - Users see only assigned devices

4. **Database Support:**
   - SQLite (default) with file permissions
   - PostgreSQL for multi-user deployments

## Module Reference

### `auth.py` - Core Authentication

Main authentication database class:

```python
from auth import AuthDatabase

auth_db = AuthDatabase()

# User management
auth_db.create_user(username, email, password, role="user")
user = auth_db.authenticate_user(username, password)
auth_db.get_user_by_id(user_id)
users = auth_db.list_users()

# Device assignment
auth_db.assign_device_to_user(user_id, device_id)
auth_db.unassign_device_from_user(user_id, device_id)
devices = auth_db.get_user_devices(user_id)

# Session management
session_id = auth_db.create_session(user_id)
user = auth_db.get_user_from_session(session_id)
auth_db.delete_session(session_id)  # logout
```

### `streamlit_auth.py` - Streamlit Integration

Streamlit authentication helpers:

```python
from streamlit_auth import (
    init_auth_state,           # Initialize session state
    is_authenticated,          # Check if logged in
    is_admin,                  # Check if admin role
    get_current_user,          # Get logged-in user info
    filter_devices_for_user,   # Get user's accessible devices
    login_page,                # Render login UI
    render_auth_header,        # Render sidebar auth info
    logout                     # Logout current user
)

# Initialize authentication on app start
init_auth_state()

# Check authentication
if not is_authenticated():
    login_page()
    st.stop()

# Filter devices based on user permissions
user_devices = filter_devices_for_user(all_devices)
```

### `pages/admin.py` - Admin Panel

Full admin interface for:
- User management (create users)
- Device management (view devices)
- Device assignments (assign devices to users)

Navigate to: `http://localhost:8501/admin`

### `pages/profile.py` - User Profile

User profile page showing:
- Account information
- Assigned devices
- Session information

Navigate to: `http://localhost:8501/profile`

## Database Initialization

Authentication tables are automatically created on first run:

```python
auth_db = AuthDatabase()
# Creates users, user_devices, and sessions tables
```

### Manual Database Setup (PostgreSQL)

```sql
-- Users
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Device assignments
CREATE TABLE user_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, device_id)
);

-- Sessions
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_username ON users(username);
CREATE INDEX idx_user_devices ON user_devices(user_id);
CREATE INDEX idx_sessions_user ON sessions(user_id);
```

## Troubleshooting

### User can't see devices
1. Check if user has devices assigned in Admin Panel
2. Verify device exists in database
3. Confirm device is in DEVICES config

### Password hashing issues
- Passwords must be at least 8 characters
- Check database hasn't been corrupted
- Verify PBKDF2 library available: `pip install hashlib`

### Session expiration
- Default is 24 hours
- Sessions stored in database, not in-memory
- Expired sessions automatically cleaned up

### Database errors
For SQLite:
- Check file permissions on `flow_data.db`
- Ensure write access to database directory

For PostgreSQL:
- Check `DATABASE_URL` environment variable
- Verify `psycopg2` is installed: `pip install psycopg2-binary`
- Test connection: `psql $DATABASE_URL`

## API Integration

The authentication system can be extended for external APIs:

```python
# Create API tokens for device integration
api_token = secrets.token_urlsafe(32)

# Validate API request
user = auth_db.get_user_from_session(api_token)
if user and user['role'] == 'admin':
    # Allow API access
    pass
```

## Future Enhancements

- [ ] Two-factor authentication (2FA)
- [ ] OAuth2 integration (Google, GitHub)
- [ ] API key management
- [ ] Permission-based access (read-only, read-write)
- [ ] Audit logging
- [ ] Password reset email flow
- [ ] Session management dashboard

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review database schema
3. Verify DEVICES config
4. Check Streamlit console for errors
