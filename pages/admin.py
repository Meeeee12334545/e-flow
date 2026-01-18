"""
Admin Panel for User & Device Management

Streamlit page for administrators to:
1. Create new users
2. Select which sites (devices) users can see
"""

import streamlit as st
import pandas as pd
from auth import AuthDatabase
from database import FlowDatabase
from streamlit_auth import init_auth_state, is_authenticated, is_admin, get_current_user


def render_admin_panel():
    """Render the admin management panel."""
    if not is_authenticated():
        st.error("❌ You must be logged in")
        return
    
    if not is_admin():
        st.error("❌ Admin access required")
        return
    
    st.markdown("# 👨‍💼 Admin Panel")
    st.markdown("*Manage users and select which sites they can access*")
    
    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()
    
    # ==================== USER CREATION ====================
    st.markdown("## ➕ Create New User")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.form("create_user_form"):
            new_username = st.text_input("Username", placeholder="john_operator")
            new_email = st.text_input("Email", placeholder="john@example.com")
            new_password = st.text_input("Password", type="password", help="Min 8 characters")
            
            if st.form_submit_button("✅ Create User", use_container_width=True):
                if not new_username or not new_email or not new_password:
                    st.error("❌ Please fill in all fields")
                elif len(new_password) < 8:
                    st.error("❌ Password must be at least 8 characters")
                else:
                    success = auth_db.create_user(new_username, new_email, new_password, role="user")
                    if success:
                        st.success(f"✅ User '{new_username}' created successfully!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ Failed to create user (username/email may already exist)")
    
    with col2:
        st.info("📋 **New User Created:**\n- Role: User (can only see assigned sites)\n- Sites: None (assign below)")
    
    st.markdown("---")
    
    # ==================== SITE ASSIGNMENT ====================
    st.markdown("## 📍 Assign Sites to Users")
    
    users = auth_db.list_users()
    devices = flow_db.get_devices()
    
    if not users:
        st.warning("⚠️  No users available. Create a user first.")
    elif not devices:
        st.warning("⚠️  No devices/sites available")
    else:
        # Get only non-admin users for assignment
        regular_users = [u for u in users if u['role'] == 'user']
        
        if not regular_users:
            st.info("ℹ️  All users are admins. Create a regular user to assign sites.")
        else:
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("### Select User")
                selected_username = st.selectbox(
                    "Pick a user to manage sites for:",
                    options=[u['username'] for u in regular_users],
                    key="user_selector"
                )
                selected_user = next((u for u in regular_users if u['username'] == selected_username), None)
            
            if selected_user:
                with col2:
                    st.markdown("### Current Sites")
                    user_device_ids = auth_db.get_user_devices(selected_user['user_id'])
                    st.write(f"**{len(user_device_ids)}** site(s) assigned")
                
                st.markdown("---")
                st.markdown(f"### 📊 Manage Sites for **{selected_user['username']}**")
                
                # Show all devices as checkboxes
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Available Sites to Add:**")
                    
                    # Devices not yet assigned
                    unassigned_devices = [d for d in devices if d['device_id'] not in user_device_ids]
                    
                    if unassigned_devices:
                        for device in unassigned_devices:
                            if st.button(
                                f"➕ Add: {device['device_name']}",
                                key=f"add_{selected_user['user_id']}_{device['device_id']}",
                                use_container_width=True
                            ):
                                auth_db.assign_device_to_user(selected_user['user_id'], device['device_id'])
                                st.success(f"✅ Added {device['device_name']}")
                                st.rerun()
                    else:
                        st.info("✅ All sites assigned")
                
                with col2:
                    st.markdown("**Currently Assigned Sites:**")
                    
                    # Devices already assigned
                    if user_device_ids:
                        for device_id in user_device_ids:
                            device = next((d for d in devices if d['device_id'] == device_id), None)
                            if device:
                                col_a, col_b = st.columns([3, 1])
                                with col_a:
                                    st.write(f"📍 {device['device_name']}")
                                with col_b:
                                    if st.button(
                                        "❌",
                                        key=f"remove_{selected_user['user_id']}_{device_id}",
                                        help=f"Remove {device['device_name']}"
                                    ):
                                        auth_db.unassign_device_from_user(selected_user['user_id'], device_id)
                                        st.warning(f"✅ Removed {device['device_name']}")
                                        st.rerun()
                    else:
                        st.info("No sites assigned yet")
        
        st.markdown("---")
        st.markdown("### 📋 All Users Overview")
        
        # Summary table
        user_summary = []
        for user in regular_users:
            user_device_ids = auth_db.get_user_devices(user['user_id'])
            device_names = [d['device_name'] for d in devices if d['device_id'] in user_device_ids]
            user_summary.append({
                'Username': user['username'],
                'Email': user['email'],
                'Sites Assigned': len(user_device_ids),
                'Sites': ', '.join(device_names) if device_names else 'None'
            })
        
        if user_summary:
            df_summary = pd.DataFrame(user_summary)
            st.dataframe(df_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No regular users to display")


if __name__ == "__main__":
    init_auth_state()
    render_admin_panel()
