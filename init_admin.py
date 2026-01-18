#!/usr/bin/env python
"""
Quick initialization script to create admin user with admin/admin credentials.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from auth import AuthDatabase
from database import FlowDatabase
from config import DEVICES

def init_with_default_admin():
    """Initialize with admin/admin credentials."""
    print("Initializing e-flow authentication system...")
    
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
    
    # Create admin user with admin/admin
    print("\nCreating admin user...")
    success = auth_db.create_user(
        username="admin",
        email="admin@example.com",
        password="admin",
        role="admin"
    )
    
    if success:
        print("  ✓ Admin user created: admin / admin")
    else:
        print("  ⚠ Admin user already exists or error occurred")
    
    # Assign all devices to admin
    print("\nAssigning all devices to admin user...")
    devices = flow_db.get_devices()
    admin_user_id = auth_db.authenticate_user("admin", "admin")
    
    if admin_user_id:
        admin_id = admin_user_id['user_id']
        for device in devices:
            auth_db.assign_device_to_user(admin_id, device['device_id'])
            print(f"  ✓ Assigned {device['device_name']}")
    
    print("\n✅ Initialization complete!")
    print("\nLogin credentials:")
    print("  Username: admin")
    print("  Password: admin")
    print("\nRun: streamlit run app.py")

if __name__ == "__main__":
    init_with_default_admin()
