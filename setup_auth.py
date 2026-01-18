#!/usr/bin/env python
"""
Setup script for e-flow authentication system.

This script helps initialize the authentication system by creating
the first admin user and configuring initial devices.
"""

import sys
import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth import AuthDatabase
from database import FlowDatabase
from config import DEVICES


def setup_auth():
    """Initialize authentication system."""
    print("\n" + "="*60)
    print("🔐 E-FLOW AUTHENTICATION SETUP")
    print("="*60 + "\n")
    
    auth_db = AuthDatabase()
    flow_db = FlowDatabase()
    
    # Step 1: Initialize devices
    print("📊 Step 1: Initializing Devices")
    print("-" * 40)
    
    existing_devices = flow_db.get_devices()
    existing_ids = {d['device_id'] for d in existing_devices}
    
    for device_id, device_info in DEVICES.items():
        if device_id not in existing_ids:
            flow_db.add_device(
                device_id,
                device_info.get("name", device_id),
                device_info.get("location", "")
            )
            print(f"✅ Added device: {device_id} - {device_info.get('name')}")
        else:
            print(f"⏭️  Device already exists: {device_id}")
    
    all_devices = flow_db.get_devices()
    print(f"\n📝 Total devices: {len(all_devices)}\n")
    
    # Step 2: Create admin user
    print("👨‍💼 Step 2: Create Admin User")
    print("-" * 40)
    
    while True:
        admin_username = input("Admin username (default: 'admin'): ").strip() or "admin"
        
        # Check if user exists
        existing_user = auth_db.authenticate_user(admin_username, "")
        if existing_user:
            print(f"⚠️  User '{admin_username}' already exists")
            retry = input("Create different user? (y/n): ").lower()
            if retry != 'y':
                print("Skipping admin user creation.")
                break
            continue
        
        admin_email = input("Admin email: ").strip()
        if not admin_email:
            print("Email is required")
            continue
        
        while True:
            admin_password = getpass.getpass("Admin password: ")
            if len(admin_password) < 8:
                print("❌ Password must be at least 8 characters")
                continue
            
            confirm_password = getpass.getpass("Confirm password: ")
            if admin_password != confirm_password:
                print("❌ Passwords don't match")
                continue
            
            break
        
        # Create user
        success = auth_db.create_user(
            admin_username,
            admin_email,
            admin_password,
            role="admin"
        )
        
        if success:
            print(f"✅ Admin user '{admin_username}' created successfully!\n")
            break
        else:
            print("❌ Failed to create user (may already exist)\n")
    
    # Step 3: Create demo user (optional)
    print("👤 Step 3: Create Demo User (Optional)")
    print("-" * 40)
    
    create_demo = input("Create a demo user? (y/n): ").lower() == 'y'
    
    if create_demo:
        demo_username = input("Demo username (default: 'demo'): ").strip() or "demo"
        demo_email = input("Demo email (default: 'demo@example.com'): ").strip() or "demo@example.com"
        demo_password = getpass.getpass("Demo password (default: 'demo1234'): ") or "demo1234"
        
        success = auth_db.create_user(
            demo_username,
            demo_email,
            demo_password,
            role="user"
        )
        
        if success:
            print(f"✅ Demo user '{demo_username}' created!")
            
            # Assign first device to demo user
            if all_devices:
                first_device = all_devices[0]
                auth_db.assign_device_to_user(1, first_device['device_id'])  # Assuming demo user has ID 2
                print(f"✅ Assigned {first_device['device_name']} to demo user")
        else:
            print("❌ Failed to create demo user")
    
    # Step 4: Summary
    print("\n" + "="*60)
    print("✅ SETUP COMPLETE")
    print("="*60)
    print("\nYou can now run the app:")
    print("  streamlit run app.py\n")
    print("Login credentials:")
    print(f"  Username: {admin_username}")
    print(f"  Password: (the password you entered)\n")
    print("Next steps:")
    print("  1. Log in to the dashboard")
    print("  2. Go to Admin Panel (/admin)")
    print("  3. Create more users and assign devices")
    print("  4. Users can then log in and view their assigned meters\n")


if __name__ == "__main__":
    try:
        setup_auth()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
