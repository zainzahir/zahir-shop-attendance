"""
db.py — Shared database connection for the Streamlit web dashboard.

Secret resolution order (12-factor pattern):
  1. st.secrets["DATABASE_URL"]   ← Streamlit Community Cloud (production)
  2. os.getenv("DATABASE_URL")    ← local .env file / system env
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import logging
import calendar
import datetime
from decimal import Decimal
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


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTO-CREATE TABLES ON STARTUP
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_settings_tables():
    """
    Create the management/payroll tables if they don't exist,
    then seed singleton rows with defaults.
    Called once at dashboard startup (after auth).
    """
    conn = get_connection()
    with conn.cursor() as cur:
        # ── shift_settings ────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shift_settings (
                id                    SERIAL PRIMARY KEY,
                shift_start           TIME    NOT NULL DEFAULT '07:30',
                present_max_minutes   INT     NOT NULL DEFAULT 15,
                late_max_minutes      INT     NOT NULL DEFAULT 60,
                half_day_max_minutes  INT     NOT NULL DEFAULT 240,
                updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            INSERT INTO shift_settings (shift_start, present_max_minutes,
                                        late_max_minutes, half_day_max_minutes)
            SELECT '07:30', 15, 60, 240
            WHERE NOT EXISTS (SELECT 1 FROM shift_settings);
        """)

        # ── salary_settings ───────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS salary_settings (
                id                       SERIAL PRIMARY KEY,
                employee_id              INT NOT NULL UNIQUE
                                             REFERENCES employees(id) ON DELETE CASCADE,
                base_salary              NUMERIC(12,2) NOT NULL DEFAULT 0,
                late_deduction_type      TEXT NOT NULL DEFAULT 'fixed'
                                             CHECK (late_deduction_type IN ('fixed', 'percentage', 'per_minute')),
                late_deduction_value     NUMERIC(10,2) NOT NULL DEFAULT 0,
                absent_deduction_type    TEXT NOT NULL DEFAULT 'fixed'
                                             CHECK (absent_deduction_type IN ('fixed', 'percentage')),
                absent_deduction_value   NUMERIC(10,2) NOT NULL DEFAULT 0,
                half_day_deduction_type  TEXT NOT NULL DEFAULT 'fixed'
                                             CHECK (half_day_deduction_type IN ('fixed', 'percentage')),
                half_day_deduction_value NUMERIC(10,2) NOT NULL DEFAULT 0,
                updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        # ── relaxation_settings ───────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relaxation_settings (
                id                       SERIAL PRIMARY KEY,
                daily_grace_minutes      INT NOT NULL DEFAULT 0,
                monthly_late_waivers     INT NOT NULL DEFAULT 0,
                monthly_halfday_waivers  INT NOT NULL DEFAULT 0,
                updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            INSERT INTO relaxation_settings
                   (daily_grace_minutes, monthly_late_waivers, monthly_halfday_waivers)
            SELECT 0, 0, 0
            WHERE NOT EXISTS (SELECT 1 FROM relaxation_settings);
        """)

        # ── relaxation_dates ──────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS relaxation_dates (
                id                SERIAL PRIMARY KEY,
                date              DATE NOT NULL UNIQUE,
                relaxation_type   TEXT NOT NULL DEFAULT 'full_day_off'
                                      CHECK (relaxation_type IN
                                             ('full_day_off', 'no_deduction', 'extra_grace')),
                extra_grace_minutes INT NOT NULL DEFAULT 0,
                note              TEXT DEFAULT '',
                created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_relaxation_dates_date
            ON relaxation_dates (date);
        """)
    logger.info("Settings tables verified / created.")


# ═══════════════════════════════════════════════════════════════════════════════
#  SHIFT SETTINGS CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def get_shift_settings() -> dict:
    """Return the singleton shift_settings row as a dict."""
    rows = run_query("SELECT * FROM shift_settings ORDER BY id LIMIT 1;")
    if rows:
        return dict(rows[0])
    # fallback defaults
    return {
        "shift_start": datetime.time(7, 30),
        "present_max_minutes": 15,
        "late_max_minutes": 60,
        "half_day_max_minutes": 240,
    }


