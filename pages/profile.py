"""
User Profile Page

Streamlit page for users to view their profile and assigned devices.
"""

import streamlit as st
from database import FlowDatabase
from streamlit_auth import init_auth_state, is_authenticated, get_current_user


def render_profile_page():
    """Render user profile page."""
    if not is_authenticated():
        st.error("❌ You must be logged in")
        return
    
    user = get_current_user()
    
    st.markdown("# 👤 My Profile")
    
    # User info
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("## Account Information")
        st.write(f"**Username:** {user['username']}")
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Role:** {user['role'].capitalize()}")
    
    with col2:
        st.markdown("## Account Status")
        if user['active']:
            st.success("✅ Active")
        else:
            st.error("❌ Inactive")
    
    st.markdown("---")
    
    # Assigned devices
    st.markdown("## 📊 Assigned Devices")
    
    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()
    
    user_devices = auth_db.get_user_devices(user['user_id'])
    
    if user_devices:
        all_devices = flow_db.get_devices()
        assigned_devices = [d for d in all_devices if d['device_id'] in user_devices]
        
        if assigned_devices:
            st.markdown(f"You have access to **{len(assigned_devices)}** device(s):")
            
            for device in assigned_devices:
                with st.container():
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.markdown(f"### 📍 {device['device_name']}")
                        st.write(f"Location: {device['location'] or 'Not specified'}")
                    
                    with col2:
                        st.write(f"**ID:** {device['device_id']}")
                    
                    with col3:
                        if st.button("📈 View Data", key=f"view_{device['device_id']}"):
                            st.session_state.selected_device = device['device_id']
                            st.write(f"Go to main dashboard and select {device['device_name']}")
                    
                    st.markdown("---")
        else:
            st.info("No devices assigned to your account yet")
    else:
        st.info("You don't have any devices assigned yet. Contact an administrator.")
    
    st.markdown("---")
    
    # Session info
    with st.expander("🔐 Session Information"):
        st.write(f"**User ID:** {user['user_id']}")
        st.write(f"**Session Token:** {st.session_state.session_id[:20]}...")


if __name__ == "__main__":
    init_auth_state()
    render_profile_page()
