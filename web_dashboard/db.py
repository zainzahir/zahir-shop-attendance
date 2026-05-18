"""
db.py — Shared database connection for the Streamlit web dashboard.

Secret resolution order (12-factor pattern):
  1. st.secrets["DATABASE_URL"]   ← Streamlit Community Cloud (production)
  2. os.getenv("DATABASE_URL")    ← local .env file / system env
"""

import os
import logging
import psycopg2
import psycopg2.extras
import streamlit as st

logger = logging.getLogger(__name__)


@st.cache_resource(show_spinner=False)
def get_connection():
    """
    Return a long-lived psycopg2 connection cached for the Streamlit session.
    @st.cache_resource ensures the connection is shared across reruns, not
    re-opened on every widget interaction.
    """
    url = None
    try:
        url = st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        url = os.getenv("DATABASE_URL", "")

    if not url:
        st.error(
            "DATABASE_URL is not set.\n\n"
            "• **Local dev**: add it to `web_dashboard/.env`\n"
            "• **Streamlit Cloud**: add it in App Settings → Secrets"
        )
        st.stop()

    conn = psycopg2.connect(url, sslmode="require")
    conn.autocommit = True          # dashboard is mostly read; safer for concurrent use
    return conn


def run_query(sql: str, params=None, fetch: bool = True):
    """Execute a parameterized SQL statement and optionally return rows."""
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        if fetch:
            return cur.fetchall()
        return None
