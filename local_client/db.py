"""
db.py — Cloud Database Layer  (Supabase / PostgreSQL via psycopg2)
All SQL is parameterized — never use f-strings for user-supplied data.
"""

import logging
import datetime
from typing import Optional, List, Tuple

import psycopg2
import psycopg2.extras

from config import DATABASE_URL

logger = logging.getLogger(__name__)


# ─── Connection ───────────────────────────────────────────────────────────────
def get_connection():
    """Return a new psycopg2 connection (caller must close it)."""
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add it to local_client/.env  →  DATABASE_URL=postgresql://..."
        )
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    conn.autocommit = False
    return conn


# ─── Employee Queries ─────────────────────────────────────────────────────────
def insert_employee(
    name: str,
    cnic: str,
    phone: str,
    address: str,
    fingerprint_b64: str,
) -> int:
    """
    INSERT a new employee row with a biometric template.
    Returns the new employee id.
    """
    sql = """
        INSERT INTO employees (name, cnic, phone, address,
                               fingerprint_template, enrollment_status)
        VALUES (%s, %s, %s, %s, %s, 'enrolled')
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name, cnic, phone, address, fingerprint_b64))
            emp_id = cur.fetchone()[0]
        conn.commit()
    logger.info(f"Enrolled employee id={emp_id}  name={name!r}")
    return emp_id


def get_all_templates() -> List[Tuple[int, str]]:
    """
    Fetch (employee_id, fingerprint_template) for every enrolled employee.
    Used by the 1:N identification loop.
    """
    sql = """
        SELECT id, fingerprint_template
        FROM   employees
        WHERE  enrollment_status = 'enrolled'
          AND  fingerprint_template IS NOT NULL;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return rows   # [(id, b64_str), ...]


def get_employee_name(employee_id: int) -> Optional[str]:
    """Return the name of a single employee by id."""
    sql = "SELECT name FROM employees WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (employee_id,))
            row = cur.fetchone()
    return row[0] if row else None


# ─── Attendance Queries ───────────────────────────────────────────────────────
def already_logged_today(employee_id: int) -> bool:
    """Return True if the employee already has a log entry for today."""
    sql = """
        SELECT 1 FROM attendance_logs
        WHERE  employee_id = %s AND date = CURRENT_DATE
        LIMIT  1;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (employee_id,))
            return cur.fetchone() is not None


def log_attendance(
    employee_id: int,
    check_in_time: datetime.time,
    status: str,
) -> int:
    """
    INSERT a new attendance_log row.
    Returns log_id.  Raises if a duplicate daily entry exists.
    """
    sql = """
        INSERT INTO attendance_logs (employee_id, check_in_time, status)
        VALUES (%s, %s, %s)
        RETURNING log_id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (employee_id, check_in_time, status))
            log_id = cur.fetchone()[0]
        conn.commit()
    logger.info(
        f"Logged attendance: employee_id={employee_id} "
        f"time={check_in_time}  status={status!r}"
    )
    return log_id
