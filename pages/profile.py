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
    get_sidebar_logo_path, get_user_avatar_data_uri, get_org_logo_data_uri,
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

    # ── Company Logo ──────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Company Logo</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Upload your own company logo. It will appear in the sidebar and header <em>only for your account</em>. "
        "If not set, the organisation logo configured by your administrator will be used.</p>",
        unsafe_allow_html=True,
    )

    auth_db = st.session_state.auth_db
    current_user_logo = auth_db.get_user_company_logo(user['user_id'])
    org_logo_uri = get_org_logo_data_uri()

    logo_col1, logo_col2 = st.columns([2, 1])
    with logo_col1:
        uploaded_logo = st.file_uploader(
            "Upload company logo (PNG, JPG or SVG — max 2 MB)",
            type=["png", "jpg", "jpeg", "svg"],
            key="user_company_logo_uploader",
            label_visibility="collapsed",
        )
        if uploaded_logo is not None:
            file_bytes = uploaded_logo.read()
            if len(file_bytes) > 2 * 1024 * 1024:
                st.error("File is too large. Please upload an image under 2 MB.")
            else:
                logo_b64 = base64.b64encode(file_bytes).decode()
                mime_type = uploaded_logo.type or "image/png"
                st.image(file_bytes, caption="Preview", width=200)
                if st.button("Save Company Logo", type="primary", key="save_user_company_logo_btn"):
                    try:
                        auth_db.save_user_company_logo(user['user_id'], logo_b64, mime_type)
                        st.success("Company logo saved. It will appear on your next page load.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save logo: {e}")

    with logo_col2:
        if current_user_logo:
            st.markdown(
                "<p style='font-size:0.82rem;color:#6b7280;margin-bottom:0.4rem;'>Your current logo</p>",
                unsafe_allow_html=True,
            )
            st.image(
                base64.b64decode(current_user_logo['b64']),
                width=160,
            )
            if st.button("Remove (use org default)", key="remove_user_company_logo_btn"):
                try:
                    auth_db.save_user_company_logo(user['user_id'], "", "")
                    st.success("Personal logo removed. Organisation logo will be used.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not remove logo: {e}")
        elif org_logo_uri:
            st.markdown(
                "<p style='font-size:0.82rem;color:#6b7280;margin-bottom:0.4rem;'>"
                "Using organisation logo (default)</p>",
                unsafe_allow_html=True,
            )
            st.image(org_logo_uri, width=160)
        else:
            st.markdown(
                "<p style='color:#9ca3af;font-size:0.88rem;margin:0;'>No custom logo set<br>"
                "<span style='font-size:0.82rem;'>Default EDS branding will be used.</span></p>",
                unsafe_allow_html=True,
            )

    # ── Assigned Devices ─────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Assigned Monitoring Sites</p>', unsafe_allow_html=True)

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
                             width="stretch"):
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

