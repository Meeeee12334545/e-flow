"""
Streamlit Authentication UI Module

Handles login/logout, session management, and auth state in Streamlit.
"""

import streamlit as st
from auth import AuthDatabase


def init_auth_state():
    """Initialize session state for authentication."""
    if 'auth_db' not in st.session_state:
        st.session_state.auth_db = AuthDatabase()
    
    if 'user' not in st.session_state:
        st.session_state.user = None
    
    if 'session_id' not in st.session_state:
        st.session_state.session_id = None


def login_page():
    """Display login page."""
    st.markdown("# 🔐 e-flow Login")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("---")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            st.markdown("### Login to Your Account")
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("🔓 Login", use_container_width=True):
                if not username or not password:
                    st.error("Please enter username and password")
                else:
                    user_info = st.session_state.auth_db.authenticate_user(username, password)
                    if user_info:
                        session_id = st.session_state.auth_db.create_session(user_info['user_id'])
                        st.session_state.user = user_info
                        st.session_state.session_id = session_id
                        st.success("✅ Login successful!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password")
        
        with tab2:
            st.markdown("### Create New Account")
            new_username = st.text_input("Username", key="signup_username")
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm")
            
            if st.button("📝 Sign Up", use_container_width=True):
                if not new_username or not new_email or not new_password:
                    st.error("Please fill in all fields")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    success = st.session_state.auth_db.create_user(
                        new_username, new_email, new_password, role="user"
                    )
                    if success:
                        st.success("✅ Account created! Please login.")
                    else:
                        st.error("❌ Username or email already exists")
        
        st.markdown("---")


def logout():
    """Logout current user."""
    if st.session_state.session_id:
        st.session_state.auth_db.delete_session(st.session_state.session_id)
    
    st.session_state.user = None
    st.session_state.session_id = None
    st.rerun()


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return st.session_state.user is not None


def is_admin() -> bool:
    """Check if current user is admin."""
    return is_authenticated() and st.session_state.user.get('role') == 'admin'


def get_current_user() -> dict:
    """Get current authenticated user info."""
    return st.session_state.user or {}


def render_auth_header():
    """Render authentication header in sidebar."""
    with st.sidebar:
        st.markdown("---")
        
        if is_authenticated():
            user = get_current_user()
            col1, col2 = st.columns([3, 1])
            
            with col1:
                role_badge = "👨‍💼 Admin" if is_admin() else "👤 User"
                st.markdown(f"**{user['username']}**  \n{role_badge}")
            
            with col2:
                if st.button("🚪"):
                    logout()
        else:
            st.markdown("*Not logged in*")


def filter_devices_for_user(all_devices: list) -> list:
    """Filter devices based on user's access rights."""
    if not is_authenticated():
        return []
    
    user = get_current_user()
    
    # Admins see all devices
    if is_admin():
        return all_devices
    
    # Regular users only see assigned devices
    user_device_ids = st.session_state.auth_db.get_user_devices(user['user_id'])
    return [d for d in all_devices if d.get('device_id') in user_device_ids]


if __name__ == "__main__":
    init_auth_state()
    
    if not is_authenticated():
        login_page()
    else:
        user = get_current_user()
        st.write(f"Hello, {user['username']}!")
