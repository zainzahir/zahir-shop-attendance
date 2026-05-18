"""
app.py — Zahir Shop Digital Attendance System  (Streamlit Web Dashboard)
=========================================================================
Deploy:  streamlit run app.py            (local)
         → push to GitHub → share.streamlit.io  (production, free)

Secrets (Streamlit Cloud):
    In App Settings → Secrets, add:
        DATABASE_URL = "postgresql://..."
"""

import streamlit as st

st.set_page_config(
    page_title="Zahir Shop – Attendance Dashboard",
    page_icon="🖐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS for a premium dark look ────────────────────────────────────────
st.markdown(
    """
    <style>
        /* Gradient header bar */
        .stApp > header { background: transparent; }
        .block-container  { padding-top: 1.5rem; }

        /* Metric card styling */
        [data-testid="metric-container"] {
            background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
            border: 1px solid #3a3a5e;
            border-radius: 12px;
            padding: 16px;
        }
        [data-testid="stMetricLabel"]  { font-size: 0.85rem; color: #aaa; }
        [data-testid="stMetricValue"]  { font-size: 2rem;    color: #fff; }

        /* Tab strip */
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

        /* DataFrame */
        .stDataFrame { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 24px;
        border: 1px solid #0f3460;
    ">
        <h1 style="color:#fff; margin:0; font-size:2rem;">
            🖐 Zahir Shop — Digital Attendance System
        </h1>
        <p style="color:#aaa; margin:6px 0 0; font-size:1rem;">
            Biometric Fingerprint Attendance &nbsp;|&nbsp;
            Suprema BioMini Slim 2 &nbsp;|&nbsp;
            Real-Time Cloud Analytics
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Tabs ───────────────────────────────────────────────────────────────────────
from tabs import analytics, crud

tab_analytics, tab_crud = st.tabs(["📊  Analytics Dashboard", "👥  Employee Management"])

with tab_analytics:
    analytics.render()

with tab_crud:
    crud.render()
