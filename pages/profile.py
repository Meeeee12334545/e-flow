"""
User Profile Page

Streamlit page for users to view their profile and assigned devices.
"""

import streamlit as st
from database import FlowDatabase
from shared_styles import apply_styles
from streamlit_auth import init_auth_state, is_authenticated, is_admin, get_current_user


def render_profile_page():
    """Render user profile page."""
    apply_styles()

    if not is_authenticated():
        st.error("❌ You must be logged in")
        return

    user = get_current_user()
    role = user.get('role', 'user')
    role_label = "Administrator" if role == "admin" else "User"
    role_icon = "👨‍💼" if role == "admin" else "👤"
    initial = user['username'][0].upper() if user.get('username') else "?"

    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown("""
    <div class="page-header">
        <p class="page-header-title">👤 My Profile</p>
        <p class="page-header-sub">Account details and device access overview.</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Profile card ─────────────────────────────────────────────────────────
    active_badge = (
        '<span style="color:#4CAF50;font-weight:600;">● Active</span>'
        if user.get('active') else
        '<span style="color:#D93025;font-weight:600;">● Inactive</span>'
    )
    role_badge_cls = "admin" if role == "admin" else "user"

    st.markdown(f"""
    <div class="profile-card">
        <div class="profile-avatar">{initial}</div>
        <div class="profile-info">
            <p class="profile-name">{user['username']}</p>
            <span class="profile-role-badge {role_badge_cls}">{role_icon} {role_label}</span>
            <div class="profile-meta">
                <span class="profile-meta-item">
                    <strong>Email</strong><br>{user.get('email', '—')}
                </span>
                <span class="profile-meta-item">
                    <strong>Status</strong><br>{active_badge}
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Assigned Devices ─────────────────────────────────────────────────────
    st.markdown('<p class="section-title">📊 Assigned Devices</p>', unsafe_allow_html=True)

    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()

    if is_admin():
        all_devices = flow_db.get_devices()
        assigned_devices = all_devices
        st.caption("As an administrator you have access to all devices.")
    else:
        user_device_ids = auth_db.get_user_devices(user['user_id'])
        all_devices = flow_db.get_devices()
        assigned_devices = [d for d in all_devices if d['device_id'] in user_device_ids]

    if assigned_devices:
        st.caption(f"Access to **{len(assigned_devices)}** device(s).")
        for device in assigned_devices:
            col_info, col_action = st.columns([5, 1])
            with col_info:
                st.markdown(f"""
                <div class="device-row">
                    <div class="device-icon">📡</div>
                    <div>
                        <p class="device-name">{device['device_name']}</p>
                        <p class="device-meta">
                            ID: <code>{device['device_id']}</code>
                            &nbsp;·&nbsp;
                            {device.get('location') or 'Location not specified'}
                        </p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col_action:
                st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
                if st.button("View →", key=f"view_{device['device_id']}",
                             use_container_width=True):
                    st.session_state.selected_device = device['device_id']
                    st.switch_page("app.py")
    else:
        st.info("You don't have any devices assigned yet. Contact an administrator.")

    # ── Session info ──────────────────────────────────────────────────────────
    with st.expander("🔐 Session Information"):
        st.markdown(f"""
        <div style="font-size:0.88rem;line-height:1.8;color:#374151;">
            <strong>User ID:</strong> <code>{user['user_id']}</code><br>
            <strong>Session token:</strong> <code>{st.session_state.session_id[:20]}…</code>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_auth_state()
    render_profile_page()

