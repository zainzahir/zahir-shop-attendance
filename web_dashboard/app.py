"""
app.py — Zahir Shop Digital Attendance System  (Streamlit Web Dashboard)
=========================================================================
Deploy:  streamlit run app.py            (local)
         → push to GitHub → share.streamlit.io  (production, free)

Secrets (Streamlit Cloud) — add ALL of these in App Settings → Secrets:
    DATABASE_URL  = "postgresql://..."
    DASHBOARD_PASSWORD = "your_chosen_password"
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import streamlit as st

st.set_page_config(
    page_title="Zahir Shop – Attendance Dashboard",
    page_icon="🖐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        .stApp > header { background: transparent; }
        .block-container  { padding-top: 1.5rem; }

        [data-testid="metric-container"] {
            background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
            border: 1px solid #3a3a5e;
            border-radius: 12px;
            padding: 16px;
        }
        [data-testid="stMetricLabel"]  { font-size: 0.85rem; color: #aaa; }
        [data-testid="stMetricValue"]  { font-size: 2rem;    color: #fff; }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            border-bottom: 2px solid #3a3a5e;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 1rem;
            font-weight: 600;
            padding: 10px 24px;
            border-radius: 8px 8px 0 0;
        }
        .stDataFrame { border-radius: 10px; }

        /* Login card */
        .login-card {
            max-width: 420px;
            margin: 80px auto 0;
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border: 1px solid #0f3460;
            border-radius: 20px;
            padding: 40px 36px;
            text-align: center;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Password Gate ──────────────────────────────────────────────────────────────
def _get_dashboard_password() -> str:
    """Read admin password from Streamlit secrets or environment variable."""
    try:
        return st.secrets["DASHBOARD_PASSWORD"]
    except (KeyError, FileNotFoundError):
        import os
        return os.getenv("DASHBOARD_PASSWORD", "admin123")   # fallback for local dev


def _login_screen():
    """Render a branded login card and handle password verification."""
    st.markdown(
        """
        <div class="login-card">
            <div style="font-size:3rem; margin-bottom:8px;">🖐</div>
            <h2 style="color:#fff; margin:0 0 4px;">Zahir Shop</h2>
            <p style="color:#aaa; margin:0 0 28px; font-size:0.95rem;">
                Attendance System — Admin Portal
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Center the input widgets
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("<br>", unsafe_allow_html=True)
        password = st.text_input(
            "Admin Password",
            type="password",
            placeholder="Enter password …",
            label_visibility="collapsed",
        )
        login_btn = st.button("🔓  Sign In", use_container_width=True, type="primary")

        if login_btn or password:
            if password == _get_dashboard_password():
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")


# ── Auth Check ─────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    _login_screen()
    st.stop()          # halt — nothing below runs until authenticated

# ── Header (only shown after login) ───────────────────────────────────────────
st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 24px;
        border: 1px solid #0f3460;
        display: flex;
        justify-content: space-between;
        align-items: center;
    ">
        <div>
            <h1 style="color:#fff; margin:0; font-size:2rem;">
                🖐 Zahir Shop — Digital Attendance System
            </h1>
            <p style="color:#aaa; margin:6px 0 0; font-size:1rem;">
                Biometric Fingerprint Attendance &nbsp;|&nbsp;
                Suprema BioMini Slim 2 &nbsp;|&nbsp;
                Real-Time Cloud Analytics
            </p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Logout button in top-right area
if st.button("🚪 Logout", key="logout_btn"):
    st.session_state["authenticated"] = False
    st.rerun()

# ── Tabs ───────────────────────────────────────────────────────────────────────
from tabs import analytics, crud, management
from db import ensure_settings_tables

# Auto-create management/payroll tables on first load
ensure_settings_tables()

tab_analytics, tab_crud, tab_mgmt = st.tabs([
    "📊  Analytics Dashboard",
    "👥  Employee Management",
    "⚙️  Management & Payroll",
])

with tab_analytics:
    analytics.render()

with tab_crud:
    crud.render()

with tab_mgmt:
    management.render()
