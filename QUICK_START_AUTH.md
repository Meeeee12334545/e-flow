# E-Flow Multi-User System - Quick Reference

## 🚀 Getting Started in 5 Minutes

### Step 1: Setup (1 minute)
```bash
cd /workspaces/e-flow
python setup_auth.py
```
Follow the prompts to create an admin user.

### Step 2: Run App (30 seconds)
```bash
streamlit run app.py
```

### Step 3: Login
- Use the admin credentials you created
- Or sign up as a new user

## 👥 User Types

| Role | Can | Cannot |
|------|-----|--------|
| **Admin** | Create users, assign devices, view all data | - |
| **User** | View assigned devices, login/logout | Create users, assign devices |

## 🔑 Quick Commands

### Create Admin User (Direct Python)
```python
from auth import AuthDatabase

auth_db = AuthDatabase()
auth_db.create_user("admin", "admin@email.com", "password123", role="admin")
```

### Create Regular User (Direct Python)
```python
auth_db.create_user("john", "john@email.com", "password123", role="user")
```

### Assign Device to User
```python
auth_db.assign_device_to_user(user_id=1, device_id="FIT100")
```

### Get User's Devices
```python
devices = auth_db.get_user_devices(user_id=1)
```

## 📊 Devices

### Current Meters
1. **FIT100** - Main Inflow Lismore STP
2. **BYPASS_INFLOW** - Bypass Inflow Lismore STP

Both meters automatically collected every 60 seconds by monitor service.

## 🔗 Pages

### Public
- `/` - **Login/Signup** (if not authenticated)

### User Pages
- `/` - **Dashboard** (view assigned meter data)
- `/profile` - **My Profile** (view assigned devices)

### Admin Pages
- `/admin` - **Admin Panel** (manage users & devices)

## 🔐 Security

- ✅ Passwords hashed with PBKDF2-SHA256
- ✅ Session tokens expire after 24 hours
- ✅ Users can only see assigned devices
- ✅ Automatic password validation (min 8 characters)

## 📝 Use Cases

### Scenario 1: Multi-Site Monitoring
1. Admin creates users for each site operator
2. Admin assigns site-specific meter to each user
3. Site operators log in and see only their meter

### Scenario 2: Management Overview
1. Admin creates manager account
2. Admin assigns all meters to manager
3. Manager can see all meters in one dashboard

### Scenario 3: Self-Service Portal
1. Enable public signup (users see signup tab)
2. Admin assigns meters after email verification
3. Users manage their own accounts

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't login | Run setup_auth.py to create admin user |
| No devices | Admin needs to assign devices in /admin |
| Permission error | Check user role in database |
| Reset password | Contact admin (feature planned) |

## 📊 Useful Queries

### List All Users
```python
from auth import AuthDatabase
auth_db = AuthDatabase()
users = auth_db.list_users()
for user in users:
    print(f"{user['username']} ({user['role']})")
```

### List User's Devices
```python
user_id = 1
devices = auth_db.get_user_devices(user_id)
print(f"User has {len(devices)} devices: {devices}")
```

### List Device's Users
```python
device_id = "FIT100"
users = auth_db.get_device_users(device_id)
for user in users:
    print(f"{user['username']} ({user['role']})")
```

### Export All Users
```python
import csv
from auth import AuthDatabase

auth_db = AuthDatabase()
users = auth_db.list_users()

with open('users.csv', 'w') as f:
    writer = csv.DictWriter(f, fieldnames=['user_id', 'username', 'email', 'role', 'active'])
    writer.writeheader()
    writer.writerows(users)
```

## 🔄 Workflows

### Admin: Create User and Assign Device

1. **Web UI:**
   - Go to http://localhost:8501/admin
   - Click "Create User" tab
   - Enter username, email, password
   - Click "Create User"

2. **Assign Device:**
   - Go to "Assignments" tab
   - Select the user
   - Select a device
   - Click "Assign Device"

3. **User can now login and see the device**

### Admin: Create User via Python

```python
from auth import AuthDatabase
from database import FlowDatabase

auth_db = AuthDatabase()
flow_db = FlowDatabase()

# Create user
auth_db.create_user("operator", "op@example.com", "secure123", "user")

# Get all devices
devices = flow_db.get_devices()

# Assign first device to user (assuming user_id=2)
auth_db.assign_device_to_user(user_id=2, device_id=devices[0]['device_id'])

print("User created and device assigned!")
```

## 📈 Monitoring Multi-User Access

Check [monitor.py](monitor.py) logs to see both devices being collected:

```
[Check #1] Checking for data updates...
  Checking device: FIT100
  Depth: 132 mm
  Velocity: 0.65 m/s
  Flow: 28.5 L/s
  ✅ Data changed and stored for FIT100!
  
  Checking device: BYPASS_INFLOW
  Depth: 45 mm
  Velocity: 0.28 m/s
  Flow: 12.3 L/s
  ✅ Data changed and stored for BYPASS_INFLOW!
```

## 🎯 Next Steps

1. ✅ Run setup_auth.py
2. ✅ Create admin and demo users
3. ✅ Go to /admin and assign devices
4. ✅ Log in as different users to test access
5. ✅ Check monitor.log to see both meters being collected

## 📚 Documentation

- See [AUTH_GUIDE.md](AUTH_GUIDE.md) for complete authentication reference
- See [AUTHENTICATION_IMPLEMENTATION.md](AUTHENTICATION_IMPLEMENTATION.md) for implementation details
- See [config.py](config.py) for device configuration

## 💡 Tips

- **Admins:** Create multiple accounts for different teams
- **Security:** Change default password after first setup
- **Monitoring:** Both meters collect data independently
- **Access:** Users see only their assigned devices
- **Performance:** No data filtering on dashboard queries

---

**Need help?** Check [AUTH_GUIDE.md](AUTH_GUIDE.md) for detailed information.
