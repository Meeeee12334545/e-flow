"""
User Profile Page

Streamlit page for users to view their profile and assigned devices.
"""

import base64
import streamlit as st
from pathlib import Path
from database import FlowDatabase
from shared_styles import apply_styles
from streamlit_auth import (
    init_auth_state, is_authenticated, is_admin, get_current_user,
    get_sidebar_logo_path, get_user_avatar_data_uri,
)

_ASSETS = Path(__file__).parent.parent / "assets"


def render_profile_page():
    """Render user profile page."""
    apply_styles()
    st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

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
        <p class="page-header-title">My Profile</p>
        <p class="page-header-sub">Account details, avatar and device access overview.</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Profile card ─────────────────────────────────────────────────────────
    active_badge = (
        '<span style="color:#4CAF50;font-weight:600;">● Active</span>'
        if user.get('active') else
        '<span style="color:#D93025;font-weight:600;">● Inactive</span>'
    )
    role_badge_cls = "admin" if role == "admin" else "user"

    avatar_uri = get_user_avatar_data_uri(user.get('user_id', 0))
    if avatar_uri:
        avatar_html = (
            f'<img src="{avatar_uri}" alt="avatar" '
            f'style="width:72px;height:72px;border-radius:50%;object-fit:cover;'
            f'box-shadow:0 2px 8px rgba(0,0,0,0.12);flex-shrink:0;" />'
        )
    else:
        avatar_html = f'<div class="profile-avatar">{initial}</div>'

    st.markdown(f"""
    <div class="profile-card">
        {avatar_html}
        <div class="profile-info">
            <p class="profile-name">{user['username']}</p>
            <span class="profile-role-badge {role_badge_cls}">{role_label}</span>
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

    # ── Avatar upload ─────────────────────────────────────────────────────────
    with st.expander("Upload / Change Avatar", expanded=False):
        st.caption("Upload a profile picture (PNG or JPG, max 2 MB). It will appear in the sidebar and your profile card.")
        uploaded_avatar = st.file_uploader(
            "Choose image",
            type=["png", "jpg", "jpeg"],
            key="avatar_uploader",
            label_visibility="collapsed",
        )
        if uploaded_avatar is not None:
            file_bytes = uploaded_avatar.read()
            if len(file_bytes) > 2 * 1024 * 1024:
                st.error("File is too large. Please upload an image under 2 MB.")
            else:
                logo_b64 = base64.b64encode(file_bytes).decode()
                mime_type = uploaded_avatar.type or "image/png"
                col_prev, col_save = st.columns([1, 2])
                with col_prev:
                    st.image(file_bytes, caption="Preview", width=120)
                with col_save:
                    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
                    if st.button("Save Avatar", type="primary", key="save_avatar_btn"):
                        try:
                            auth_db = st.session_state.auth_db
                            auth_db.save_user_logo(user['user_id'], logo_b64, mime_type)
                            st.success("Avatar updated. It will appear on your next page load.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not save avatar: {e}")

        if avatar_uri:
            if st.button("Remove Avatar", key="remove_avatar_btn"):
                try:
                    auth_db = st.session_state.auth_db
                    auth_db.save_user_logo(user['user_id'], "", "")
                    st.success("Avatar removed.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not remove avatar: {e}")

    # ── Assigned Devices ─────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Assigned Monitoring Sites</p>', unsafe_allow_html=True)

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
                    <div class="device-icon" style="background:#f0f4f2; font-size:0.9rem; font-weight:700; color:#3A7F5F; letter-spacing:0;">FLW</div>
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
    with st.expander("Session Information"):
        st.markdown(f"""
        <div style="font-size:0.88rem;line-height:1.8;color:#374151;">
            <strong>User ID:</strong> <code>{user['user_id']}</code><br>
            <strong>Session token:</strong> <code>{st.session_state.session_id[:20]}…</code>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_auth_state()
    render_profile_page()

