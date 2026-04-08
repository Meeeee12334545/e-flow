"""
Shared styling module for the EDS FlowSense (EDS-FS) application.

Provides a single design system (colors, typography, components) that is
applied consistently across every Streamlit page.

Colour specification: EDS official brand palette.
  Primary Green:      #3A7F5F  (header, primary buttons, active nav)
  Dark Green:         #2F6B50  (hover, secondary headers)
  Light BG Grey:      #F4F5F4  (main page background)
  Text Grey:          #4A4A4A  (body text)
  Border Grey:        #D9D9D9  (dividers, card borders)
  Good / Normal:      #4CAF50
  Warning:            #F4B400
  Critical / Alert:   #D93025
  Chart – Depth:      #3A7F5F
  Chart – Velocity:   #2A9D8F
  Chart – Flow:       #1D4E89
"""

import streamlit as st

# ── Design tokens ──────────────────────────────────────────────────────────
_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        /* ── EDS brand palette ── */
        --bg:             #F4F5F4;
        --surface:        #ffffff;
        --surface-soft:   #f9faf9;
        --border:         #D9D9D9;
        --text:           #4A4A4A;
        --muted:          #6b7280;
        --primary:        #3A7F5F;
        --primary-light:  #2F6B50;
        --primary-soft:   #E8F3EE;
        --accent:         #2A9D8F;
        --accent-soft:    #E2F5F2;
        --success:        #4CAF50;
        --success-soft:   #E8F5E9;
        --warning:        #F4B400;
        --warning-soft:   #FFF8E1;
        --danger:         #D93025;
        --danger-soft:    #FDECEA;
        /* ── Chart parameter colours (fixed per sensor) ── */
        --chart-depth:    #3A7F5F;
        --chart-velocity: #2A9D8F;
        --chart-flow:     #1D4E89;
        /* ── Geometry ── */
        --radius-sm:      8px;
        --radius-md:      12px;
        --radius-lg:      16px;
        --shadow-sm:      0 2px 8px rgba(58,127,95,0.07);
        --shadow-md:      0 6px 20px rgba(58,127,95,0.09);
        --shadow-lg:      0 14px 40px rgba(58,127,95,0.11);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }

    [data-testid="stAppViewContainer"] > .main {
        background: var(--bg) !important;
    }

    * {
        /* No !important here — lets icon-font elements (Material Symbols used by
           Streamlit's sidebar toggle, expander arrow, etc.) keep their own font.
           The html/body rule above already seeds Inter for all text via inheritance. */
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        box-sizing: border-box;
    }

    .block-container {
        padding: 1.25rem 2rem 3rem !important;
        max-width: 1400px !important;
    }

    /* ── Typography ── */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text) !important;
        font-weight: 700 !important;
    }

    h1 { font-size: 2.6rem !important; line-height: 1.15 !important; }
    h2 { font-size: 1.7rem !important; line-height: 1.25 !important; }
    h3 { font-size: 1.25rem !important; }

    p, span, li { line-height: 1.7 !important; }

    /* ── Hero Card ── */
    .hero-card {
        background: linear-gradient(135deg, #2A6347 0%, #3A7F5F 60%, #2F6B50 100%);
        border-radius: var(--radius-lg);
        padding: 32px 40px;
        box-shadow: var(--shadow-lg);
        color: #ffffff;
        border: 1px solid rgba(255,255,255,0.08);
    }

    .hero-title {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        margin: 0.5rem 0 !important;
        color: #ffffff !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }

    .hero-subtitle {
        margin: 0.5rem 0 1.25rem 0 !important;
        font-size: 0.95rem !important;
        color: rgba(255,255,255,0.78) !important;
        max-width: 600px;
        line-height: 1.6 !important;
        letter-spacing: 0.01em;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 1rem;
        border-radius: 999px;
        background: rgba(255,255,255,0.18);
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        border: 1px solid rgba(255,255,255,0.3);
    }

    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.4rem 1rem;
        border-radius: 4px;
        font-weight: 600 !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        margin-right: 0.5rem;
        margin-bottom: 0.5rem;
    }

    /* ── Page header (sub-pages) ── */
    .page-header {
        background: #3A7F5F;
        border-radius: var(--radius-lg);
        padding: 28px 36px;
        margin-bottom: 1.75rem;
        box-shadow: var(--shadow-md);
    }

    .page-header-title {
        font-size: 1.9rem !important;
        font-weight: 700 !important;
        color: #ffffff !important;
        margin: 0 !important;
        letter-spacing: -0.02em;
        line-height: 1.2 !important;
    }

    .page-header-sub {
        font-size: 0.95rem !important;
        color: rgba(255,255,255,0.82) !important;
        margin: 0.4rem 0 0 0 !important;
        line-height: 1.5 !important;
    }

    /* ── Status / Live Card ── */
    .status-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-left: 4px solid var(--success);
        border-radius: var(--radius-md);
        padding: 24px 20px;
        box-shadow: var(--shadow-sm);
        text-align: center;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    .status-live-dot {
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: var(--success);
        display: inline-block;
        margin-right: 6px;
        animation: pulse 2.5s ease-in-out infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.5; transform: scale(0.85); }
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.45rem 1.2rem;
        border-radius: 4px;
        background: var(--success-soft);
        color: #2e7d32 !important;
        font-weight: 700 !important;
        font-size: 0.82rem !important;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-bottom: 0.75rem;
        border: 1px solid rgba(76,175,80,0.3);
    }

    .status-note {
        font-size: 0.82rem !important;
        color: var(--muted) !important;
        line-height: 1.55 !important;
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-top: 3px solid var(--primary);
        border-radius: var(--radius-md);
        padding: 20px 24px;
        box-shadow: var(--shadow-sm);
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }

    .metric-card:hover {
        box-shadow: var(--shadow-md);
        transform: translateY(-1px);
    }

    .metric-card.depth    { border-top-color: var(--chart-depth); }
    .metric-card.velocity { border-top-color: var(--chart-velocity); }
    .metric-card.flow     { border-top-color: var(--chart-flow); }

    .metric-label {
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin: 0 0 0.5rem 0 !important;
    }

    .metric-value {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        color: var(--text) !important;
        margin: 0 !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum";
    }

    .metric-value.green { color: #2e7d32 !important; }
    .metric-value.amber { color: #b45309 !important; }

    .metric-unit {
        font-size: 0.95rem !important;
        font-weight: 400 !important;
        color: var(--muted) !important;
        margin-left: 4px;
    }

    /* ── Section Card ── */
    .section-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 28px 30px;
        box-shadow: var(--shadow-sm);
        margin-bottom: 1.5rem;
    }

    .section-title {
        font-size: 0.82rem !important;
        font-weight: 700 !important;
        color: var(--muted) !important;
        margin: 0 0 0.75rem 0 !important;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        border-left: 3px solid var(--primary);
        padding-left: 10px;
    }

    .section-subtitle {
        font-size: 0.9rem !important;
        color: var(--muted) !important;
        margin: 0 0 1.5rem 0 !important;
    }

    /* ── Info / hint boxes ── */
    .info-box {
        background: var(--primary-soft);
        border-left: 3px solid var(--primary);
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 0.88rem !important;
        color: var(--text) !important;
        line-height: 1.6 !important;
    }

    /* ── Profile card ── */
    .profile-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 32px;
        box-shadow: var(--shadow-md);
        display: flex;
        align-items: flex-start;
        gap: 24px;
        margin-bottom: 1.5rem;
    }

    .profile-avatar {
        width: 72px;
        height: 72px;
        border-radius: 50%;
        background: #3A7F5F;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff;
        flex-shrink: 0;
        box-shadow: var(--shadow-sm);
    }

    .profile-info { flex: 1; }

    .profile-name {
        font-size: 1.55rem !important;
        font-weight: 700 !important;
        color: var(--text) !important;
        margin: 0 0 0.25rem 0 !important;
        letter-spacing: -0.01em;
    }

    .profile-role-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
        padding: 0.3rem 0.85rem;
        border-radius: 999px;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        margin-bottom: 0.75rem;
    }

    .profile-role-badge.admin {
        background: var(--primary-soft);
        color: var(--primary) !important;
        border: 1px solid rgba(58,127,95,0.25);
    }

    .profile-role-badge.user {
        background: var(--accent-soft);
        color: var(--accent) !important;
        border: 1px solid rgba(42,157,143,0.25);
    }

    .profile-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        font-size: 0.88rem !important;
        color: var(--muted) !important;
    }

    .profile-meta-item strong {
        color: var(--text) !important;
        font-weight: 500 !important;
    }

    /* ── Device row card ── */
    .device-row {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 18px 20px;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        gap: 16px;
        transition: box-shadow 0.15s ease;
    }

    .device-row:hover {
        box-shadow: var(--shadow-sm);
    }

    .device-icon {
        width: 44px;
        height: 44px;
        border-radius: 10px;
        background: var(--primary-soft);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.4rem;
        flex-shrink: 0;
    }

    .device-name {
        font-weight: 600 !important;
        color: var(--text) !important;
        font-size: 0.97rem !important;
        margin: 0 0 0.15rem 0 !important;
    }

    .device-meta {
        font-size: 0.82rem !important;
        color: var(--muted) !important;
        margin: 0 !important;
    }

    /* ── Login page ── */
    .login-wrapper {
        min-height: 60vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem 1rem;
    }

    .login-brand {
        text-align: center;
        margin-bottom: 2rem;
    }

    .login-brand-logo {
        width: 64px;
        height: 64px;
        border-radius: 18px;
        background: #3A7F5F;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 2rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 8px 24px rgba(58,127,95,0.25);
    }

    .login-brand-name {
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        margin: 0 !important;
        letter-spacing: -0.03em;
    }

    .login-brand-tagline {
        font-size: 0.92rem !important;
        color: var(--muted) !important;
        margin: 0.25rem 0 0 0 !important;
    }

    .login-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 36px 40px;
        box-shadow: var(--shadow-lg);
        width: 100%;
        max-width: 440px;
    }

    /* ── Streamlit native metric override ── */
    div[data-testid="metric-container"] {
        background: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-top: 3px solid var(--primary) !important;
        border-radius: var(--radius-md) !important;
        padding: 1rem 1.25rem !important;
        box-shadow: var(--shadow-sm) !important;
    }

    div[data-testid="metric-container"] label {
        color: var(--muted) !important;
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-weight: 700 !important;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum";
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: var(--radius-sm) !important;
        background: #3A7F5F !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 3px 10px rgba(58,127,95,0.20) !important;
        padding: 0.6rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: background 0.15s ease, box-shadow 0.15s ease !important;
    }

    .stButton > button:hover {
        background: #2F6B50 !important;
        box-shadow: 0 6px 16px rgba(58,127,95,0.28) !important;
    }

    .stButton > button[kind="secondary"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        border: 1.5px solid var(--primary) !important;
        box-shadow: none !important;
    }

    .stButton > button[kind="secondary"]:hover {
        background: var(--primary-soft) !important;
    }

    /* Download buttons */
    .stDownloadButton > button {
        border-radius: var(--radius-sm) !important;
        border: 1.5px solid var(--border) !important;
        background: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 600 !important;
        padding: 0.55rem 1.2rem !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid var(--border) !important;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 0.75rem !important;
    }

    /* Section headers in sidebar — refined rule, applied after the first */
    section[data-testid="stSidebar"] h2 {
        font-size: 0.68rem !important;
        font-weight: 700 !important;
        color: var(--muted) !important;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin: 1.1rem 0 0.4rem 0 !important;
        padding-top: 1rem !important;
        border-top: 1px solid var(--border) !important;
    }

    /* ── Sidebar navigation buttons ── */
    section[data-testid="stSidebar"] .stButton > button {
        background: #ffffff !important;
        color: var(--text) !important;
        border: 1px solid var(--border) !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0.3rem 0.6rem !important;
        font-weight: 500 !important;
        font-size: 0.78rem !important;
        border-radius: var(--radius-sm) !important;
        transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
    }

    section[data-testid="stSidebar"] .stButton > button:hover {
        background: var(--primary-soft) !important;
        color: var(--primary) !important;
        border-color: var(--primary) !important;
        box-shadow: none !important;
    }

    /* ── "How Does FlowSense™ Work" — discreet small link style ── */
    .methodology-nav .stButton > button {
        background: transparent !important;
        color: var(--muted) !important;
        border: none !important;
        box-shadow: none !important;
        font-size: 0.72rem !important;
        font-weight: 400 !important;
        padding: 0.15rem 0.4rem !important;
        text-decoration: underline !important;
        text-underline-offset: 2px !important;
        justify-content: center !important;
    }

    .methodology-nav .stButton > button:hover {
        background: transparent !important;
        color: var(--primary) !important;
        border-color: transparent !important;
    }

    /* Sign Out button — keep it distinct */
    section[data-testid="stSidebar"] .stButton > button[data-testid*="logout"] {
        background: #ffffff !important;
        color: var(--muted) !important;
        border: 1px solid var(--border) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
    }

    section[data-testid="stSidebar"] .stButton > button[data-testid*="logout"]:hover {
        background: var(--danger-soft) !important;
        color: var(--danger) !important;
        border-color: var(--danger) !important;
    }

    /* ── Sidebar user card ── */
    .sidebar-user-card {
        background: var(--primary-soft);
        border: 1px solid rgba(58,127,95,0.18);
        border-radius: var(--radius-sm);
        padding: 12px 14px;
        margin-bottom: 0.75rem;
    }

    .sidebar-user-name {
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        color: var(--primary) !important;
        margin: 0 0 0.15rem 0 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    .sidebar-user-role {
        font-size: 0.75rem !important;
        color: var(--muted) !important;
        margin: 0 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px !important;
        background: #f0f2f1 !important;
        border-radius: 6px !important;
        padding: 4px !important;
        border: 1px solid var(--border) !important;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 4px !important;
        padding: 0.45rem 1.1rem !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--muted) !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 700 !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.1) !important;
        border: 1px solid var(--border) !important;
    }

    /* ── Selectbox & inputs ── */
    .stSelectbox > div > div {
        border-radius: var(--radius-sm) !important;
        border-color: var(--border) !important;
        background: var(--surface) !important;
    }

    /* Prevent selectbox label from overlapping adjacent elements */
    .stSelectbox label {
        display: block !important;
        overflow: hidden !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        max-width: 100% !important;
    }

    /* ── Expander: fix the _arr...Label overlap ──────────────────────────────
       The collapse/expand toggle icon lives inside <summary> alongside a <p>
       with the label.  Applying white-space:nowrap + ellipsis to the <summary>
       squashes both the icon and the text together, producing garbled output
       like "_arr...SiteDetails".  Instead we constrain only the inner <p>. */
    .stExpander summary,
    [data-testid="stExpander"] summary {
        display: flex !important;
        align-items: center !important;
        gap: 6px !important;
        overflow: hidden !important;
        /* Do NOT set white-space or text-overflow here */
    }

    .stExpander summary p,
    [data-testid="stExpander"] summary p,
    .stExpander summary span.st-emotion-cache-1gulkj5,
    .stExpander [data-testid="stExpanderToggleIcon"] ~ * {
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
        flex: 1 1 0 !important;
        min-width: 0 !important;
        margin: 0 !important;
    }

    /* Keep the toggle icon from shrinking */
    .stExpander [data-testid="stExpanderToggleIcon"],
    [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
        flex-shrink: 0 !important;
    }

    /* Sidebar element spacing — prevents stacked elements from visually colliding */
    section[data-testid="stSidebar"] .stSelectbox,
    section[data-testid="stSidebar"] .stExpander,
    section[data-testid="stSidebar"] .stButton {
        margin-bottom: 0.45rem !important;
    }

    /* Text inputs & textareas in sidebar */
    section[data-testid="stSidebar"] .stTextInput,
    section[data-testid="stSidebar"] .stTextArea {
        margin-bottom: 0.45rem !important;
    }

    /* Ensure code blocks in sidebar wrap cleanly */
    section[data-testid="stSidebar"] code {
        word-break: break-word !important;
        overflow-wrap: break-word !important;
        white-space: pre-wrap !important;
        display: block !important;
    }

    /* ── Code ── */
    code {
        background: #f1f5f9 !important;
        padding: 0.2rem 0.45rem !important;
        border-radius: 6px !important;
        font-size: 0.85em !important;
        color: var(--primary) !important;
    }

    /* ── Footer ── */
    .app-footer {
        border-top: 1px solid var(--border);
        padding: 1.25rem 0 0.5rem 0;
        margin-top: 3rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .app-footer-brand {
        font-weight: 700 !important;
        color: var(--primary) !important;
        font-size: 0.95rem !important;
    }

    .app-footer-meta {
        font-size: 0.82rem !important;
        color: var(--muted) !important;
    }

    /* ── Dataframe / Data tables ── */
    [data-testid="stDataFrame"] table {
        font-size: 0.84rem !important;
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum";
    }

    [data-testid="stDataFrame"] thead th {
        background: #f0f4f2 !important;
        color: var(--text) !important;
        font-weight: 700 !important;
        font-size: 0.74rem !important;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        border-bottom: 2px solid var(--border) !important;
    }

    [data-testid="stDataFrame"] tbody tr:hover td {
        background: var(--primary-soft) !important;
    }

    /* ── Form inputs — polished appearance ── */
    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        border: 1.5px solid var(--border) !important;
        border-radius: var(--radius-sm) !important;
        background: var(--surface) !important;
        color: var(--text) !important;
        font-size: 0.9rem !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
        padding: 0.55rem 0.85rem !important;
    }

    .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(58,127,95,0.12) !important;
        outline: none !important;
    }

    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stNumberInput label, .stRadio label {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        margin-bottom: 0.3rem !important;
    }

    /* ── Radio buttons — pill style ── */
    .stRadio [data-testid="stMarkdownContainer"] p {
        font-size: 0.88rem !important;
        color: var(--text) !important;
    }

    .stRadio > div[role="radiogroup"] {
        gap: 0.4rem !important;
    }

    /* ── Checkbox ── */
    .stCheckbox label {
        font-size: 0.88rem !important;
        color: var(--text) !important;
        text-transform: none !important;
        letter-spacing: 0 !important;
        font-weight: 400 !important;
    }

    /* ── Alert / info / success banners — tighter ── */
    .stAlert {
        border-radius: var(--radius-sm) !important;
        font-size: 0.88rem !important;
        padding: 0.7rem 1rem !important;
    }

    /* ── Forms ── */
    [data-testid="stForm"] {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-md) !important;
        padding: 1.25rem 1.5rem 1rem !important;
        background: var(--surface) !important;
        box-shadow: var(--shadow-sm) !important;
    }

    [data-testid="stForm"] [data-testid="stFormSubmitButton"] > button {
        margin-top: 0.5rem !important;
        width: 100% !important;
        padding: 0.65rem 1.4rem !important;
        font-size: 0.92rem !important;
        letter-spacing: 0.03em;
    }

    /* ── Dividers — subtle horizontal rule ── */
    hr {
        border: none !important;
        border-top: 1px solid var(--border) !important;
        margin: 1.5rem 0 !important;
    }

    /* ── Quality / status text badges ── */
    .quality-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    .quality-badge.high     { background: #E8F5E9; color: #2e7d32; border: 1px solid #a5d6a7; }
    .quality-badge.medium   { background: #FFF8E1; color: #b45309; border: 1px solid #ffe082; }
    .quality-badge.low      { background: #FDECEA; color: #c62828; border: 1px solid #ef9a9a; }

    /* ── Hide Streamlit's auto-generated page navigation (duplicates explicit nav buttons) ── */
    [data-testid="stSidebarNavItems"],
    [data-testid="stSidebarNavSeparator"] {
        display: none !important;
    }

    /* ── Responsive ── */
    @media (max-width: 768px) {
        .block-container { padding: 1rem 1rem 2rem !important; }
        .hero-card       { padding: 24px 20px !important; }
        .hero-title      { font-size: 2rem !important; }
        .metric-value    { font-size: 1.9rem !important; }
        .section-card    { padding: 20px !important; }
        .login-card      { padding: 24px 20px !important; }
        .profile-card    { flex-direction: column; }
    }
</style>
"""


def apply_styles() -> None:
    """Inject the shared design system CSS into the current Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)
