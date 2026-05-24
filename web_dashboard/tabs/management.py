"""
tabs/management.py — Management & Payroll Control Panel
Provides shift configuration, per-employee salary settings,
relaxation waivers (monthly + date-specific), and payroll calculator.
"""

import datetime
import calendar
import pandas as pd
import streamlit as st

from db import (
    run_query,
    get_shift_settings,
    upsert_shift_settings,
    get_salary_settings,
    get_all_salary_settings,
    upsert_salary_settings,
    delete_salary_settings,
    get_relaxation_settings,
    upsert_relaxation_settings,
    get_relaxation_dates,
    add_relaxation_date,
    delete_relaxation_date,
    compute_monthly_payroll,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _load_employees() -> pd.DataFrame:
    """Fetch all employees for dropdown selection."""
    rows = run_query(
        "SELECT id, name, enrollment_status FROM employees ORDER BY name;"
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _format_currency(value: float) -> str:
    """Format as Pakistani Rupee string."""
    return f"Rs. {value:,.2f}"


# ─── Main Render ──────────────────────────────────────────────────────────────

def render():
    st.subheader("⚙️ Management & Payroll Control")

    sections = st.tabs([
        "⏰ Shift Settings",
        "💰 Salary Settings",
        "🕊️ Relaxation Waivers",
        "📊 Payroll Calculator",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION 1: SHIFT SETTINGS
    # ══════════════════════════════════════════════════════════════════════════
    with sections[0]:
        st.markdown("#### ⏰ Shift Timing & Status Thresholds")
        st.markdown(
            "Configure when the work shift starts and the lateness thresholds "
            "that determine **Present** and **Late** status."
        )

        shift = get_shift_settings()

        # Parse the shift_start — could be time object or timedelta from PG
        raw_start = shift["shift_start"]
        if isinstance(raw_start, datetime.timedelta):
            total_secs = int(raw_start.total_seconds())
            default_start = datetime.time(total_secs // 3600, (total_secs % 3600) // 60)
        elif isinstance(raw_start, datetime.time):
            default_start = raw_start
        else:
            default_start = datetime.time(7, 30)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #1a1a2e, #16213e);
                    border: 1px solid #0f3460;
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 16px;
                ">
                    <h4 style="color: #4fc3f7; margin: 0 0 12px;">🕐 Shift Start Time</h4>
                    <p style="color: #aaa; font-size: 0.85rem; margin: 0;">
                        The official start time of the work shift.
                        Employees who scan after this + grace period are marked Late.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            new_shift_start = st.time_input(
                "Shift Start Time",
                value=default_start,
                key="shift_start_input",
            )

        with col2:
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #1a1a2e, #16213e);
                    border: 1px solid #0f3460;
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 16px;
                ">
                    <h4 style="color: #ffb74d; margin: 0 0 12px;">⏱️ Threshold Rules</h4>
                    <p style="color: #aaa; font-size: 0.85rem; margin: 0;">
                        Minutes after shift start → determines attendance status.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            new_present_max = st.number_input(
                "✅ Present — max minutes late",
                min_value=0, max_value=120,
                value=int(shift["present_max_minutes"]),
                help="Arriving within this many minutes = Present",
                key="present_max_input",
            )
            new_late_max = st.number_input(
                "⏰ Late — max minutes late",
                min_value=0, max_value=480,
                value=int(shift["late_max_minutes"]),
                help="Arriving after the Present window = Late",
                key="late_max_input",
            )

        # Visual timeline
        st.markdown("---")
        st.markdown("##### 📐 Visual Timeline")
        shift_str = new_shift_start.strftime("%I:%M %p")
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(90deg, #1b5e20 0%, #e65100 60%, #b71c1c 100%);
                border-radius: 8px;
                padding: 12px 20px;
                color: white;
                font-weight: 600;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 0.85rem;
            ">
                <span>✅ Present<br><small>{shift_str} + {new_present_max}min</small></span>
                <span>⏰ Late<br><small>Arriving after {new_present_max}min</small></span>
                <span>❌ Absent<br><small>No scan log today</small></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("")
        if st.button("💾 Save Shift Settings", type="primary", key="save_shift_btn"):
            if new_present_max >= new_late_max:
                st.error("Present threshold must be less than Late threshold.")
            else:
                upsert_shift_settings(
                    new_shift_start, new_present_max, new_late_max, 240
                )
                st.success("✅ Shift settings updated successfully!")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION 2: SALARY SETTINGS (PER-EMPLOYEE)
    # ══════════════════════════════════════════════════════════════════════════
    with sections[1]:
        st.markdown("#### 💰 Per-Employee Salary & Deduction Rules")

        df_emp = _load_employees()
        if df_emp.empty:
            st.info("No employees found. Add employees first.")
        else:
            salary_tabs = st.tabs(["📝 Configure Salary", "📋 View All Settings"])

            # ── Configure ─────────────────────────────────────────────
            with salary_tabs[0]:
                options = {
                    f"#{row['id']}  {row['name']}": row["id"]
                    for _, row in df_emp.iterrows()
                }
                selected = st.selectbox(
                    "Select Employee",
                    list(options.keys()),
                    key="sal_emp_select",
                )
                emp_id = options[selected]

                # Load existing settings
                existing = get_salary_settings(emp_id)

                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #1a1a2e, #16213e);
                        border: 1px solid #0f3460;
                        border-radius: 12px;
                        padding: 16px 20px;
                        margin: 12px 0;
                    ">
                        <h5 style="color: #81c784; margin: 0 0 8px;">💵 Base Monthly Salary</h5>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                base_salary = st.number_input(
                    "Monthly Base Salary (Rs.)",
                    min_value=0.0,
                    value=float(existing["base_salary"]) if existing else 0.0,
                    step=500.0,
                    format="%.2f",
                    key="base_salary_input",
                )

                st.markdown("---")
                st.markdown("##### 📉 Deduction Rules")
                st.caption(
                    "**Fixed** = flat amount deducted per occurrence  |  "
                    "**Percentage** = % of daily salary deducted per occurrence"
                )

                ded_col1, ded_col2 = st.columns(2)

                with ded_col1:
                    st.markdown(
                        '<p style="color: #ffb74d; font-weight: 600;">⏰ Late Deduction</p>',
                        unsafe_allow_html=True,
                    )
                    
                    if not existing:
                        late_type_idx = 0
                    elif existing["late_deduction_type"] == "fixed":
                        late_type_idx = 0
                    elif existing["late_deduction_type"] == "percentage":
                        late_type_idx = 1
                    else:
                        late_type_idx = 2
                        
                    late_type = st.radio(
                        "Type",
                        ["fixed", "percentage", "per_minute"],
                        index=late_type_idx,
                        key="late_ded_type",
                        horizontal=True,
                    )
                    
                    if late_type == "fixed":
                        late_label = "Amount (Rs.)"
                        late_step = 50.0
                    elif late_type == "percentage":
                        late_label = "Percentage (%)"
                        late_step = 1.0
                    else:
                        late_label = "Rate per Minute (Rs./min)"
                        late_step = 0.5

                    late_value = st.number_input(
                        late_label,
                        min_value=0.0,
                        value=float(existing["late_deduction_value"]) if existing else 0.0,
                        step=late_step,
                        format="%.2f",
                        key="late_ded_val",
                    )

                with ded_col2:
                    st.markdown(
                        '<p style="color: #ef5350; font-weight: 600;">❌ Absent Deduction</p>',
                        unsafe_allow_html=True,
                    )
                    abs_type_idx = (
                        0 if not existing or existing["absent_deduction_type"] == "fixed" else 1
                    )
                    abs_type = st.radio(
                        "Type",
                        ["fixed", "percentage"],
                        index=abs_type_idx,
                        key="abs_ded_type",
                        horizontal=True,
                    )
                    abs_label = "Amount (Rs.)" if abs_type == "fixed" else "Percentage (%)"
                    abs_value = st.number_input(
                        abs_label,
                        min_value=0.0,
                        value=float(existing["absent_deduction_value"]) if existing else 0.0,
                        step=50.0 if abs_type == "fixed" else 1.0,
                        format="%.2f",
                        key="abs_ded_val",
                    )

                st.markdown("")
                bc1, bc2 = st.columns([3, 1])
                with bc1:
                    if st.button("💾 Save Salary Settings", type="primary", key="save_sal_btn"):
                        if base_salary <= 0:
                            st.error("Base salary must be greater than 0.")
                        else:
                            upsert_salary_settings(
                                emp_id, base_salary,
                                late_type, late_value,
                                abs_type, abs_value,
                                "fixed", 0.0,
                            )
                            st.success(
                                f"✅ Salary settings saved for **{selected}**!"
                            )
                            st.rerun()
                with bc2:
                    if existing and st.button(
                        "🗑️ Remove Settings", key="del_sal_btn"
                    ):
                        delete_salary_settings(emp_id)
                        st.warning("Salary settings removed.")
                        st.rerun()

            # ── View All ──────────────────────────────────────────────
            with salary_tabs[1]:
                all_sal = get_all_salary_settings()
                if not all_sal:
                    st.info("No salary settings configured yet.")
                else:
                    df_sal = pd.DataFrame(all_sal)
                    display_cols = [
                        "employee_name", "base_salary",
                        "late_deduction_type", "late_deduction_value",
                        "absent_deduction_type", "absent_deduction_value",
                    ]
                    df_display = df_sal[
                        [c for c in display_cols if c in df_sal.columns]
                    ].copy()
                    df_display.columns = [
                        "Employee", "Base Salary",
                        "Late Type", "Late Value",
                        "Absent Type", "Absent Value",
                    ]
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION 3: RELAXATION WAIVERS
    # ══════════════════════════════════════════════════════════════════════════
    with sections[2]:
        st.markdown("#### 🕊️ Relaxation & Waiver Settings")

        relax_tabs = st.tabs([
            "📅 Monthly Waivers (Global)",
            "📌 Date-Specific Relaxation",
        ])

        # ── Monthly Waivers ───────────────────────────────────────
        with relax_tabs[0]:
            st.markdown(
                "Set global monthly waivers that apply to **all employees**. "
                "These free passes are deducted before salary penalties kick in."
            )

            relax = get_relaxation_settings()

            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #1a1a2e, #16213e);
                    border: 1px solid #0f3460;
                    border-radius: 12px;
                    padding: 20px;
                    margin: 12px 0;
                ">
                    <h5 style="color: #4fc3f7; margin: 0 0 8px;">
                        🎟️ Monthly Free Passes
                    </h5>
                    <p style="color: #aaa; font-size: 0.85rem; margin: 0;">
                        These many late occurrences per month will NOT
                        attract any salary deduction.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            rc1, rc2 = st.columns(2)
            with rc1:
                grace_min = st.number_input(
                    "🕐 Daily Grace Minutes (Extra)",
                    min_value=0, max_value=120,
                    value=int(relax["daily_grace_minutes"]),
                    help="Extra minutes of grace added on top of Present threshold",
                    key="grace_min_input",
                )
            with rc2:
                late_waivers = st.number_input(
                    "⏰ Free Late Days / Month",
                    min_value=0, max_value=30,
                    value=int(relax["monthly_late_waivers"]),
                    help="Late days waived (no deduction) per month",
                    key="late_waiver_input",
                )

            if st.button("💾 Save Monthly Waivers", type="primary", key="save_relax_btn"):
                upsert_relaxation_settings(grace_min, late_waivers, 0)
                st.success("✅ Monthly relaxation waivers updated!")
                st.rerun()

        # ── Date-Specific Relaxation ──────────────────────────────
        with relax_tabs[1]:
            st.markdown(
                "Add relaxation for **specific dates** — holidays, special events, "
                "or admin-granted grace for a particular day."
            )

            add_col, view_col = st.columns([1, 1])

            with add_col:
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #1a1a2e, #16213e);
                        border: 1px solid #0f3460;
                        border-radius: 12px;
                        padding: 16px 20px;
                        margin-bottom: 12px;
                    ">
                        <h5 style="color: #81c784; margin: 0;">
                            ➕ Add Date Relaxation
                        </h5>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                relax_date = st.date_input(
                    "Date",
                    value=datetime.date.today(),
                    key="relax_date_input",
                )
                relax_type = st.selectbox(
                    "Relaxation Type",
                    [
                        ("full_day_off", "🏖️ Full Day Off — no attendance needed"),
                        ("no_deduction", "🛡️ No Deduction — attendance counted but no penalty"),
                        ("extra_grace", "⏱️ Extra Grace — additional grace minutes for this day"),
                    ],
                    format_func=lambda x: x[1],
                    key="relax_type_select",
                )
                extra_grace = 0
                if relax_type[0] == "extra_grace":
                    extra_grace = st.number_input(
                        "Extra Grace Minutes",
                        min_value=1, max_value=240,
                        value=30,
                        key="extra_grace_input",
                    )
                relax_note = st.text_input(
                    "Note (optional)",
                    placeholder="e.g., Eid holiday, rain day …",
                    key="relax_note_input",
                )

                if st.button("➕ Add Relaxation Date", type="primary", key="add_relax_date_btn"):
                    add_relaxation_date(
                        relax_date, relax_type[0], extra_grace, relax_note
                    )
                    st.success(
                        f"✅ Relaxation added for **{relax_date.strftime('%d %b %Y')}**!"
                    )
                    st.rerun()

            with view_col:
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #1a1a2e, #16213e);
                        border: 1px solid #0f3460;
                        border-radius: 12px;
                        padding: 16px 20px;
                        margin-bottom: 12px;
                    ">
                        <h5 style="color: #ffb74d; margin: 0;">
                            📋 Active Relaxation Dates
                        </h5>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                existing_dates = get_relaxation_dates()
                if not existing_dates:
                    st.info("No date-specific relaxations set.")
                else:
                    for rd in existing_dates:
                        d = rd["date"]
                        date_str = d.strftime("%d %b %Y") if isinstance(d, datetime.date) else str(d)
                        type_emoji = {
                            "full_day_off": "🏖️",
                            "no_deduction": "🛡️",
                            "extra_grace": "⏱️",
                        }
                        emoji = type_emoji.get(rd["relaxation_type"], "📅")
                        label = rd["relaxation_type"].replace("_", " ").title()
                        note_str = f" — {rd['note']}" if rd.get("note") else ""

                        dc1, dc2 = st.columns([4, 1])
                        with dc1:
                            extra_info = ""
                            if rd["relaxation_type"] == "extra_grace":
                                extra_info = f" (+{rd['extra_grace_minutes']}min)"
                            st.markdown(
                                f"**{date_str}** &nbsp; {emoji} {label}{extra_info}{note_str}"
                            )
                        with dc2:
                            if st.button(
                                "🗑️", key=f"del_rd_{rd['id']}",
                                help=f"Remove relaxation for {date_str}",
                            ):
                                delete_relaxation_date(d)
                                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION 4: PAYROLL CALCULATOR
    # ══════════════════════════════════════════════════════════════════════════
    with sections[3]:
        st.markdown("#### 📊 Monthly Payroll Calculator")
        st.markdown(
            "Select an employee and month to calculate their net salary "
            "after deductions, waivers, and relaxation adjustments."
        )

        pc1, pc2, pc3 = st.columns(3)

        df_emp_pay = _load_employees()
        if df_emp_pay.empty:
            st.info("No employees found.")
        else:
            with pc1:
                pay_options = {
                    f"#{row['id']}  {row['name']}": row["id"]
                    for _, row in df_emp_pay.iterrows()
                }
                pay_selected = st.selectbox(
                    "Employee", list(pay_options.keys()), key="pay_emp_select"
                )
                pay_emp_id = pay_options[pay_selected]

            with pc2:
                today = datetime.date.today()
                pay_month = st.selectbox(
                    "Month",
                    list(range(1, 13)),
                    index=today.month - 1,
                    format_func=lambda m: calendar.month_name[m],
                    key="pay_month_select",
                )

            with pc3:
                pay_year = st.number_input(
                    "Year",
                    min_value=2020,
                    max_value=2030,
                    value=today.year,
                    key="pay_year_input",
                )

            if st.button("🧮 Calculate Payroll", type="primary", key="calc_payroll_btn"):
                result = compute_monthly_payroll(pay_emp_id, pay_year, pay_month)

                if "error" in result:
                    st.error(f"⚠️ {result['error']}")
                else:
                    # ── Summary Cards ─────────────────────────────────
                    st.markdown("---")
                    st.markdown(
                        f"##### 💰 Payroll Summary — "
                        f"{calendar.month_name[pay_month]} {pay_year}"
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("💵 Base Salary", _format_currency(result["base_salary"]))
                    m2.metric(
                        "📉 Total Deductions",
                        _format_currency(result["total_deductions"]),
                    )
                    m3.metric(
                        "💰 Net Salary",
                        _format_currency(result["net_salary"]),
                        delta=f"-{_format_currency(result['total_deductions'])}",
                        delta_color="inverse",
                    )
                    m4.metric(
                        "📅 Daily Rate",
                        _format_currency(result["daily_salary"]),
                    )

                    # ── Attendance Breakdown ──────────────────────────
                    st.markdown("---")
                    st.markdown("##### 📋 Attendance Breakdown")

                    a1, a2, a3 = st.columns(3)
                    a1.metric("✅ Present Days", result["present_days"])
                    a2.metric(
                        "⏰ Late Days",
                        result["late_days"],
                        delta=f"-{result['waived_late']} waived"
                        if result["waived_late"] > 0
                        else None,
                        delta_color="off",
                    )
                    a3.metric("❌ Absent Days", result["absent_days"])

                    # ── Deduction Details ─────────────────────────────
                    st.markdown("---")
                    st.markdown("##### 💸 Deduction Details")

                    d1, d2 = st.columns(2)
                    d1.metric(
                        f"⏰ Late ({result['billable_late']} billable)",
                        _format_currency(result["late_deduction"]),
                    )
                    d2.metric(
                        f"❌ Absent ({result['billable_absent']} days)",
                        _format_currency(result["absent_deduction"]),
                    )

                    # ── Relaxation dates applied ──────────────────────
                    if result["relaxation_dates_applied"]:
                        st.markdown("---")
                        st.markdown("##### 🕊️ Relaxation Dates Applied")
                        for rd in result["relaxation_dates_applied"]:
                            d_str = rd.strftime("%d %b %Y") if isinstance(rd, datetime.date) else str(rd)
                            st.markdown(f"• **{d_str}** — Relaxation waiver applied")

                    # ── Daily Breakdown Table ─────────────────────────
                    if result["daily_breakdown"]:
                        st.markdown("---")
                        st.markdown("##### 📅 Day-by-Day Breakdown")

                        breakdown_data = []
                        for entry in result["daily_breakdown"]:
                            d = entry["date"]
                            date_str = (
                                d.strftime("%d %b (%a)")
                                if isinstance(d, datetime.date)
                                else str(d)
                            )
                            breakdown_data.append({
                                "Date": date_str,
                                "Status": entry["status"],
                                "Deduction": _format_currency(float(entry["deduction"])) if entry.get("deduction") else "Rs. 0.00",
                                "Note": entry.get("note", ""),
                            })

                        df_bd = pd.DataFrame(breakdown_data)
                        st.dataframe(
                            df_bd,
                            use_container_width=True,
                            hide_index=True,
                            height=min(len(df_bd) * 35 + 38, 600),
                        )

                    # ── Final Net Salary Box ──────────────────────────
                    st.markdown(
                        f"""
                        <div style="
                            background: linear-gradient(135deg, #1b5e20, #2e7d32);
                            border-radius: 12px;
                            padding: 24px;
                            margin-top: 16px;
                            text-align: center;
                            border: 1px solid #4caf50;
                        ">
                            <h3 style="color: #fff; margin: 0 0 8px;">
                                💰 Net Payable Salary
                            </h3>
                            <h1 style="color: #c8e6c9; margin: 0; font-size: 2.5rem;">
                                {_format_currency(result['net_salary'])}
                            </h1>
                            <p style="color: #a5d6a7; margin: 8px 0 0; font-size: 0.9rem;">
                                Base {_format_currency(result['base_salary'])}
                                — Deductions {_format_currency(result['total_deductions'])}
                            </p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
