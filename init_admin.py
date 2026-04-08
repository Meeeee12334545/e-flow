#!/usr/bin/env python
"""
Quick initialization script to create the admin user.

The admin password must be provided via the ADMIN_INIT_PASSWORD environment
variable.  If it is not set a secure random password is generated and printed
to stdout once — note it down before the terminal session closes.
"""

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auth import AuthDatabase
from database import FlowDatabase
from config import DEVICES

def init_with_default_admin():
    """Initialize with a secure admin password."""
    print("Initializing EDS FlowSense authentication system...")

    admin_password = os.getenv("ADMIN_INIT_PASSWORD", "")
    if not admin_password:
        admin_password = secrets.token_urlsafe(16)
        # Write to stderr so the credential is not captured in log files
        import sys as _sys
        _sys.stderr.write("\n  ⚠ ADMIN_INIT_PASSWORD not set — generated a random password.\n")
        _sys.stderr.write("  ⚠ Save this now, it will NOT be shown again.\n\n")
        _sys.stderr.write(f"     Admin password: {admin_password}\n\n")
        _sys.stderr.flush()

    # Initialize databases
    flow_db = FlowDatabase()
    auth_db = AuthDatabase()

    # Add devices
    print("\nInitializing devices...")
    for device_id, device_info in DEVICES.items():
        flow_db.add_device(
            device_id,
            device_info.get("name", device_id),
            device_info.get("location", "")
        )
        print(f"  ✓ {device_id}: {device_info.get('name')}")

    # Create admin user
    print("\nCreating admin user...")
    success = auth_db.create_user(
        username="admin",
        email="admin@example.com",
        password=admin_password,
        role="admin"
    )

    if success:
        print("  ✓ Admin user created: admin / (password shown above or set via ADMIN_INIT_PASSWORD)")
    else:
        print("  ⚠ Admin user already exists — password was NOT changed.")

    # Assign all devices to admin
    print("\nAssigning all devices to admin user...")
    devices = flow_db.get_devices()
    admin_user = auth_db.authenticate_user("admin", admin_password)

    if admin_user:
        admin_id = admin_user['user_id']
        for device in devices:
            auth_db.assign_device_to_user(admin_id, device['device_id'])
            print(f"  ✓ Assigned {device['device_name']}")

    print("\n✅ Initialization complete!")
    print("\nRun: streamlit run app.py")

if __name__ == "__main__":
    init_with_default_admin()