def upsert_shift_settings(
    shift_start: datetime.time,
    present_max: int,
    late_max: int,
    half_day_max: int,
):
    """Update the singleton shift_settings row."""
    run_query(
        """
        UPDATE shift_settings
        SET    shift_start          = %s,
               present_max_minutes  = %s,
               late_max_minutes     = %s,
               half_day_max_minutes = %s,
               updated_at           = NOW()
        WHERE  id = (SELECT id FROM shift_settings ORDER BY id LIMIT 1);
        """,
        (shift_start, present_max, late_max, half_day_max),
        fetch=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  SALARY SETTINGS CRUD (per-employee)
# ═══════════════════════════════════════════════════════════════════════════════

def get_salary_settings(employee_id: int) -> dict | None:
    """Return salary settings for a specific employee, or None."""
    rows = run_query(
        "SELECT * FROM salary_settings WHERE employee_id = %s;",
        (employee_id,),
    )
    return dict(rows[0]) if rows else None


def get_all_salary_settings() -> list[dict]:
    """Return salary settings joined with employee name for all configured employees."""
    rows = run_query("""
        SELECT ss.*, e.name AS employee_name
        FROM   salary_settings ss
        JOIN   employees e ON e.id = ss.employee_id
        ORDER  BY e.name;
    """)
    return [dict(r) for r in rows] if rows else []


def upsert_salary_settings(
    employee_id: int,
    base_salary: float,
    late_ded_type: str,
    late_ded_value: float,
    absent_ded_type: str,
    absent_ded_value: float,
    half_day_ded_type: str,
    half_day_ded_value: float,
):
    """Insert or update salary settings for an employee."""
    run_query(
        """
        INSERT INTO salary_settings
               (employee_id, base_salary,
                late_deduction_type, late_deduction_value,
                absent_deduction_type, absent_deduction_value,
                half_day_deduction_type, half_day_deduction_value,
                updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (employee_id) DO UPDATE SET
               base_salary              = EXCLUDED.base_salary,
               late_deduction_type      = EXCLUDED.late_deduction_type,
               late_deduction_value     = EXCLUDED.late_deduction_value,
               absent_deduction_type    = EXCLUDED.absent_deduction_type,
               absent_deduction_value   = EXCLUDED.absent_deduction_value,
               half_day_deduction_type  = EXCLUDED.half_day_deduction_type,
               half_day_deduction_value = EXCLUDED.half_day_deduction_value,
               updated_at               = NOW();
        """,
        (employee_id, base_salary,
         late_ded_type, late_ded_value,
         absent_ded_type, absent_ded_value,
         half_day_ded_type, half_day_ded_value),
        fetch=False,
    )


def delete_salary_settings(employee_id: int):
    """Remove salary settings for an employee."""
    run_query(
        "DELETE FROM salary_settings WHERE employee_id = %s;",
        (employee_id,),
        fetch=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  RELAXATION SETTINGS CRUD (monthly/global)
# ═══════════════════════════════════════════════════════════════════════════════

def get_relaxation_settings() -> dict:
    """Return the singleton relaxation_settings row."""
    rows = run_query("SELECT * FROM relaxation_settings ORDER BY id LIMIT 1;")
    if rows:
        return dict(rows[0])
    return {"daily_grace_minutes": 0, "monthly_late_waivers": 0, "monthly_halfday_waivers": 0}


def upsert_relaxation_settings(
    daily_grace: int,
    monthly_late_waivers: int,
    monthly_halfday_waivers: int,
):
    """Update the singleton relaxation_settings row."""
    run_query(
        """
        UPDATE relaxation_settings
        SET    daily_grace_minutes     = %s,
               monthly_late_waivers    = %s,
               monthly_halfday_waivers = %s,
               updated_at              = NOW()
        WHERE  id = (SELECT id FROM relaxation_settings ORDER BY id LIMIT 1);
        """,
        (daily_grace, monthly_late_waivers, monthly_halfday_waivers),
        fetch=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  RELAXATION DATES CRUD (date-specific overrides)
# ═══════════════════════════════════════════════════════════════════════════════

def get_relaxation_dates(year: int = None, month: int = None) -> list[dict]:
    """
    Return relaxation_dates rows.
    If year/month given, filter to that month; otherwise return all.
    """
    if year and month:
        rows = run_query(
            """
            SELECT * FROM relaxation_dates
            WHERE EXTRACT(YEAR FROM date) = %s
              AND EXTRACT(MONTH FROM date) = %s
            ORDER BY date;
            """,
            (year, month),
        )
    else:
        rows = run_query("SELECT * FROM relaxation_dates ORDER BY date DESC LIMIT 50;")
    return [dict(r) for r in rows] if rows else []


def add_relaxation_date(
    date: datetime.date,
    relaxation_type: str,
    extra_grace_minutes: int = 0,
    note: str = "",
):
    """Add a date-specific relaxation override."""
    run_query(
        """
        INSERT INTO relaxation_dates (date, relaxation_type, extra_grace_minutes, note)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
            relaxation_type     = EXCLUDED.relaxation_type,
            extra_grace_minutes = EXCLUDED.extra_grace_minutes,
            note                = EXCLUDED.note;
        """,
        (date, relaxation_type, extra_grace_minutes, note),
        fetch=False,
    )


def delete_relaxation_date(date: datetime.date):
    """Remove a date-specific relaxation override."""
    run_query(
        "DELETE FROM relaxation_dates WHERE date = %s;",
        (date,),
        fetch=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  PAYROLL COMPUTATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def compute_monthly_payroll(employee_id: int, year: int, month: int) -> dict:
    """
    Calculate the net salary for an employee for a given month.

    Returns a dict with:
      - base_salary, working_days, present_days, late_days, half_day_days,
        absent_days, waived_late, waived_half, billable_late, billable_half,
        billable_absent, late_deduction, half_day_deduction, absent_deduction,
        total_deductions, net_salary, relaxation_dates_applied, daily_breakdown
    """
    # 1. Get salary settings for this employee
    sal = get_salary_settings(employee_id)
    if not sal:
        return {"error": "No salary settings configured for this employee."}

    base_salary = Decimal(str(sal["base_salary"]))

    # 2. Get relaxation settings (monthly waivers)
    relax = get_relaxation_settings()
    monthly_late_waivers = relax.get("monthly_late_waivers", 0)

    # 3. Get relaxation dates for this month
    relax_dates = get_relaxation_dates(year, month)
    relax_date_map = {r["date"]: r for r in relax_dates}

    # 4. Get attendance logs for this employee this month
    _, last_day = calendar.monthrange(year, month)
    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, last_day)

    logs = run_query(
        """
        SELECT date, check_in_time, status
        FROM   attendance_logs
        WHERE  employee_id = %s
          AND  date BETWEEN %s AND %s
        ORDER  BY date;
        """,
        (employee_id, start_date, end_date),
    )
    log_map = {r["date"]: dict(r) for r in logs} if logs else {}

    # 5. Calculate working days (exclude relaxation full_day_off dates)
    today = datetime.date.today()
    daily_breakdown = []
    present_days = 0
    late_days = 0
    absent_days = 0
    relaxation_dates_applied = []
    
    late_days_list = []

    for day_num in range(1, last_day + 1):
        d = datetime.date(year, month, day_num)

        # Don't count future dates
        if d > today:
            break

        # Check if this date has a relaxation override
        relax_override = relax_date_map.get(d)

        if relax_override and relax_override["relaxation_type"] == "full_day_off":
            daily_breakdown.append({
                "date": d, "status": "Day Off (Relaxation)",
                "deduction": Decimal("0"), "note": relax_override.get("note", ""),
            })
            relaxation_dates_applied.append(d)
            continue

        log = log_map.get(d)
        if log:
            status = log["status"]
            # Treat 'Half Day' as 'Late' for legacy logs
            if status == "Half Day":
                status = "Late"
                
            no_deduction = (
                relax_override
                and relax_override["relaxation_type"] == "no_deduction"
            )
            if no_deduction:
                relaxation_dates_applied.append(d)

            if status == "Present":
                present_days += 1
                daily_breakdown.append({
                    "date": d, "status": "Present",
                    "deduction": Decimal("0"), "note": "",
                })
            elif status == "Late":
                if no_deduction:
                    present_days += 1  # treat as present
                    daily_breakdown.append({
                        "date": d, "status": "Late → Waived (Date Relaxation)",
                        "deduction": Decimal("0"),
                        "note": relax_override.get("note", ""),
                    })
                else:
                    late_days += 1
                    
                    # Fetch shift settings for start time
                    shift_cfg = get_shift_settings()
                    shift_start_time = shift_cfg["shift_start"]
                    if isinstance(shift_start_time, datetime.timedelta):
                        total_secs = int(shift_start_time.total_seconds())
                        shift_start_time = datetime.time(total_secs // 3600, (total_secs % 3600) // 60)
                    
                    # Compute minutes late
                    dt_checkin = datetime.datetime.combine(d, log["check_in_time"])
                    dt_shift = datetime.datetime.combine(d, shift_start_time)
                    minutes_late = max(0, int((dt_checkin - dt_shift).total_seconds() / 60))
                    
                    late_days_list.append((d, minutes_late))
                    daily_breakdown.append({
                        "date": d,
                        "status": f"Late ({minutes_late} min)" if minutes_late > 0 else "Late",
                        "deduction": Decimal("0"),
                        "note": "",
                    })
            else:
                # Absent (shouldn't appear in logs normally, but handle it)
                if no_deduction:
                    daily_breakdown.append({
                        "date": d, "status": "Absent → Waived (Date Relaxation)",
                        "deduction": Decimal("0"),
                        "note": relax_override.get("note", ""),
                    })
                else:
                    absent_days += 1
                    daily_breakdown.append({
                        "date": d, "status": "Absent",
                        "deduction": Decimal("0"),
                        "note": "",
                    })
        else:
            # No log = absent (unless relaxation)
            no_deduction = (
                relax_override
                and relax_override["relaxation_type"] == "no_deduction"
            )
            if no_deduction:
                relaxation_dates_applied.append(d)
                daily_breakdown.append({
                    "date": d, "status": "Absent → Waived (Date Relaxation)",
                    "deduction": Decimal("0"),
                    "note": relax_override.get("note", ""),
                })
            else:
                absent_days += 1
                daily_breakdown.append({
                    "date": d, "status": "Absent",
                    "deduction": Decimal("0"),
                    "note": "",
                })

    # 6. Apply monthly waivers
    waived_late = min(late_days, monthly_late_waivers)
    billable_late = late_days - waived_late
    billable_absent = absent_days

    # 7. Calculate deductions
    working_days_in_month = last_day  # use calendar days for simplicity
    daily_salary = base_salary / Decimal(str(working_days_in_month)) if working_days_in_month > 0 else Decimal("0")

    late_ded_type = sal["late_deduction_type"]
    late_ded_val = Decimal(str(sal["late_deduction_value"]))
    late_deduction = Decimal("0")
    
    # Sort late days chronologically
    late_days_list.sort(key=lambda x: x[0])
    
    # Waive the first waived_late days, deduct for the rest
    for idx, (day_date, mins) in enumerate(late_days_list):
        entry = next((e for e in daily_breakdown if e["date"] == day_date), None)
        
        if idx < waived_late:
            if entry:
                entry["status"] = f"Late ({mins} min) → Waived (Monthly Waiver)"
        else:
            day_ded = Decimal("0")
            if late_ded_type == "fixed":
                day_ded = late_ded_val
            elif late_ded_type == "percentage":
                day_ded = (late_ded_val / Decimal("100")) * daily_salary
            elif late_ded_type == "per_minute":
                day_ded = late_ded_val * Decimal(str(mins))
                
            late_deduction += day_ded
            if entry:
                entry["deduction"] = day_ded

    # Absent deductions
    absent_ded_type = sal["absent_deduction_type"]
    absent_ded_val = Decimal(str(sal["absent_deduction_value"]))
    absent_deduction = Decimal("0")
    
    for entry in daily_breakdown:
        if entry["status"] == "Absent":
            day_ded = Decimal("0")
            if absent_ded_type == "fixed":
                day_ded = absent_ded_val
            elif absent_ded_type == "percentage":
                day_ded = (absent_ded_val / Decimal("100")) * daily_salary
            absent_deduction += day_ded
            entry["deduction"] = day_ded

    total_deductions = late_deduction + absent_deduction
    net_salary = max(base_salary - total_deductions, Decimal("0"))

    return {
        "base_salary": float(base_salary),
        "working_days": working_days_in_month,
        "daily_salary": float(daily_salary),
        "present_days": present_days,
        "late_days": late_days,
        "half_day_days": 0,
        "absent_days": absent_days,
        "waived_late": waived_late,
        "waived_half": 0,
        "billable_late": billable_late,
        "billable_half": 0,
        "billable_absent": billable_absent,
        "late_deduction": float(late_deduction),
        "half_day_deduction": 0.0,
        "absent_deduction": float(absent_deduction),
        "total_deductions": float(total_deductions),
        "net_salary": float(net_salary),
        "relaxation_dates_applied": relaxation_dates_applied,
        "daily_breakdown": daily_breakdown,
    }

