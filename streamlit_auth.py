"""
Streamlit Authentication UI Module

Handles login/logout, session management, and auth state in Streamlit.
"""

import streamlit as st
from auth import AuthDatabase
from shared_styles import apply_styles


def init_auth_state():
    """Initialize session state for authentication."""
    if 'auth_db' not in st.session_state:
        st.session_state.auth_db = AuthDatabase()

    if 'user' not in st.session_state:
        st.session_state.user = None

    if 'session_id' not in st.session_state:
        st.session_state.session_id = None


def login_page():
    """Display a polished, branded login page."""
    apply_styles()

    # Brand header
    st.markdown("""
    <div style="text-align: center; padding: 2.5rem 1rem 1.5rem;">
        <div style="
            width: 64px; height: 64px; border-radius: 18px;
            background: linear-gradient(135deg, #0f4c81 0%, #0b76ca 100%);
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 2rem; margin-bottom: 0.75rem;
            box-shadow: 0 8px 24px rgba(15,76,129,0.25);
        ">🌊</div>
        <h1 style="
            font-size: 2rem !important; font-weight: 700 !important;
            color: #0f4c81 !important; margin: 0 !important;
            letter-spacing: -0.03em; line-height: 1.1 !important;
        ">e-flow™</h1>
        <p style="
            font-size: 0.92rem !important; color: #6b7280 !important;
            margin: 0.3rem 0 0 0 !important;
        ">by EDS — Professional hydrological monitoring</p>
    </div>
    """, unsafe_allow_html=True)

    # Centered card
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style="
            background: #ffffff; border: 1px solid #dfe7ef;
            border-radius: 22px; padding: 36px 40px;
            box-shadow: 0 24px 60px rgba(15,76,129,0.10);
        ">
        """, unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["🔓 Login", "📝 Sign Up"])

        with tab1:
            st.markdown(
                '<p style="font-size:1.1rem;font-weight:700;color:#233047;margin:0 0 1rem 0;">'
                'Welcome back</p>',
                unsafe_allow_html=True,
            )
            username = st.text_input("Username", key="login_username", placeholder="your_username")
            password = st.text_input("Password", type="password", key="login_password",
                                     placeholder="••••••••")

            if st.button("Login →", use_container_width=True, key="login_btn"):
                if not username or not password:
                    st.error("Please enter your username and password.")
                else:
                    user_info = st.session_state.auth_db.authenticate_user(username, password)
                    if user_info:
                        session_id = st.session_state.auth_db.create_session(user_info['user_id'])
                        st.session_state.user = user_info
                        st.session_state.session_id = session_id
                        st.success("✅ Login successful!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password.")

        with tab2:
            st.markdown(
                '<p style="font-size:1.1rem;font-weight:700;color:#233047;margin:0 0 1rem 0;">'
                'Create an account</p>',
                unsafe_allow_html=True,
            )
            new_username = st.text_input("Username", key="signup_username",
                                         placeholder="john_operator")
            new_email = st.text_input("Email", key="signup_email",
                                      placeholder="john@example.com")
            new_password = st.text_input("Password", type="password", key="signup_password",
                                         placeholder="Min 8 characters")
            confirm_password = st.text_input("Confirm Password", type="password",
                                             key="signup_confirm", placeholder="Re-enter password")

            if st.button("Create Account →", use_container_width=True, key="signup_btn"):
                if not new_username or not new_email or not new_password:
                    st.error("Please fill in all fields.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    success = st.session_state.auth_db.create_user(
                        new_username, new_email, new_password, role="user"
                    )
                    if success:
                        st.success("✅ Account created! Please log in.")
                    else:
                        st.error("❌ Username or email already exists.")

        st.markdown("</div>", unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <p style="text-align:center; font-size:0.8rem; color:#9ca3af; margin-top:2rem;">
        © EDS — Environmental Data Solutions &nbsp;·&nbsp; Secure, role-based access
    </p>
    """, unsafe_allow_html=True)


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
        st.markdown("<div style='height: 0.25rem'></div>", unsafe_allow_html=True)

        if is_authenticated():
            user = get_current_user()
            role = user.get('role', 'user')
            role_icon = "👨‍💼" if role == "admin" else "👤"
            role_label = "Administrator" if role == "admin" else "User"
            initial = user['username'][0].upper() if user.get('username') else "?"

            st.markdown(f"""
            <div class="sidebar-user-card">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="
                        width: 38px; height: 38px; border-radius: 50%;
                        background: linear-gradient(135deg, #0f4c81 0%, #0b76ca 100%);
                        display: flex; align-items: center; justify-content: center;
                        font-size: 1rem; font-weight: 700; color: #fff; flex-shrink: 0;
                    ">{initial}</div>
                    <div>
                        <p class="sidebar-user-name">{user['username']}</p>
                        <p class="sidebar-user-role">{role_icon} {role_label}</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("🚪 Sign Out", use_container_width=True, key="logout_btn"):
                logout()

            # Navigation links
            st.markdown("<div style='height: 0.25rem'></div>", unsafe_allow_html=True)
            if is_admin():
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("⚙️ Admin", use_container_width=True, key="nav_admin"):
                        st.switch_page("pages/admin.py")
                with col2:
                    if st.button("👤 Profile", use_container_width=True, key="nav_profile"):
                        st.switch_page("pages/profile.py")
            else:
                if st.button("👤 My Profile", use_container_width=True, key="nav_profile_user"):
                    st.switch_page("pages/profile.py")
        else:
            st.markdown(
                '<p style="font-size:0.85rem;color:#9ca3af;margin:0;">Not signed in</p>',
                unsafe_allow_html=True,
            )


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

