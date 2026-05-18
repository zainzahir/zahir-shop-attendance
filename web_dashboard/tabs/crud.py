"""
tabs/crud.py — Employee CRUD Management Portal Tab
Provides Create / Read / Update / Delete operations on the employees table.
"""

import re
import pandas as pd
import streamlit as st

from db import run_query


# ─── Validation helpers (mirrors local_client/validators.py) ──────────────────
def _validate_name(v: str) -> str | None:
    v = v.strip()
    if not v:
        return "Full Name is required."
    if not re.fullmatch(r"[A-Za-z\s]+", v):
        return "Name must contain only letters and spaces."
    return None

def _validate_cnic(v: str) -> str | None:
    v = v.strip()
    if not v:
        return "CNIC is required."
    digits = re.sub(r"\D", "", v)
    if len(digits) != 13:
        return "CNIC must be exactly 13 digits."
    return None

def _format_cnic(v: str) -> str:
    digits = re.sub(r"\D", "", v.strip())
    if len(digits) >= 13:
        return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"
    return v.strip()

def _validate_phone(v: str) -> str | None:
    v = v.strip()
    if not v:
        return "Phone number is required."
    digits = re.sub(r"\D", "", v)
    if len(digits) != 11:
        return "Phone must be exactly 11 digits."
    return None

def _validate_address(v: str) -> str | None:
    v = v.strip()
    if not v:
        return "Address is required."
    if not re.fullmatch(r"[A-Za-z0-9\s,/\#.\-]+", v):
        return "Address contains invalid characters."
    return None


def _run_all_validations(name, cnic, phone, address) -> list[str]:
    """Return a list of error messages. Empty list = all valid."""
    errors = []
    for fn, val in [
        (_validate_name,    name),
        (_validate_cnic,    cnic),
        (_validate_phone,   phone),
        (_validate_address, address),
    ]:
        err = fn(val)
        if err:
            errors.append(err)
    return errors


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _reload_employees(search: str = "") -> pd.DataFrame:
    sql = """
        SELECT id, name, cnic, phone, address, enrollment_status, created_at::TEXT
        FROM   employees
        WHERE  name ILIKE %s OR cnic ILIKE %s OR phone ILIKE %s
        ORDER  BY id DESC;
    """
    pattern = f"%{search}%"
    rows    = run_query(sql, (pattern, pattern, pattern))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ─── Main Render ──────────────────────────────────────────────────────────────
def render():
    st.subheader("👥 Employee Management Portal")

    op_tabs = st.tabs(["➕ Add Employee", "📋 View & Search", "✏️ Edit", "🗑️ Delete"])

    # ── CREATE ────────────────────────────────────────────────────────────────
    with op_tabs[0]:
        st.markdown("#### Add New Employee Profile")
        st.info(
            "Fingerprint will be enrolled later via the **local desktop client**. "
            "The record is created with status `pending_local_enrollment`."
        )
        with st.form("add_employee_form", clear_on_submit=True):
            name    = st.text_input("Full Name *", help="Only letters and spaces")
            cnic    = st.text_input("CNIC *", help="XXXXX-XXXXXXX-X  (13 digits)")
            phone   = st.text_input("Phone Number *", help="11 digits, e.g. 03001234567")
            address = st.text_area("Address *", height=80, help="Street, area, city")
            submitted = st.form_submit_button("💾 Save Employee")

        if submitted:
            errors = _run_all_validations(name, cnic, phone, address)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                formatted_cnic = _format_cnic(cnic)
                clean_phone = re.sub(r"\D", "", phone.strip())
                run_query(
                    """
                    INSERT INTO employees (name, cnic, phone, address,
                                          enrollment_status)
                    VALUES (%s, %s, %s, %s, 'pending_local_enrollment');
                    """,
                    (name.strip(), formatted_cnic,
                     clean_phone, address.strip()),
                    fetch=False,
                )
                st.success(f"✅ Employee **{name.strip()}** added. Visit the shop PC to enroll their fingerprint.")

    # ── READ ──────────────────────────────────────────────────────────────────
    with op_tabs[1]:
        st.markdown("#### Employee Records")
        search = st.text_input("🔍 Search by name, CNIC, or phone", placeholder="Type to filter …")
        df = _reload_employees(search)

        if df.empty:
            st.info("No employees found.")
        else:
            st.markdown(f"**{len(df)} record(s) found**")
            st.dataframe(
                df.rename(columns={
                    "id": "ID", "name": "Name", "cnic": "CNIC",
                    "phone": "Phone", "address": "Address",
                    "enrollment_status": "Status", "created_at": "Joined"
                }),
                use_container_width=True,
                hide_index=True,
            )
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Export CSV", csv, "employees.csv", "text/csv"
            )

    # ── UPDATE ────────────────────────────────────────────────────────────────
    with op_tabs[2]:
        st.markdown("#### Edit Employee Details")
        df_all = _reload_employees()

        if df_all.empty:
            st.info("No employees in the database.")
        else:
            options = {f"#{row['id']}  {row['name']}": row['id']
                       for _, row in df_all.iterrows()}
            selected_label = st.selectbox("Select Employee", list(options.keys()))
            emp_id         = options[selected_label]

            emp_row = df_all[df_all["id"] == emp_id].iloc[0]

            with st.form("edit_employee_form"):
                new_name    = st.text_input("Full Name *",    value=emp_row["name"])
                new_cnic    = st.text_input("CNIC *",         value=emp_row["cnic"]  or "")
                new_phone   = st.text_input("Phone *",        value=emp_row["phone"] or "")
                new_address = st.text_area("Address *", height=80, value=emp_row["address"] or "")
                save_btn    = st.form_submit_button("💾 Update Record")

            if save_btn:
                errors = _run_all_validations(new_name, new_cnic, new_phone, new_address)
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    formatted_cnic = _format_cnic(new_cnic)
                    clean_phone = re.sub(r"\D", "", new_phone.strip())
                    run_query(
                        """
                        UPDATE employees
                        SET    name    = %s,
                               cnic    = %s,
                               phone   = %s,
                               address = %s
                        WHERE  id = %s;
                        """,
                        (new_name.strip(), formatted_cnic,
                         clean_phone, new_address.strip(),
                         emp_id),
                        fetch=False,
                    )
                    st.success(f"✅ Employee #{emp_id} updated successfully.")

    # ── DELETE ────────────────────────────────────────────────────────────────
    with op_tabs[3]:
        st.markdown("#### Remove Employee")
        st.warning(
            "⚠️ Deleting an employee will also permanently remove all their "
            "attendance logs (CASCADE). This action cannot be undone.",
            icon="⚠️",
        )
        df_del = _reload_employees()

        if df_del.empty:
            st.info("No employees in the database.")
        else:
            del_options = {f"#{row['id']}  {row['name']}": row['id']
                           for _, row in df_del.iterrows()}
            del_label   = st.selectbox("Select Employee to Delete", list(del_options.keys()))
            del_id      = del_options[del_label]
            confirmed   = st.checkbox(
                f"I confirm I want to permanently delete **{del_label}** and all their records."
            )
            del_btn = st.button("🗑️ Delete Employee", type="primary", disabled=not confirmed)

            if del_btn and confirmed:
                run_query(
                    "DELETE FROM employees WHERE id = %s;",
                    (del_id,),
                    fetch=False,
                )
                st.error(f"Employee **{del_label}** has been deleted.")
                st.rerun()
