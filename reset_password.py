#!/usr/bin/env python
"""
Reset the password for a user (admin or any user) in EDS FlowSense (EDS-FS).
Usage: python reset_password.py <username> <new_password>
"""

import sys
from auth import AuthDatabase

if len(sys.argv) != 3:
    print("Usage: python reset_password.py <username> <new_password>")
    sys.exit(1)

username = sys.argv[1]
new_password = sys.argv[2]

auth_db = AuthDatabase()

# Check if user exists
user = None
for u in auth_db.list_users():
    if u['username'] == username:
        user = u
        break

if not user:
    print(f"❌ User '{username}' not found.")
    sys.exit(1)

# Reset password (requires method in AuthDatabase)
if hasattr(auth_db, 'reset_password'):
    success = auth_db.reset_password(username, new_password)
    if success:
        print(f"✅ Password for '{username}' reset successfully.")
    else:
        print(f"❌ Failed to reset password for '{username}'.")
else:
    print("❌ Password reset method not implemented in AuthDatabase.")
    sys.exit(1)
