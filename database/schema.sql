-- ============================================================
--  Digital Attendance System – Supabase PostgreSQL Schema
--  Engine : PostgreSQL 14+
--  Run this entire script in the Supabase → SQL Editor
-- ============================================================

-- ── TABLE 1: employees ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employees (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT        NOT NULL,
    cnic                 VARCHAR(15) UNIQUE,           -- XXXXX-XXXXXXX-X
    phone                VARCHAR(20),
    address              TEXT,
    -- Base64-encoded raw bytes of the BS2Fingerprint ctypes struct.
    -- NULL when added via the web dashboard before local enrollment.
    fingerprint_template TEXT,
    enrollment_status    TEXT        NOT NULL DEFAULT 'pending_local_enrollment'
                             CHECK (enrollment_status IN
                                    ('enrolled', 'pending_local_enrollment')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_employees_updated_at ON employees;
CREATE TRIGGER trg_employees_updated_at
    BEFORE UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_employees_name ON employees (name);

-- ── TABLE 2: attendance_logs ───────────────────────────────────
CREATE TABLE IF NOT EXISTS attendance_logs (
    log_id        SERIAL PRIMARY KEY,
    employee_id   INT  NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    date          DATE NOT NULL DEFAULT CURRENT_DATE,
    check_in_time TIME NOT NULL,
    status        TEXT NOT NULL
                      CHECK (status IN ('Present', 'Late', 'Half Day', 'Absent')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One log entry per employee per day (scanner enforces this in code too)
    CONSTRAINT uq_employee_daily_log UNIQUE (employee_id, date)
);

CREATE INDEX IF NOT EXISTS idx_logs_date        ON attendance_logs (date);
CREATE INDEX IF NOT EXISTS idx_logs_employee_id ON attendance_logs (employee_id);

-- ── VIEW: today_summary ────────────────────────────────────────
-- Full name + status for every employee today (LEFT JOIN → shows Absent too)
CREATE OR REPLACE VIEW today_summary AS
SELECT
    e.id            AS employee_id,
    e.name          AS employee_name,
    e.enrollment_status,
    al.date,
    al.check_in_time,
    COALESCE(al.status, 'Absent') AS status
FROM employees e
LEFT JOIN attendance_logs al
    ON al.employee_id = e.id AND al.date = CURRENT_DATE
WHERE e.enrollment_status = 'enrolled';

-- ── VIEW: status_counts_today ──────────────────────────────────
-- Pie-chart source for the Streamlit analytics tab
CREATE OR REPLACE VIEW status_counts_today AS
SELECT
    COALESCE(al.status, 'Absent') AS status,
    COUNT(*)                      AS count
FROM employees e
LEFT JOIN attendance_logs al
    ON al.employee_id = e.id AND al.date = CURRENT_DATE
WHERE e.enrollment_status = 'enrolled'
GROUP BY COALESCE(al.status, 'Absent');

-- ── VIEW: daily_attendance_trend ───────────────────────────────
-- Line-chart source: last 30 days broken down by status
CREATE OR REPLACE VIEW daily_attendance_trend AS
SELECT
    date,
    status,
    COUNT(*) AS count
FROM attendance_logs
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY date, status
ORDER BY date ASC;

COMMENT ON TABLE employees        IS 'All registered shop employees with biometric data.';
COMMENT ON TABLE attendance_logs  IS 'Daily attendance records with check-in time and computed status.';
COMMENT ON COLUMN employees.fingerprint_template
    IS 'Base64-encoded bytes of BS2Fingerprint ctypes struct. NULL until local enrollment.';
