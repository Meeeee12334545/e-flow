"""
Admin Panel for User & Device Management

Streamlit page for administrators to:
1. Create new users
2. Select which sites (devices) users can see
3. Set GPS location for each device via interactive map
4. Assign the nearest BOM rain gauge to each device
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from auth import AuthDatabase
from database import FlowDatabase
from shared_styles import apply_styles
from streamlit_auth import init_auth_state, is_authenticated, is_admin, get_current_user

_ASSETS = Path(__file__).parent.parent / "assets"


def render_admin_panel():
    """Render the admin management panel."""
    apply_styles()
    st.logo(str(_ASSETS / "logo_wide.svg"), icon_image=str(_ASSETS / "logo_icon.svg"))

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
                lat = site.get("latitude")
                lon = site.get("longitude")
                loc_str = f"{lat:.4f}, {lon:.4f}" if (lat and lon) else "No coordinates"
                st.markdown(
                    f"**{site['device_name']}** &nbsp;·&nbsp; `{site['device_id']}` &nbsp;·&nbsp; "
                    f"{site.get('location') or 'No location'} &nbsp;·&nbsp; "
                    f"📍 {loc_str} &nbsp;·&nbsp; "
                    f"<span style='color:#6b7280;font-size:0.82rem;'>{url_display}</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Map Location & Rain Gauge ────────────────────────────────────────────
    st.markdown('<p class="section-title">📍 Map Location & Rain Gauge</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Set the GPS location for each flow meter and assign the nearest BOM rain gauge. "
        "Location is required to enable the Rainfall &amp; I/I analysis tab.</p>",
        unsafe_allow_html=True,
    )

    if not all_sites:
        st.warning("⚠️ No sites configured yet. Add a site first.")
    else:
        _site_map = {s["device_name"]: s for s in all_sites}
        _site_sel = st.selectbox(
            "Select site to configure:",
            options=list(_site_map.keys()),
            key="map_site_selector",
        )
        _site = _site_map[_site_sel]
        _device_id = _site["device_id"]
        _cur_lat = _site.get("latitude")
        _cur_lon = _site.get("longitude")

        # Default map centre — Australia if no coordinates set
        _map_lat = _cur_lat if _cur_lat else -25.0
        _map_lon = _cur_lon if _cur_lon else 133.0
        _zoom = 12 if _cur_lat else 4

        with st.expander("📍 Set Map Location", expanded=(_cur_lat is None)):
            st.markdown(
                "**Click on the map** to place a marker at the flow meter's location. "
                "Then press **Save Location** to store the coordinates.",
                unsafe_allow_html=False,
            )

            try:
                import folium
                from streamlit_folium import st_folium

                _m = folium.Map(location=[_map_lat, _map_lon], zoom_start=_zoom)
                if _cur_lat and _cur_lon:
                    folium.Marker(
                        location=[_cur_lat, _cur_lon],
                        tooltip=f"{_site['device_name']} (current location)",
                        icon=folium.Icon(color="green", icon="tint", prefix="fa"),
                    ).add_to(_m)

                _map_result = st_folium(_m, height=420, use_container_width=True, key=f"map_{_device_id}")

                _clicked_lat = None
                _clicked_lon = None
                if _map_result and _map_result.get("last_clicked"):
                    _clicked_lat = _map_result["last_clicked"]["lat"]
                    _clicked_lon = _map_result["last_clicked"]["lng"]

                _col_coords, _col_save = st.columns([3, 1])
                with _col_coords:
                    if _clicked_lat is not None:
                        st.info(
                            f"📍 Clicked: **{_clicked_lat:.5f}, {_clicked_lon:.5f}** "
                            "— press Save to confirm."
                        )
                    elif _cur_lat and _cur_lon:
                        st.success(
                            f"✅ Current location: **{_cur_lat:.5f}, {_cur_lon:.5f}**"
                        )
                    else:
                        st.caption("Click on the map above to select a location.")

                with _col_save:
                    if _clicked_lat is not None:
                        if st.button("💾 Save Location", type="primary", use_container_width=True):
                            ok = flow_db.update_device_location(_device_id, _clicked_lat, _clicked_lon)
                            if ok:
                                st.success("✅ Location saved!")
                                st.rerun()
                            else:
                                st.error("❌ Failed to save location.")

            except ImportError:
                st.warning(
                    "⚠️ Map component not available. Install `folium` and `streamlit-folium` to enable this feature."
                )
                # Fallback: manual coordinate entry
                with st.form("manual_coords_form"):
                    _m_lat = st.number_input("Latitude", value=float(_cur_lat or -28.0), format="%.5f")
                    _m_lon = st.number_input("Longitude", value=float(_cur_lon or 153.0), format="%.5f")
                    if st.form_submit_button("💾 Save Location"):
                        ok = flow_db.update_device_location(_device_id, _m_lat, _m_lon)
                        if ok:
                            st.success("✅ Location saved!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to save location.")

        # Rain gauge assignment — only enabled once coordinates are set
        _site_refreshed = next((s for s in flow_db.get_devices() if s["device_id"] == _device_id), _site)
        _has_coords = bool(_site_refreshed.get("latitude") and _site_refreshed.get("longitude"))

        with st.expander("🌧️ Assign Rain Gauge", expanded=False):
            if not _has_coords:
                st.info("ℹ️ Set a map location above before assigning a rain gauge.")
            else:
                _assigned = flow_db.get_device_rainfall_station(_device_id)
                if _assigned:
                    st.success(
                        f"✅ Currently assigned: **{_assigned.get('station_name', _assigned['station_id'])}** "
                        f"({_assigned['station_id']}) — "
                        f"{_assigned.get('state', '')} &nbsp;·&nbsp; "
                        f"{_site_refreshed['latitude']:.3f}, {_site_refreshed['longitude']:.3f}"
                    )

                if st.button("🔍 Find Nearest BOM Stations", key=f"find_stations_{_device_id}"):
                    with st.spinner("Searching BOM station catalogue…"):
                        from rainfall import search_bom_stations
                        _stations = search_bom_stations(
                            _site_refreshed["latitude"],
                            _site_refreshed["longitude"],
                            radius_km=150,
                            limit=8,
                        )
                        if _stations:
                            flow_db.save_rainfall_stations(_stations)
                        st.session_state[f"bom_stations_{_device_id}"] = _stations

                _found_stations = st.session_state.get(f"bom_stations_{_device_id}", [])

                if not _found_stations:
                    # Show cached stations from DB as fallback
                    _found_stations = flow_db.get_nearest_stations(
                        _site_refreshed["latitude"],
                        _site_refreshed["longitude"],
                        limit=8,
                    )

                if _found_stations:
                    st.markdown("**Select a station:**")
                    _station_labels = [
                        f"{s['station_name']} ({s['station_id']}) — {s.get('state', '')} — {s.get('distance_km', '?'):.1f} km away"
                        for s in _found_stations
                    ]
                    _sel_idx = st.radio(
                        "Nearest stations:",
                        options=range(len(_station_labels)),
                        format_func=lambda i: _station_labels[i],
                        key=f"station_radio_{_device_id}",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 Assign Station", type="primary", key=f"assign_station_{_device_id}"):
                        _chosen = _found_stations[_sel_idx]
                        flow_db.save_rainfall_stations([_chosen])
                        ok = flow_db.set_device_rainfall_station(_device_id, _chosen["station_id"])
                        if ok:
                            st.success(
                                f"✅ Assigned **{_chosen['station_name']}** ({_chosen['station_id']}) "
                                f"to {_site['device_name']}."
                            )
                            st.rerun()
                        else:
                            st.error("❌ Failed to assign station.")
                else:
                    st.info(
                        "No cached BOM stations found. Click **Find Nearest BOM Stations** to search, "
                        "or the system will use Open-Meteo coordinates-based data automatically."
                    )

                # Option to clear assignment
                if _assigned:
                    with st.expander("Remove current assignment", expanded=False):
                        if st.button("🗑️ Remove rain gauge assignment", key=f"remove_station_{_device_id}"):
                            # Delete the assignment row
                            try:
                                import sqlite3 as _sl
                                _conn = _sl.connect(flow_db.db_path, timeout=30)
                                _conn.execute(
                                    "DELETE FROM device_rainfall_stations WHERE device_id = ?",
                                    (_device_id,),
                                )
                                _conn.commit()
                                _conn.close()
                                st.success("✅ Assignment removed.")
                                st.rerun()
                            except Exception as _e:
                                st.error(f"❌ Could not remove: {_e}")

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

