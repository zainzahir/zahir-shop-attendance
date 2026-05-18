"""
db.py — Shared database connection for the Streamlit web dashboard.

Secret resolution order (12-factor pattern):
  1. st.secrets["DATABASE_URL"]   ← Streamlit Community Cloud (production)
  2. os.getenv("DATABASE_URL")    ← local .env file / system env
"""

import os
import logging
import urllib.parse as _up
import psycopg2
import psycopg2.extras
import streamlit as st

logger = logging.getLogger(__name__)

# psycopg2 only accepts standard libpq parameters.
# Supabase pooler URLs append ?pgbouncer=true which causes a ProgrammingError.
_ALLOWED_PARAMS = {
    "sslmode", "sslcert", "sslkey", "sslrootcert",
    "connect_timeout", "application_name", "options",
}

def _sanitize_url(url: str) -> str:
    """Strip any query parameters not supported by psycopg2/libpq."""
    parsed      = _up.urlparse(url)
    params      = _up.parse_qs(parsed.query)
    clean       = {k: v for k, v in params.items() if k in _ALLOWED_PARAMS}
    clean_query = _up.urlencode({k: v[0] for k, v in clean.items()})
    return _up.urlunparse(parsed._replace(query=clean_query))


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

    clean_url = _sanitize_url(url)
    conn = psycopg2.connect(clean_url)
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
