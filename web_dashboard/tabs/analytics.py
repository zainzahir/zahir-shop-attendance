"""
tabs/analytics.py — Real-time Analytics Dashboard Tab
Renders a Plotly pie chart, a 30-day trend line chart, and KPI metric cards.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import run_query

# Consistent colour map shared across both charts
STATUS_COLORS = {
    "Present":  "#4CAF50",
    "Late":     "#FFA500",
    "Half Day": "#FF5722",
    "Absent":   "#9E9E9E",
}


def render():
    st.subheader("📊 Today's Attendance  —  Live Overview")

    # ── KPI cards ─────────────────────────────────────────────────────────────
    rows = run_query("SELECT status, count FROM status_counts_today;")
    counts = {r["status"]: int(r["count"]) for r in rows} if rows else {}

    total_all = run_query("SELECT COUNT(*) AS n FROM employees;")
    total_all_count = int(total_all[0]["n"]) if total_all else 0

    total_enrolled = run_query(
        "SELECT COUNT(*) AS n FROM employees WHERE enrollment_status = 'enrolled';"
    )
    enrolled_count = int(total_enrolled[0]["n"]) if total_enrolled else 0
    
    # Absent count is based on enrolled_count (since pending users can't check in anyway)
    absent = enrolled_count - sum(counts.get(s, 0) for s in ["Present", "Late"])
    counts.setdefault("Absent", absent)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("👥 Total Employees", total_all_count, delta=f"{enrolled_count} With Fingerprint", delta_color="off")
    col2.metric("✅ Present",  counts.get("Present",  0))
    col3.metric("⏰ Late",     counts.get("Late",     0))
    col4.metric("❌ Absent",   counts.get("Absent",   0))

    st.divider()

    # ── Pie chart ─────────────────────────────────────────────────────────────
    left, right = st.columns(2)

    with left:
        st.markdown("#### Attendance Breakdown")
        if sum(counts.values()) == 0:
            st.info("No attendance data for today yet.")
        else:
            df_pie = pd.DataFrame(
                list(counts.items()), columns=["Status", "Count"]
            )
            fig_pie = px.pie(
                df_pie,
                names="Status",
                values="Count",
                color="Status",
                color_discrete_map=STATUS_COLORS,
                hole=0.45,
            )
            fig_pie.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="%{label}: %{value} employee(s)<extra></extra>",
            )
            fig_pie.update_layout(
                showlegend=True,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#FAFAFA",
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # ── 30-day trend line chart ────────────────────────────────────────────────
    with right:
        st.markdown("#### 30-Day Attendance Trend")
        trend_rows = run_query(
            "SELECT date, status, count FROM daily_attendance_trend;"
        )
        if not trend_rows:
            st.info("Not enough historical data yet.")
        else:
            df_trend = pd.DataFrame(trend_rows)
            df_trend["date"] = pd.to_datetime(df_trend["date"])
            df_trend["count"] = df_trend["count"].astype(int)

            fig_line = px.line(
                df_trend,
                x="date",
                y="count",
                color="status",
                color_discrete_map=STATUS_COLORS,
                markers=True,
                labels={"count": "Employees", "date": "Date", "status": "Status"},
            )
            fig_line.update_layout(
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#FAFAFA",
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="#333"),
                margin=dict(t=10, b=10, l=10, r=10),
            )
            st.plotly_chart(fig_line, use_container_width=True)

    # ── Today's detailed log table ─────────────────────────────────────────────
    st.divider()
    st.markdown("#### Today's Individual Records")
    detail = run_query(
        """
        SELECT employee_name, TO_CHAR(check_in_time, 'HH12:MI am') AS check_in_time, status
        FROM   today_summary
        ORDER  BY status, employee_name;
        """
    )
    if detail:
        df_detail = pd.DataFrame(detail)
        df_detail.columns = ["Name", "Check-In", "Status"]
        st.dataframe(df_detail, use_container_width=True, hide_index=True)
    else:
        st.info("No records for today.")

    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
