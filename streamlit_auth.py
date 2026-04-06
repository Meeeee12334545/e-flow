"""
Streamlit Authentication UI Module

Handles login/logout, session management, and auth state in Streamlit.
"""

import base64
import streamlit as st
from pathlib import Path
from auth import AuthDatabase
from shared_styles import apply_styles

_ASSETS = Path(__file__).parent / "assets"


def init_auth_state():
    """Initialize session state for authentication."""
    if 'auth_db' not in st.session_state:
        st.session_state.auth_db = AuthDatabase()

    if 'user' not in st.session_state:
        st.session_state.user = None

    if 'session_id' not in st.session_state:
        st.session_state.session_id = None


# ── Logo helpers ─────────────────────────────────────────────────────────────

def get_org_logo_data_uri() -> str | None:
    """Return the logo as a data URI for the current user, or None if not configured.

    Priority: user's personal company logo → org-wide logo → None.
    """
    auth_db = st.session_state.get('auth_db')
    if not auth_db:
        return None
    try:
        # Per-user company logo takes priority
        user = st.session_state.get('user')
        if user:
            user_logo = auth_db.get_user_company_logo(user['user_id'])
            if user_logo:
                return f"data:{user_logo['mime']};base64,{user_logo['b64']}"
        # Fall back to org-wide logo
        logo_b64 = auth_db.get_setting('org_logo_b64')
        logo_mime = auth_db.get_setting('org_logo_mime') or 'image/png'
        if logo_b64:
            return f"data:{logo_mime};base64,{logo_b64}"
    except Exception:
        pass
    return None


def get_admin_logo_data_uri() -> str | None:
    """Return the org-wide admin logo as a data URI, or None if not configured.

    Used on the login screen so the admin-configured logo is always shown,
    regardless of any per-user logo settings.  Falls back to a direct
    AuthDatabase instantiation when session state is not yet available (e.g.
    on the very first render of the login page).
    """
    auth_db = st.session_state.get('auth_db')
    if not auth_db:
        try:
            auth_db = AuthDatabase()
        except Exception:
            return None
    try:
        logo_b64 = auth_db.get_setting('org_logo_b64')
        logo_mime = auth_db.get_setting('org_logo_mime') or 'image/png'
        if logo_b64:
            return f"data:{logo_mime};base64,{logo_b64}"
    except Exception:
        pass
    return None


def get_sidebar_logo_path() -> str:
    """Return a file path suitable for st.logo(). Uses the current user's company logo if set,
    then falls back to the org-wide logo, then the EDS default."""
    import hashlib
    auth_db = st.session_state.get('auth_db')
    if auth_db:
        try:
            # Per-user company logo takes priority
            user = st.session_state.get('user')
            if user:
                user_logo = auth_db.get_user_company_logo(user['user_id'])
                if user_logo:
                    ext = 'svg' if 'svg' in user_logo['mime'] else ('jpg' if 'jpeg' in user_logo['mime'] else 'png')
                    content_hash = hashlib.sha256(user_logo['b64'].encode()).hexdigest()[:16]
                    tmp_path = Path('/tmp') / f'eflow_user_logo_{user["user_id"]}_{content_hash}.{ext}'
                    if not tmp_path.exists():
                        tmp_path.write_bytes(base64.b64decode(user_logo['b64']))
                    return str(tmp_path)
            # Fall back to org-wide logo
            logo_b64 = auth_db.get_setting('org_logo_b64')
            logo_mime = auth_db.get_setting('org_logo_mime') or 'image/png'
            if logo_b64:
                ext = 'svg' if 'svg' in logo_mime else ('jpg' if 'jpeg' in logo_mime else 'png')
                content_hash = hashlib.sha256(logo_b64.encode()).hexdigest()[:16]
                tmp_path = Path('/tmp') / f'eflow_org_logo_{content_hash}.{ext}'
                if not tmp_path.exists():
                    tmp_path.write_bytes(base64.b64decode(logo_b64))
                return str(tmp_path)
        except Exception:
            pass
    return str(_ASSETS / "logo_wide.svg")


def get_user_avatar_data_uri(user_id: int) -> str | None:
    """Return the user's avatar as a data URI, or None if not set."""
    auth_db = st.session_state.get('auth_db')
    if not auth_db:
        return None
    try:
        logo = auth_db.get_user_logo(user_id)
        if logo:
            return f"data:{logo['mime']};base64,{logo['b64']}"
    except Exception:
        pass
    return None


