"""
Admin Panel for User & Device Management

Streamlit page for administrators to:
1. Create new users
2. Select which sites (devices) users can see
3. Set GPS location for each device via interactive map
4. Assign the nearest BOM rain gauge to each device
"""

import base64
import streamlit as st
import pandas as pd
from pathlib import Path
from auth import AuthDatabase
from database import FlowDatabase
from shared_styles import apply_styles, render_footer
from streamlit_auth import init_auth_state, is_authenticated, is_admin, get_current_user, get_sidebar_logo_path, log_page_view

_ASSETS = Path(__file__).parent.parent / "assets"


def render_admin_panel():
    """Render the admin management panel."""
    apply_styles()
    st.logo(get_sidebar_logo_path(), icon_image=str(_ASSETS / "logo_icon.svg"))

    if not is_authenticated():
        st.error("You must be logged in")
        st.stop()
        return

    if not is_admin():
        st.switch_page("app.py")
        return

    log_page_view("Admin Panel")

    # ── Page header ─────────────────────────────────────────────────────────
    st.markdown("""
    <div class="page-header">
        <p class="page-header-title">Admin Panel</p>
        <p class="page-header-sub">Manage users, monitoring sites, and control which sites each user can access.</p>
    </div>
    """, unsafe_allow_html=True)

    auth_db = st.session_state.auth_db
    flow_db = FlowDatabase()

    # ── Organisation Branding ────────────────────────────────────────────────
    st.markdown('<p class="section-title">Organisation Branding</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Upload your organisation's logo. It replaces the default EDS logo in the application "
        "header, login page, sidebar and PDF reports.</p>",
        unsafe_allow_html=True,
    )

    branding_col1, branding_col2 = st.columns([2, 1])

    with branding_col1:
        uploaded_logo = st.file_uploader(
            "Upload organisation logo (PNG, JPG or SVG — max 2 MB)",
            type=["png", "jpg", "jpeg", "svg"],
            key="org_logo_uploader",
        )
        if uploaded_logo is not None:
            file_bytes = uploaded_logo.read()
            if len(file_bytes) > 2 * 1024 * 1024:
                st.error("File is too large. Please upload an image under 2 MB.")
            else:
                org_logo_b64 = base64.b64encode(file_bytes).decode()
                mime_type = uploaded_logo.type or "image/png"
                branding_save_col, branding_preview_col = st.columns([1, 1])
                with branding_preview_col:
                    st.image(file_bytes, caption="Preview", width="stretch")
                with branding_save_col:
                    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
                    if st.button("Save Organisation Logo", type="primary", key="save_org_logo_btn"):
                        try:
                            auth_db.save_setting('org_logo_b64', org_logo_b64)
                            auth_db.save_setting('org_logo_mime', mime_type)
                            st.success("Organisation logo saved. It will appear on the next page load.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not save logo: {e}")

    with branding_col2:
        current_logo_b64 = auth_db.get_setting('org_logo_b64')
        current_logo_mime = auth_db.get_setting('org_logo_mime') or 'image/png'
        if current_logo_b64:
            st.markdown(
                "<p style='font-size:0.82rem;font-weight:600;color:#6b7280;margin-bottom:0.5rem;'>"
                "CURRENT LOGO</p>",
                unsafe_allow_html=True,
            )
            st.image(
                base64.b64decode(current_logo_b64),
                caption=None,
                width="stretch",
            )
            if st.button("Remove Logo (restore default)", key="remove_org_logo_btn"):
                auth_db.delete_setting('org_logo_b64')
                auth_db.delete_setting('org_logo_mime')
                st.success("Logo removed. Default EDS branding restored.")
                st.rerun()
        else:
            st.markdown(
                "<div style='background:#f9faf9;border:1px dashed #D9D9D9;border-radius:8px;"
                "padding:24px;text-align:center;'>"
                "<p style='color:#9ca3af;font-size:0.88rem;margin:0;'>No custom logo set<br>"
                "<span style='font-size:0.8rem;'>Default EDS branding is active</span></p>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    _FREQ_OPTIONS = {
        "30 seconds": 30,
        "1 minute": 60,
        "2 minutes": 120,
        "5 minutes": 300,
    }

    # ── Per-Site Collection Frequency ─────────────────────────────────────────
    st.markdown('<p class="section-title">Per-Site Collection Frequency</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Set the collection interval for each individual monitoring site. "
        "Changes take effect on the next collection cycle.</p>",
        unsafe_allow_html=True,
    )

    _all_sites_freq = flow_db.get_devices()
    if not _all_sites_freq:
        st.info("No monitoring sites configured yet. Add a site first.")
    else:
        _FREQ_OPTIONS_WITH_DEFAULT = {"Use default": None, **_FREQ_OPTIONS}

        for _fs in _all_sites_freq:
            _fs_id = _fs["device_id"]
            _fs_name = _fs["device_name"]
            _fs_interval = _fs.get("poll_interval")

            # Map current value to a label
            _fs_current_label = next(
                (lbl for lbl, val in _FREQ_OPTIONS.items() if val == _fs_interval),
                "Use default",
            )

            _fcol_name, _fcol_radio, _fcol_btn = st.columns([2, 3, 1])
            with _fcol_name:
                st.markdown(
                    f"<div style='padding-top:0.5rem;'>"
                    f"<span style='font-weight:600;color:#4A4A4A;'>{_fs_name}</span><br>"
                    f"<code style='font-size:0.78rem;color:#6b7280;'>{_fs_id}</code>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with _fcol_radio:
                _fs_selected = st.radio(
                    f"Frequency for {_fs_id}",
                    options=list(_FREQ_OPTIONS_WITH_DEFAULT.keys()),
                    index=list(_FREQ_OPTIONS_WITH_DEFAULT.keys()).index(_fs_current_label),
                    horizontal=True,
                    key=f"freq_radio_{_fs_id}",
                    label_visibility="collapsed",
                )
            with _fcol_btn:
                if st.button("Save", key=f"freq_save_{_fs_id}", type="primary"):
                    _new_val = _FREQ_OPTIONS_WITH_DEFAULT[_fs_selected]
                    ok = flow_db.set_device_poll_interval(_fs_id, _new_val)
                    if ok:
                        _label_str = _fs_selected if _fs_selected != "Use default" else "default"
                        st.success(f"Saved — {_fs_name}: {_label_str}")
                        st.rerun()
                    else:
                        st.error("Failed to save.")

            st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Add New Monitoring Site ──────────────────────────────────────────────
    st.markdown('<p class="section-title">Add New Monitoring Site</p>', unsafe_allow_html=True)

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

            if st.form_submit_button("Add Site →", width='stretch'):
                if not new_site_name or not new_site_id or not new_site_url:
                    st.error("Site Name, Site ID and Dashboard URL are required.")
                elif not new_site_url.startswith("http"):
                    st.error("Dashboard URL must start with http:// or https://")
                else:
                    import re as _re
                    # Normalise site ID — uppercase, spaces → underscores
                    clean_id = new_site_id.strip().upper().replace(" ", "_")
                    if not _re.match(r'^[A-Z0-9_]+$', clean_id):
                        st.error("Site ID may only contain letters, numbers and underscores.")
                    else:
                        existing = flow_db.get_devices()
                        existing_ids = {d["device_id"] for d in existing}
                        if clean_id in existing_ids:
                            st.error(f"A site with ID '{clean_id}' already exists.")
                        else:
                            flow_db.add_device(
                                device_id=clean_id,
                                device_name=new_site_name.strip(),
                                location=new_site_location.strip() or None,
                                dashboard_url=new_site_url.strip(),
                            )
                            st.success(f"Site '{new_site_name.strip()}' (ID: {clean_id}) added successfully!")
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
        with st.expander(f"All Configured Sites ({len(all_sites)})", expanded=False):
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
                    f"{loc_str} &nbsp;·&nbsp; "
                    f"<span style='color:#6b7280;font-size:0.82rem;'>{url_display}</span>",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Edit Monitoring Site ──────────────────────────────────────────────────
    st.markdown('<p class="section-title">Edit Monitoring Site</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Update the name, location or dashboard URL for an existing monitoring site.</p>",
        unsafe_allow_html=True,
    )

    # Refresh after potential adds above
    _all_sites_for_edit = flow_db.get_devices()
    if not _all_sites_for_edit:
        st.info("No sites configured yet. Add a site first.")
    else:
        _edit_site_map = {s["device_name"]: s for s in _all_sites_for_edit}
        _edit_col, _edit_hint_col = st.columns([3, 2])

        with _edit_col:
            _edit_sel = st.selectbox(
                "Select site to edit:",
                options=list(_edit_site_map.keys()),
                key="edit_site_selector",
            )
            _edit_site = _edit_site_map[_edit_sel]

            with st.form("edit_site_form"):
                _edit_name = st.text_input(
                    "Site Name",
                    value=_edit_site.get("device_name", ""),
                    key="edit_site_name",
                )
                _edit_location = st.text_input(
                    "Location",
                    value=_edit_site.get("location") or "",
                    key="edit_site_location",
                )
                _edit_url = st.text_input(
                    "Dashboard URL",
                    value=_edit_site.get("dashboard_url") or "",
                    help="Full URL to the USRIOT unit dashboard for this site.",
                    key="edit_site_url",
                )
                if st.form_submit_button("Save Changes →", width="stretch"):
                    if not _edit_name.strip():
                        st.error("Site Name cannot be empty.")
                    elif _edit_url.strip() and not _edit_url.strip().startswith("http"):
                        st.error("Dashboard URL must start with http:// or https://")
                    else:
                        ok = flow_db.update_device(
                            device_id=_edit_site["device_id"],
                            device_name=_edit_name.strip(),
                            location=_edit_location.strip() or None,
                            dashboard_url=_edit_url.strip() or None,
                        )
                        if ok:
                            st.success(f"Site '{_edit_name.strip()}' updated successfully.")
                            st.rerun()
                        else:
                            st.error("Failed to update site.")

        with _edit_hint_col:
            st.markdown(f"""
            <div class="info-box" style="margin-top: 0.25rem;">
                <strong>Editing site:</strong> <code>{_edit_site['device_id']}</code><br>
                <span style="color: #6b7280;">
                    The Site ID (<code>{_edit_site['device_id']}</code>) cannot be changed
                    as it is used to link collected measurements.<br><br>
                    You can update the name, physical location description,
                    and the USRIOT dashboard URL at any time.
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Delete Monitoring Site ────────────────────────────────────────────────
    st.markdown('<p class="section-title">Delete Monitoring Site</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Permanently remove a site and all its collected measurements, anomaly flags, "
        "reports and rain gauge assignments.</p>",
        unsafe_allow_html=True,
    )

    if not all_sites:
        st.info("No sites configured yet.")
    else:
        col_del_site, col_del_site_hint = st.columns([3, 2])

        with col_del_site:
            _del_site_map = {s["device_name"]: s for s in all_sites}
            _del_site_sel = st.selectbox(
                "Select site to delete:",
                options=list(_del_site_map.keys()),
                key="delete_site_selector",
            )
            _del_site = _del_site_map[_del_site_sel]
            _confirm_site = st.checkbox(
                f"I understand this will permanently delete **{_del_site['device_name']}** "
                "and all its data. This cannot be undone.",
                key="delete_site_confirm",
            )
            if st.button("Delete Site", disabled=not _confirm_site, key="delete_site_btn"):
                ok = flow_db.delete_device(_del_site["device_id"])
                if ok:
                    st.success(f"Site '{_del_site['device_name']}' and all its data have been deleted.")
                    st.rerun()
                else:
                    st.error("Failed to delete site.")

        with col_del_site_hint:
            st.markdown("""
            <div class="info-box" style="margin-top: 0.25rem; border-left: 4px solid #D93025;">
                <strong style="color: #D93025;">Destructive action</strong><br>
                <span style="color: #6b7280;">
                    Deleting a site removes all its flow measurements, anomaly flags,
                    reports and rain gauge assignments permanently.<br><br>
                    This action <strong>cannot be undone</strong>.
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Map Location & Rain Gauge ────────────────────────────────────────────
    st.markdown('<p class="section-title">Map Location & Rain Gauge</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Set the GPS location for each flow meter and assign the nearest BOM rain gauge. "
        "Location is required to enable the Rainfall &amp; I/I analysis tab.</p>",
        unsafe_allow_html=True,
    )

    if not all_sites:
        st.warning("No sites configured yet. Add a site first.")
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

        with st.expander("Set Map Location", expanded=(_cur_lat is None)):
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
                            f"Clicked: **{_clicked_lat:.5f}, {_clicked_lon:.5f}** "
                            "— press Save to confirm."
                        )
                    elif _cur_lat and _cur_lon:
                        st.success(
                            f"Current location: **{_cur_lat:.5f}, {_cur_lon:.5f}**"
                        )
                    else:
                        st.caption("Click on the map above to select a location.")

                with _col_save:
                    if _clicked_lat is not None:
                        if st.button("Save Location", type="primary", width='stretch'):
                            ok = flow_db.update_device_location(_device_id, _clicked_lat, _clicked_lon)
                            if ok:
                                st.success("Location saved!")
                                st.rerun()
                            else:
                                st.error("Failed to save location.")

            except ImportError:
                st.warning(
                    "Map component not available. Install `folium` and `streamlit-folium` to enable this feature."
                )
                # Fallback: manual coordinate entry
                with st.form("manual_coords_form"):
                    _m_lat = st.number_input("Latitude", value=float(_cur_lat or -28.0), format="%.5f")
                    _m_lon = st.number_input("Longitude", value=float(_cur_lon or 153.0), format="%.5f")
                    if st.form_submit_button("Save Location"):
                        ok = flow_db.update_device_location(_device_id, _m_lat, _m_lon)
                        if ok:
                            st.success("Location saved!")
                            st.rerun()
                        else:
                            st.error("Failed to save location.")

        # Rain gauge assignment — only enabled once coordinates are set
        _site_refreshed = next((s for s in flow_db.get_devices() if s["device_id"] == _device_id), _site)
        _has_coords = bool(_site_refreshed.get("latitude") and _site_refreshed.get("longitude"))

        with st.expander("Assign Rain Gauge", expanded=False):
            if not _has_coords:
                st.info("Set a map location above before assigning a rain gauge.")
            else:
                _assigned = flow_db.get_device_rainfall_station(_device_id)
                if _assigned:
                    st.success(
                        f"Currently assigned: **{_assigned.get('station_name', _assigned['station_id'])}** "
                        f"({_assigned['station_id']}) — "
                        f"{_assigned.get('state', '')} &nbsp;·&nbsp; "
                        f"{_site_refreshed['latitude']:.3f}, {_site_refreshed['longitude']:.3f}"
                    )

                if st.button("Find Nearest BOM Stations", key=f"find_stations_{_device_id}"):
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
                    if st.button("Assign Station", type="primary", key=f"assign_station_{_device_id}"):
                        _chosen = _found_stations[_sel_idx]
                        flow_db.save_rainfall_stations([_chosen])
                        ok = flow_db.set_device_rainfall_station(_device_id, _chosen["station_id"])
                        if ok:
                            st.success(
                                f"Assigned **{_chosen['station_name']}** ({_chosen['station_id']}) "
                                f"to {_site['device_name']}."
                            )
                            st.rerun()
                        else:
                            st.error("Failed to assign station.")
                else:
                    st.info(
                        "No cached BOM stations found. Click **Find Nearest BOM Stations** to search, "
                        "or the system will use Open-Meteo coordinates-based data automatically."
                    )

                # Option to clear assignment
                if _assigned:
                    with st.expander("Remove current assignment", expanded=False):
                        if st.button("Remove rain gauge assignment", key=f"remove_station_{_device_id}"):
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
                                st.success("Assignment removed.")
                                st.rerun()
                            except Exception as _e:
                                st.error(f"Could not remove: {_e}")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Create New User ──────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Create New User</p>', unsafe_allow_html=True)

    col_form, col_hint = st.columns([3, 2])

    with col_form:
        with st.form("create_user_form"):
            new_username = st.text_input("Username", placeholder="john_operator")
            new_email = st.text_input("Email", placeholder="john@example.com")
            new_password = st.text_input("Password", type="password",
                                         help="Minimum 8 characters")

            if st.form_submit_button("Create User →", width='stretch'):
                if not new_username or not new_email or not new_password:
                    st.error("Please fill in all fields.")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    success = auth_db.create_user(new_username, new_email, new_password,
                                                  role="user")
                    if success:
                        st.success(f"User '{new_username}' created successfully!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("Failed to create user (username or email already exists).")

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

    # ── Delete User ──────────────────────────────────────────────────────────
    st.markdown('<p class="section-title">Delete User</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Permanently remove a user account and all their session data.</p>",
        unsafe_allow_html=True,
    )

    _current_user = get_current_user()
    _all_users_for_delete = auth_db.list_users_with_devices()
    # Prevent the currently logged-in admin from deleting their own account
    _deletable_users = [u for u in _all_users_for_delete if u['username'] != _current_user.get('username')]

    if not _deletable_users:
        st.info("No other users to delete.")
    else:
        col_del_user, col_del_user_hint = st.columns([3, 2])

        with col_del_user:
            _del_user_sel = st.selectbox(
                "Select user to delete:",
                options=[u['username'] for u in _deletable_users],
                format_func=lambda u: f"{u}  ({next(x['role'] for x in _deletable_users if x['username'] == u)})",
                key="delete_user_selector",
            )
            _del_user = next(u for u in _deletable_users if u['username'] == _del_user_sel)
            _confirm_user = st.checkbox(
                f"I understand this will permanently delete **{_del_user['username']}** "
                "and all their session data. This cannot be undone.",
                key="delete_user_confirm",
            )
            if st.button("Delete User", disabled=not _confirm_user, key="delete_user_btn"):
                ok = auth_db.delete_user(_del_user['user_id'])
                if ok:
                    st.success(f"User '{_del_user['username']}' has been deleted.")
                    st.rerun()
                else:
                    st.error("Failed to delete user.")

        with col_del_user_hint:
            st.markdown("""
            <div class="info-box" style="margin-top: 0.25rem; border-left: 4px solid #D93025;">
                <strong style="color: #D93025;">Destructive action</strong><br>
                <span style="color: #6b7280;">
                    Deleting a user removes their account, all active sessions
                    and site assignments permanently.<br><br>
                    You cannot delete your own account.<br><br>
                    This action <strong>cannot be undone</strong>.
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Assign Sites to Users ────────────────────────────────────────────────
    st.markdown('<p class="section-title">Assign Sites to Users</p>', unsafe_allow_html=True)

    # Single batch query: users + their assigned device IDs/names in one round-trip
    users = auth_db.list_users_with_devices()
    devices = flow_db.get_devices()
    # Build a lookup dict for O(1) device resolution by ID
    device_map = {d['device_id']: d for d in devices}

    if not users:
        st.warning("No users available. Create a user first.")
    elif not devices:
        st.warning("No devices / sites available.")
    else:
        regular_users = [u for u in users if u['role'] == 'user']

        if not regular_users:
            st.info("All users are admins. Create a regular user to assign sites.")
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
                                width='stretch',
                            ):
                                auth_db.assign_device_to_user(
                                    selected_user['user_id'], device['device_id']
                                )
                                st.success(f"Added {device['device_name']}")
                                st.rerun()
                    else:
                        st.info("All sites already assigned.")

                with col_assigned:
                    st.markdown(
                        '<p style="font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;">'
                        'Assigned Sites</p>',
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
                                        f'{device["device_name"]}</p>',
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
                                        st.toast(f"Removed {device['device_name']}")
                                        st.rerun()
                    else:
                        st.info("No sites assigned yet.")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── All Users Overview ───────────────────────────────────────────────────
    st.markdown('<p class="section-title">All Users Overview</p>', unsafe_allow_html=True)

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
                width='stretch',
                hide_index=True,
            )
        else:
            st.info("No regular users to display.")

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── User Analytics ───────────────────────────────────────────────────────
    st.markdown('<p class="section-title">User Analytics</p>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#6b7280;font-size:0.9rem;margin-top:-0.5rem;margin-bottom:1rem;'>"
        "Activity insights showing when users are using the platform and what they are doing.</p>",
        unsafe_allow_html=True,
    )

    try:
        summary = auth_db.get_activity_summary()

        # ── KPI tiles ────────────────────────────────────────────────────────
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric("Total Logins (all time)", summary["total_logins"])
        with kpi2:
            st.metric("Unique Users Today", summary["unique_users_today"])
        with kpi3:
            st.metric("Unique Users (last 7 days)", summary["unique_users_7d"])

        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

        ana_col1, ana_col2 = st.columns(2)

        with ana_col1:
            st.markdown(
                "<p style='font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;'>Logins per User</p>",
                unsafe_allow_html=True,
            )
            if summary["logins_by_user"]:
                st.dataframe(
                    pd.DataFrame(summary["logins_by_user"]).rename(
                        columns={"username": "Username", "count": "Logins"}
                    ),
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("No login data yet.")

        with ana_col2:
            st.markdown(
                "<p style='font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;'>Page Views</p>",
                unsafe_allow_html=True,
            )
            if summary["page_views_by_page"]:
                st.dataframe(
                    pd.DataFrame(summary["page_views_by_page"]).rename(
                        columns={"page": "Page", "count": "Views"}
                    ),
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("No page-view data yet.")

        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

        st.markdown(
            "<p style='font-weight:600;color:#4A4A4A;margin-bottom:0.5rem;'>Recent Logins</p>",
            unsafe_allow_html=True,
        )
        if summary["recent_logins"]:
            st.dataframe(
                pd.DataFrame(summary["recent_logins"]).rename(
                    columns={"username": "Username", "timestamp": "Time (UTC)"}
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No login history yet.")

        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

        # ── Full activity log ─────────────────────────────────────────────────
        with st.expander("Full Activity Log (last 200 events)"):
            activity = auth_db.get_activity_log(limit=200)
            if activity:
                df_activity = pd.DataFrame(activity)[
                    ["timestamp", "username", "event_type", "page", "details"]
                ].rename(
                    columns={
                        "timestamp": "Time (UTC)",
                        "username": "User",
                        "event_type": "Event",
                        "page": "Page",
                        "details": "Details",
                    }
                )
                st.dataframe(df_activity, hide_index=True, width="stretch")
            else:
                st.info("No activity recorded yet.")

    except Exception as _exc:
        st.error(f"Could not load analytics: {_exc}")

    render_footer()


if __name__ == "__main__":
    init_auth_state()
    render_admin_panel()

