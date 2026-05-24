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
                      CHECK (status IN ('Present', 'Late', 'Absent')),
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

-- ============================================================
--  Management & Payroll Control Tables
-- ============================================================

-- ── TABLE 3: shift_settings (singleton) ────────────────────────
CREATE TABLE IF NOT EXISTS shift_settings (
    id                    SERIAL PRIMARY KEY,
    shift_start           TIME    NOT NULL DEFAULT '07:30',
    present_max_minutes   INT     NOT NULL DEFAULT 15,
    late_max_minutes      INT     NOT NULL DEFAULT 60,
    half_day_max_minutes  INT     NOT NULL DEFAULT 240,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed the default row if empty
INSERT INTO shift_settings (shift_start, present_max_minutes, late_max_minutes, half_day_max_minutes)
SELECT '07:30', 15, 60, 240
WHERE NOT EXISTS (SELECT 1 FROM shift_settings);

-- ── TABLE 4: salary_settings (per employee) ────────────────────
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

-- ── TABLE 5: relaxation_settings (singleton — monthly defaults) ─
CREATE TABLE IF NOT EXISTS relaxation_settings (
    id                       SERIAL PRIMARY KEY,
    daily_grace_minutes      INT NOT NULL DEFAULT 0,
    monthly_late_waivers     INT NOT NULL DEFAULT 0,
    monthly_halfday_waivers  INT NOT NULL DEFAULT 0,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO relaxation_settings (daily_grace_minutes, monthly_late_waivers, monthly_halfday_waivers)
SELECT 0, 0, 0
WHERE NOT EXISTS (SELECT 1 FROM relaxation_settings);

-- ── TABLE 6: relaxation_dates (date-specific overrides) ─────────
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

CREATE INDEX IF NOT EXISTS idx_relaxation_dates_date ON relaxation_dates (date);

COMMENT ON TABLE shift_settings      IS 'Singleton shift timing configuration.';
COMMENT ON TABLE salary_settings     IS 'Per-employee base salary and deduction rules.';
COMMENT ON TABLE relaxation_settings IS 'Monthly relaxation waivers (global defaults).';
COMMENT ON TABLE relaxation_dates    IS 'Date-specific attendance relaxation overrides.';

