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
from shared_styles import apply_styles
from streamlit_auth import init_auth_state, is_authenticated, is_admin, get_current_user


def render_admin_panel():
    """Render the admin management panel."""
    apply_styles()

    if not is_authenticated():
        st.error("❌ You must be logged in")
        return

    if not is_admin():
        st.error("❌ Admin access required")
        return

    # ── Page header ─────────────────────────────────────────────────────────
    st.markdown("""
    <div class="page-header">
        <p class="page-header-title">⚙️ Admin Panel</p>
        <p class="page-header-sub">Manage users, monitoring sites, and control which sites each user can access.</p>
    </div>
    """, unsafe_allow_html=True)

    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()

    # ── Add New Monitoring Site ──────────────────────────────────────────────
    st.markdown('<p class="section-title">🌐 Add New Monitoring Site</p>', unsafe_allow_html=True)

    col_site_form, col_site_hint = st.columns([3, 2])

    with col_site_form:
        with st.form("add_site_form"):
            new_site_name = st.text_input("Site Name", placeholder="e.g. Main Inflow Lismore STP")
            new_site_id = st.text_input(
                "Site ID / Code",
                placeholder="e.g. FIT200",
                help="Unique identifier used internally. Letters, numbers and underscores only.",
            )
            new_site_location = st.text_input("Location", placeholder="e.g. Lismore")
            new_site_url = st.text_input(
                "Dashboard URL",
                placeholder="https://mp.usriot.com/draw/show.html?...",
                help="Full URL to the USRIOT unit dashboard for this site. The data selectors are the same for all sites.",
            )

            if st.form_submit_button("Add Site →", use_container_width=True):
                if not new_site_name or not new_site_id or not new_site_url:
                    st.error("❌ Site Name, Site ID and Dashboard URL are required.")
                elif not new_site_url.startswith("http"):
                    st.error("❌ Dashboard URL must start with http:// or https://")
                else:
                    import re as _re
                    # Normalise site ID — uppercase, spaces → underscores
                    clean_id = new_site_id.strip().upper().replace(" ", "_")
                    if not _re.match(r'^[A-Z0-9_]+$', clean_id):
                        st.error("❌ Site ID may only contain letters, numbers and underscores.")
                    else:
                        existing = flow_db.get_devices()
                        existing_ids = {d["device_id"] for d in existing}
                        if clean_id in existing_ids:
                            st.error(f"❌ A site with ID '{clean_id}' already exists.")
                        else:
                            flow_db.add_device(
                                device_id=clean_id,
                                device_name=new_site_name.strip(),
                                location=new_site_location.strip() or None,
                                dashboard_url=new_site_url.strip(),
                            )
                            st.success(f"✅ Site '{new_site_name.strip()}' (ID: {clean_id}) added successfully!")
                            st.info("The monitor service will begin collecting data from this site on its next cycle.")
                            st.rerun()

    with col_site_hint:
        st.markdown("""
        <div class="info-box" style="margin-top: 0.25rem;">
            <strong>About dashboard URLs</strong><br>
            <span style="color: #6b7280;">
                All USRIOT sites share the same data selectors — only the URL differs per site.<br><br>
                After adding a site, assign it to users in the section below so they can view it.
            </span>
        </div>
        """, unsafe_allow_html=True)

    # ── Current Sites Overview ───────────────────────────────────────────────
    all_sites = flow_db.get_devices()
    if all_sites:
        with st.expander(f"📋 All Configured Sites ({len(all_sites)})", expanded=False):
            for site in all_sites:
                url_display = site.get("dashboard_url") or "—"
                if len(url_display) > 60:
                    url_display = url_display[:60] + "…"
                st.markdown(
                    f"**{site['device_name']}** &nbsp;·&nbsp; `{site['device_id']}` &nbsp;·&nbsp; "
                    f"{site.get('location') or 'No location'} &nbsp;·&nbsp; "
                    f"<span style='color:#6b7280;font-size:0.82rem;'>{url_display}</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Create New User ──────────────────────────────────────────────────────
    st.markdown('<p class="section-title">➕ Create New User</p>', unsafe_allow_html=True)

    col_form, col_hint = st.columns([3, 2])

    with col_form:
        with st.form("create_user_form"):
            new_username = st.text_input("Username", placeholder="john_operator")
            new_email = st.text_input("Email", placeholder="john@example.com")
            new_password = st.text_input("Password", type="password",
                                         help="Minimum 8 characters")

            if st.form_submit_button("Create User →", use_container_width=True):
                if not new_username or not new_email or not new_password:
                    st.error("❌ Please fill in all fields.")
                elif len(new_password) < 8:
                    st.error("❌ Password must be at least 8 characters.")
                else:
                    success = auth_db.create_user(new_username, new_email, new_password,
                                                  role="user")
                    if success:
                        st.success(f"✅ User '{new_username}' created successfully!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ Failed to create user (username or email already exists).")

    with col_hint:
        st.markdown("""
        <div class="info-box" style="margin-top: 0.25rem;">
            <strong>New user defaults</strong><br>
            <span style="color: #6b7280;">
                Role: <strong style="color: #3A7F5F;">User</strong> — can only view assigned sites.<br>
                Sites: None — assign them in the section below.
            </span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Assign Sites to Users ────────────────────────────────────────────────
    st.markdown('<p class="section-title">📍 Assign Sites to Users</p>', unsafe_allow_html=True)

    # Single batch query: users + their assigned device IDs/names in one round-trip
    users = auth_db.list_users_with_devices()
    devices = flow_db.get_devices()
    # Build a lookup dict for O(1) device resolution by ID
    device_map = {d['device_id']: d for d in devices}

    if not users:
        st.warning("⚠️ No users available. Create a user first.")
    elif not devices:
        st.warning("⚠️ No devices / sites available.")
    else:
        regular_users = [u for u in users if u['role'] == 'user']

        if not regular_users:
            st.info("ℹ️ All users are admins. Create a regular user to assign sites.")
        else:
            col_picker, col_info = st.columns([2, 1])

            with col_picker:
                selected_username = st.selectbox(
                    "Select user to manage:",
                    options=[u['username'] for u in regular_users],
                    key="user_selector",
                )
                selected_user = next(
                    (u for u in regular_users if u['username'] == selected_username), None
                )

            if selected_user:
                # Device IDs already fetched in the batch query — no extra DB call
                user_device_ids = selected_user['device_ids']

                with col_info:
                    st.markdown(f"""
                    <div class="info-box" style="margin-top: 1.65rem;">
                        <strong>{selected_user['username']}</strong><br>
                        <span style="color: #6b7280;">{len(user_device_ids)} site(s) currently assigned</span>
                    </div>
                    """, unsafe_allow_html=True)

                col_avail, col_assigned = st.columns(2)

                with col_avail:
                    st.markdown(
                        '<p style="font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;">'
                        '📭 Available Sites</p>',
                        unsafe_allow_html=True,
                    )
                    unassigned = [d for d in devices if d['device_id'] not in user_device_ids]
                    if unassigned:
                        for device in unassigned:
                            if st.button(
                                f"＋ {device['device_name']}",
                                key=f"add_{selected_user['user_id']}_{device['device_id']}",
                                use_container_width=True,
                            ):
                                auth_db.assign_device_to_user(
                                    selected_user['user_id'], device['device_id']
                                )
                                st.success(f"✅ Added {device['device_name']}")
                                st.rerun()
                    else:
                        st.info("✅ All sites already assigned.")

                with col_assigned:
                    st.markdown(
                        '<p style="font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;">'
                        '✅ Assigned Sites</p>',
                        unsafe_allow_html=True,
                    )
                    if user_device_ids:
                        for device_id in user_device_ids:
                            device = device_map.get(device_id)
                            if device:
                                col_name, col_remove = st.columns([4, 1])
                                with col_name:
                                    st.markdown(
                                        f'<p style="margin:0.45rem 0;font-size:0.9rem;">'
                                        f'📍 {device["device_name"]}</p>',
                                        unsafe_allow_html=True,
                                    )
                                with col_remove:
                                    if st.button(
                                        "✕",
                                        key=f"remove_{selected_user['user_id']}_{device_id}",
                                        help=f"Remove {device['device_name']}",
                                    ):
                                        auth_db.unassign_device_from_user(
                                            selected_user['user_id'], device_id
                                        )
                                        st.toast(f"Removed {device['device_name']}", icon="✅")
                                        st.rerun()
                    else:
                        st.info("No sites assigned yet.")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── All Users Overview ───────────────────────────────────────────────────
    st.markdown('<p class="section-title">📋 All Users Overview</p>', unsafe_allow_html=True)

    if not users:
        st.info("No users to display.")
    else:
        regular_users = [u for u in users if u['role'] == 'user']
        if regular_users:
            # device_ids and device_names already available from the batch query
            summary = [
                {
                    'Username': u['username'],
                    'Email': u['email'],
                    'Sites Assigned': len(u['device_ids']),
                    'Sites': ', '.join(u['device_names']) if u['device_names'] else '—',
                }
                for u in regular_users
            ]
            st.dataframe(
                pd.DataFrame(summary),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No regular users to display.")


if __name__ == "__main__":
    init_auth_state()
    render_admin_panel()

