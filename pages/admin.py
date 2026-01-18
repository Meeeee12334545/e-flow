"""
Admin Panel for User & Device Management

Streamlit page for administrators to manage users and device assignments.
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
    
    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()
    
    # Navigation tabs
    tab1, tab2, tab3 = st.tabs(["👥 User Management", "📊 Device Management", "🔗 Assignments"])
    
    # ==================== USER MANAGEMENT ====================
    with tab1:
        st.markdown("## User Management")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### Create New User")
        with col2:
            if st.button("🔄 Refresh", key="refresh_users"):
                st.rerun()
        
        # Create user form
        with st.form("create_user_form"):
            new_username = st.text_input("Username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            
            if st.form_submit_button("➕ Create User"):
                if not new_username or not new_email or not new_password:
                    st.error("Please fill in all fields")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    success = auth_db.create_user(new_username, new_email, new_password, new_role)
                    if success:
                        st.success(f"✅ User '{new_username}' created successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to create user (username/email may exist)")
        
        st.markdown("---")
        st.markdown("### Existing Users")
        
        users = auth_db.list_users()
        if users:
            # Display users in a table
            df_users = pd.DataFrame(users)
            df_users = df_users[['user_id', 'username', 'email', 'role', 'active', 'created_at']]
            st.dataframe(df_users, use_container_width=True, hide_index=True)
            
            # User actions
            st.markdown("### User Actions")
            selected_username = st.selectbox("Select user to manage", [u['username'] for u in users])
            
            selected_user = next((u for u in users if u['username'] == selected_username), None)
            if selected_user:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🔄 Toggle Active Status"):
                        # Would need to add toggle_user_active method to AuthDatabase
                        st.info("Feature: Toggle user active/inactive status")
                
                with col2:
                    if st.button("🔐 Reset Password"):
                        st.info("Feature: Send password reset link")
                
                with col3:
                    if st.button("🗑️ Delete User"):
                        st.warning("Feature: Delete user and their assignments")
        else:
            st.info("No users found")
    
    # ==================== DEVICE MANAGEMENT ====================
    with tab2:
        st.markdown("## Device Management")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### Registered Devices")
        with col2:
            if st.button("🔄 Refresh", key="refresh_devices"):
                st.rerun()
        
        devices = flow_db.get_devices()
        
        if devices:
            df_devices = pd.DataFrame(devices)
            st.dataframe(df_devices, use_container_width=True, hide_index=True)
            
            # Device statistics
            st.markdown("### Device Statistics")
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Total Devices", len(devices))
            
            with col2:
                total_measurements = flow_db.get_measurement_count()
                st.metric("Total Measurements", total_measurements)
        else:
            st.info("No devices registered yet")
    
    # ==================== DEVICE ASSIGNMENTS ====================
    with tab3:
        st.markdown("## Device Assignments")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### Assign Devices to Users")
        with col2:
            if st.button("🔄 Refresh", key="refresh_assignments"):
                st.rerun()
        
        users = auth_db.list_users()
        devices = flow_db.get_devices()
        
        if not users:
            st.warning("No users available")
        elif not devices:
            st.warning("No devices available")
        else:
            # Assignment form
            with st.form("assign_device_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    selected_user_id = st.selectbox(
                        "Select User",
                        options=[u['user_id'] for u in users],
                        format_func=lambda uid: next((u['username'] for u in users if u['user_id'] == uid), "")
                    )
                
                with col2:
                    selected_device_id = st.selectbox(
                        "Select Device",
                        options=[d['device_id'] for d in devices],
                        format_func=lambda did: next((d['device_name'] for d in devices if d['device_id'] == did), "")
                    )
                
                if st.form_submit_button("🔗 Assign Device"):
                    success = auth_db.assign_device_to_user(selected_user_id, selected_device_id)
                    if success:
                        st.success("✅ Device assigned successfully!")
                        st.rerun()
                    else:
                        st.info("Device already assigned to this user")
            
            st.markdown("---")
            st.markdown("### Current Assignments")
            
            # Show all assignments
            for user in users:
                user_devices = auth_db.get_user_devices(user['user_id'])
                if user_devices:
                    with st.expander(f"👤 {user['username']} ({len(user_devices)} device{'s' if len(user_devices) != 1 else ''})"):
                        for device_id in user_devices:
                            device = next((d for d in devices if d['device_id'] == device_id), None)
                            if device:
                                col1, col2 = st.columns([4, 1])
                                with col1:
                                    st.markdown(f"📊 **{device['device_name']}** ({device['device_id']})")
                                with col2:
                                    if st.button("❌", key=f"remove_{user['user_id']}_{device_id}"):
                                        auth_db.unassign_device_from_user(user['user_id'], device_id)
                                        st.success("✅ Device unassigned")
                                        st.rerun()
            
            # Users without devices
            users_no_devices = [u for u in users if not auth_db.get_user_devices(u['user_id'])]
            if users_no_devices:
                st.info(f"⚠️  {len(users_no_devices)} user(s) have no device assignments")


if __name__ == "__main__":
    init_auth_state()
    render_admin_panel()
