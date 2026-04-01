"""
Shared styling module for the e-flow application.

Provides a single design system (colors, typography, components) that is
applied consistently across every Streamlit page.
"""

import streamlit as st

# ── Design tokens ──────────────────────────────────────────────────────────
_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --bg:             #f4f7fb;
        --surface:        #ffffff;
        --surface-soft:   #f8fbff;
        --border:         #dfe7ef;
        --text:           #233047;
        --muted:          #6b7280;
        --primary:        #0f4c81;
        --primary-light:  #1a6bb5;
        --primary-soft:   #e7f0ff;
        --accent:         #0b76ca;
        --accent-soft:    #dbe9ff;
        --success:        #047c3d;
        --success-soft:   #daf9e6;
        --warning:        #b45309;
        --warning-soft:   #fef3c7;
        --danger:         #b91c1c;
        --danger-soft:    #fee2e2;
        --radius-sm:      12px;
        --radius-md:      18px;
        --radius-lg:      22px;
        --shadow-sm:      0 4px 12px rgba(15,76,129,0.06);
        --shadow-md:      0 14px 32px rgba(15,76,129,0.08);
        --shadow-lg:      0 24px 60px rgba(15,76,129,0.10);
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }

    [data-testid="stAppViewContainer"] > .main {
        background: var(--bg) !important;
    }

    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
        box-sizing: border-box;
    }

    .block-container {
        padding: 1.5rem 2rem 3rem !important;
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
        background: linear-gradient(135deg, #0f4c81 0%, #1a6bb5 60%, #0b76ca 100%);
        border-radius: var(--radius-lg);
        padding: 36px 40px;
        box-shadow: var(--shadow-lg);
        color: #ffffff;
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
        margin: 0.75rem 0 1.5rem 0 !important;
        font-size: 1.05rem !important;
        color: rgba(255,255,255,0.85) !important;
        max-width: 560px;
        line-height: 1.6 !important;
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
        padding: 0.55rem 1.1rem;
        border-radius: 999px;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        margin-right: 0.5rem;
        margin-bottom: 0.5rem;
    }

    /* ── Page header (sub-pages) ── */
    .page-header {
        background: linear-gradient(135deg, #0f4c81 0%, #1a6bb5 60%, #0b76ca 100%);
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
        border-radius: var(--radius-md);
        padding: 28px 20px;
        box-shadow: var(--shadow-md);
        text-align: center;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    .status-live-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--success);
        display: inline-block;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.6; transform: scale(0.9); }
    }

    .status-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.6rem 1.4rem;
        border-radius: 999px;
        background: var(--success-soft);
        color: var(--success) !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        letter-spacing: 0.06em;
        margin-bottom: 0.75rem;
        border: 1px solid rgba(4,124,61,0.2);
    }

    .status-note {
        font-size: 0.88rem !important;
        color: var(--muted) !important;
        line-height: 1.5 !important;
    }

    /* ── Metric Cards ── */
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 24px;
        box-shadow: var(--shadow-md);
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }

    .metric-card:hover {
        box-shadow: var(--shadow-lg);
        transform: translateY(-2px);
    }

    .metric-label {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0 0 0.6rem 0 !important;
    }

    .metric-value {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        margin: 0 !important;
        line-height: 1.1 !important;
        letter-spacing: -0.02em;
    }

    .metric-value.green { color: var(--success) !important; }
    .metric-value.amber { color: var(--warning) !important; }

    .metric-unit {
        font-size: 1rem !important;
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
        font-size: 1.35rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        margin: 0 0 0.75rem 0 !important;
        letter-spacing: -0.01em;
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
        background: linear-gradient(135deg, #0f4c81 0%, #0b76ca 100%);
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
        border: 1px solid rgba(15,76,129,0.2);
    }

    .profile-role-badge.user {
        background: var(--accent-soft);
        color: var(--accent) !important;
        border: 1px solid rgba(11,118,202,0.2);
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
        background: linear-gradient(135deg, #0f4c81 0%, #0b76ca 100%);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 2rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 8px 24px rgba(15,76,129,0.25);
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
        border-radius: var(--radius-md) !important;
        padding: 1rem 1.25rem !important;
        box-shadow: var(--shadow-sm) !important;
    }

    div[data-testid="metric-container"] label {
        color: var(--muted) !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }

    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: var(--primary) !important;
        font-weight: 700 !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: var(--radius-sm) !important;
        background: linear-gradient(135deg, #0f4c81 0%, #0a3c67 100%) !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 6px 18px rgba(15,76,129,0.22) !important;
        padding: 0.6rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }

    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 10px 24px rgba(15,76,129,0.3) !important;
    }

    .stButton > button[kind="secondary"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        border: 1.5px solid var(--primary) !important;
        box-shadow: none !important;
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
        padding-top: 1.5rem !important;
    }

    section[data-testid="stSidebar"] h2 {
        font-size: 1rem !important;
        font-weight: 700 !important;
        color: var(--primary) !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    /* ── Sidebar user card ── */
    .sidebar-user-card {
        background: var(--primary-soft);
        border: 1px solid rgba(15,76,129,0.15);
        border-radius: var(--radius-sm);
        padding: 14px 16px;
        margin-bottom: 1rem;
    }

    .sidebar-user-name {
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        color: var(--primary) !important;
        margin: 0 0 0.2rem 0 !important;
    }

    .sidebar-user-role {
        font-size: 0.8rem !important;
        color: var(--muted) !important;
        margin: 0 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background: var(--primary-soft) !important;
        border-radius: var(--radius-sm) !important;
        padding: 5px !important;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 500 !important;
        color: var(--muted) !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--surface) !important;
        color: var(--primary) !important;
        font-weight: 700 !important;
        box-shadow: var(--shadow-sm) !important;
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

    /* Ensure expander header text never overlaps */
    .stExpander summary {
        overflow: hidden !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
    }

    /* Sidebar element spacing — prevents stacked elements from visually colliding */
    section[data-testid="stSidebar"] .stSelectbox,
    section[data-testid="stSidebar"] .stExpander,
    section[data-testid="stSidebar"] .stButton {
        margin-bottom: 0.5rem !important;
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
