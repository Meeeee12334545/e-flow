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
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem 0;">
        <div style="background:linear-gradient(135deg,#002f6c 0%,#01408f 100%);
                    display:inline-block; padding:18px 36px; border-radius:12px;
                    box-shadow:0 4px 20px rgba(0,47,108,0.25); margin-bottom:1.5rem;">
            <div style="color:#ffffff; font-size:2rem; font-weight:700; letter-spacing:-0.5px;">💧 e-flow</div>
            <div style="color:#ffc20e; font-size:0.75rem; font-weight:600; letter-spacing:2px; text-transform:uppercase;">
                by EDS — e-d-s.com.au
            </div>
        </div>
        <div style="color:#6b7a99; font-size:0.9rem;">Sewer Flow Monitoring Platform</div>
    </div>
    """, unsafe_allow_html=True)
    
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
            role_badge = "👨‍💼 Admin" if is_admin() else "👤 User"
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"<div style='font-size:0.9rem; font-weight:600; color:#002f6c;'>{user['username']}</div>"
                    f"<div style='font-size:0.75rem; color:#6b7a99;'>{role_badge}</div>",
                    unsafe_allow_html=True,
                )
            with col2:
                if st.button("✕", key="logout_btn", help="Logout"):
                    logout()
            
            # Admin quick links
            if is_admin():
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🛠 Admin", use_container_width=True, key="admin_panel_btn"):
                        st.switch_page("pages/admin.py")
                with col2:
                    if st.button("👤 Profile", use_container_width=True, key="profile_btn"):
                        st.switch_page("pages/profile.py")
            else:
                st.markdown("---")
                if st.button("👤 My Profile", use_container_width=True, key="my_profile_btn"):
                    st.switch_page("pages/profile.py")
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