def login_page():
    """Display a polished, branded login page."""
    apply_styles()

    # Always use the org-wide admin logo on the sign-in screen
    org_logo_uri = get_admin_logo_data_uri()
    if org_logo_uri:
        _logo_img_src = org_logo_uri
        _logo_style = "max-height:72px; max-width:280px; display:inline-block; margin-bottom: 0.75rem; object-fit: contain;"
    else:
        _logo_b64 = base64.b64encode((_ASSETS / "logo_wide.svg").read_bytes()).decode()
        _logo_img_src = f"data:image/svg+xml;base64,{_logo_b64}"
        _logo_style = "height:72px; display:inline-block; margin-bottom: 0.75rem;"

    st.markdown(f"""
    <div style="text-align: center; padding: 2.5rem 1rem 1.5rem;">
        <img src="{_logo_img_src}"
             alt="Organisation Logo"
             style="{_logo_style}"/>
        <p style="
            font-size: 0.92rem !important; color: #6b7280 !important;
            margin: 0.3rem 0 0 0 !important;
        ">EDS HydroSense — See what your network is really doing.</p>
    </div>
    """, unsafe_allow_html=True)

    # Centered card
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style="
            background: #ffffff; border: 1px solid #D9D9D9;
            border-radius: 16px; padding: 36px 40px;
            box-shadow: 0 6px 24px rgba(58,127,95,0.10);
        ">
        """, unsafe_allow_html=True)

        tab1, = st.tabs(["Login"])

        with tab1:
            st.markdown(
                '<p style="font-size:1.1rem;font-weight:700;color:#4A4A4A;margin:0 0 1rem 0;">'
                'Welcome back</p>',
                unsafe_allow_html=True,
            )
            username = st.text_input("Username", key="login_username", placeholder="your_username")
            password = st.text_input("Password", type="password", key="login_password",
                                     placeholder="••••••••")

            if st.button("Login →", width="stretch", key="login_btn"):
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

        st.markdown("</div>", unsafe_allow_html=True)

    # Footer
    st.markdown("""
    <p style="text-align:center; font-size:0.8rem; color:#9ca3af; margin-top:2rem;">
        © EDS — Environmental Data Services &nbsp;·&nbsp; Secure, role-based access
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
            role_label = "Administrator" if role == "admin" else "User"
            initial = user['username'][0].upper() if user.get('username') else "?"

            # Show avatar if uploaded, otherwise show initial letter
            avatar_uri = get_user_avatar_data_uri(user.get('user_id', 0))
            if avatar_uri:
                avatar_html = (
                    f'<img src="{avatar_uri}" alt="avatar" '
                    f'style="width:38px;height:38px;border-radius:50%;object-fit:cover;flex-shrink:0;" />'
                )
            else:
                avatar_html = (
                    f'<div style="width:38px;height:38px;border-radius:50%;background:#3A7F5F;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'font-size:1rem;font-weight:700;color:#fff;flex-shrink:0;">{initial}</div>'
                )

            st.markdown(f"""
            <div class="sidebar-user-card">
                <div style="display: flex; align-items: center; gap: 10px;">
                    {avatar_html}
                    <div>
                        <p class="sidebar-user-name">{user['username']}</p>
                        <p class="sidebar-user-role">{role_label}</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Sign Out", width="stretch", key="logout_btn"):
                logout()

            # Navigation links
            st.markdown("<div style='height: 0.25rem'></div>", unsafe_allow_html=True)
            if is_admin():
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Admin", width="stretch", key="nav_admin"):
                        st.switch_page("pages/admin.py")
                with col2:
                    if st.button("Profile", width="stretch", key="nav_profile"):
                        st.switch_page("pages/profile.py")
            else:
                if st.button("My Profile", width="stretch", key="nav_profile_user"):
                    st.switch_page("pages/profile.py")
            if st.button("Reports", width="stretch", key="nav_reports"):
                st.switch_page("pages/reports.py")
            if st.button("FlowSense™ Analysis", width="stretch", key="nav_intelligence"):
                st.switch_page("pages/intelligence.py")
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

