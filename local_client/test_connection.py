"""
test_connection.py — Verifies .env, Supabase reachability, and schema tables.
"""
import os, sys
# Fix Windows console encoding for special characters
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

url = os.getenv("DATABASE_URL", "")
if not url or "<YOUR-PASSWORD>" in url:
    print("FAIL: DATABASE_URL is not set or still has the placeholder password.")
    print("      Open local_client/.env and paste your real Supabase connection string.")
    sys.exit(1)

# Strip unsupported query params that Supabase sometimes appends (e.g. pgbouncer=true)
# psycopg2 only supports standard libpq parameters.
import urllib.parse as _up
parsed = _up.urlparse(url)
params = _up.parse_qs(parsed.query)
allowed = {"sslmode", "sslcert", "sslkey", "sslrootcert", "connect_timeout",
           "application_name", "options"}
clean_params = {k: v for k, v in params.items() if k in allowed}
clean_query  = _up.urlencode({k: v[0] for k, v in clean_params.items()})
clean_url    = _up.urlunparse(parsed._replace(query=clean_query))

try:
    import psycopg2
    conn = psycopg2.connect(clean_url, connect_timeout=10)
    cur  = conn.cursor()

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    print("OK  Connected to Supabase successfully!")
    print(f"    Tables found: {tables}")

    required = {"employees", "attendance_logs"}
    missing  = required - set(tables)
    if missing:
        print(f"WARN  Missing tables: {missing}")
        print("      Run database/schema.sql in the Supabase SQL Editor first.")
    else:
        print("OK  Both required tables exist — schema is ready!")

    cur.close()
    conn.close()
    print("\nSUCCESS — Environment is fully configured. Run: python main.py")

except Exception as e:
    print(f"FAIL  Connection error: {e}")
    print("      Check your DATABASE_URL password in .env")
