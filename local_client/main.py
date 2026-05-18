"""
main.py — Zahir Shop Digital Attendance System  (Local Desktop Client)
=======================================================================
UI Framework : CustomTkinter (dark-blue theme)
Scanner      : Suprema BioMini Slim 2 via BS_SDK_V2.dll (scanner.py)
Database     : Supabase PostgreSQL (db.py)
Audio        : winsound (audio.py)

Run from the local_client/ directory:
    python main.py
"""

import datetime
import logging
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import audio
import db
from config import (
    APP_TITLE, CTK_THEME,
    SHIFT_START,
    PRESENT_MAX_MINUTES, LATE_MAX_MINUTES, HALF_DAY_MAX_MINUTES,
)
from scanner import BioStarSDK
from validators import validate_name, validate_cnic, validate_phone, validate_address

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ─── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme(CTK_THEME)

# ─── Status Computation ───────────────────────────────────────────────────────
def compute_status(check_in: datetime.time) -> str:
    """
    Compare *check_in* against the SHIFT_START constant and return one of:
    'Present' | 'Late' | 'Half Day'
    """
    today     = datetime.date.today()
    dt_checkin = datetime.datetime.combine(today, check_in)
    dt_shift   = datetime.datetime.combine(today, SHIFT_START)
    delta_min  = (dt_checkin - dt_shift).total_seconds() / 60

    if delta_min <= PRESENT_MAX_MINUTES:
        return "Present"
    elif delta_min <= LATE_MAX_MINUTES:
        return "Late"
    else:
        return "Half Day"


# ═══════════════════════════════════════════════════════════════════════════════
#  ENROLLMENT TAB — Registration Form + Pending Section + Verified Section
# ═══════════════════════════════════════════════════════════════════════════════
class EnrollmentTab(ctk.CTkScrollableFrame):
    """Three-section enrollment UI with validation."""

    def __init__(self, master, sdk: BioStarSDK, **kwargs):
        super().__init__(master, **kwargs)
        self.sdk = sdk
        self.columnconfigure(0, weight=1)
        self._build_ui()

    # ══════════════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        row = 0

        # ── Section 1: Registration Form ─────────────────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 0))
        ctk.CTkLabel(
            header_frame, text="📝  Register New Employee",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header_frame,
            text="All fields are required. Fingerprint will be enrolled separately below.",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(anchor="w")
        row += 1

        form_frame = ctk.CTkFrame(self, corner_radius=10)
        form_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 4))
        form_frame.columnconfigure(1, weight=1)

        fields = [
            ("Full Name *",    "name",    "Only letters and spaces"),
            ("CNIC *",         "cnic",    "XXXXX-XXXXXXX-X  (13 digits)"),
            ("Phone *",        "phone",   "11 digits, e.g. 03001234567"),
            ("Address *",      "address", "Street, area, city"),
        ]
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._string_vars: dict[str, tk.StringVar] = {}
        self._error_labels: dict[str, ctk.CTkLabel] = {}
        self._default_border = "#565B5E"   # default CTk border colour
        self._suppress_trace = False       # prevents recursive trace calls

        for i, (label, key, placeholder) in enumerate(fields):
            ctk.CTkLabel(form_frame, text=label, anchor="w",
                         font=ctk.CTkFont(size=13)).grid(
                row=i * 2, column=0, padx=(12, 6), pady=(8, 0), sticky="w"
            )
            sv = tk.StringVar()
            entry = ctk.CTkEntry(
                form_frame, width=300,
                placeholder_text=placeholder,
                font=ctk.CTkFont(size=13),
                textvariable=sv,
            )
            entry.grid(row=i * 2, column=1, padx=(0, 12), pady=(8, 0), sticky="ew")
            self._entries[key] = entry
            self._string_vars[key] = sv

            err_lbl = ctk.CTkLabel(
                form_frame, text="", text_color="#F44336",
                font=ctk.CTkFont(size=11), anchor="w",
            )
            err_lbl.grid(row=i * 2 + 1, column=1, padx=(0, 12), sticky="w")
            self._error_labels[key] = err_lbl

        # ── Real-time input filters ──
        self._string_vars["name"].trace_add("write", self._filter_name)
        self._string_vars["cnic"].trace_add("write", self._filter_cnic)
        self._string_vars["phone"].trace_add("write", self._filter_phone)

        row += 1

        # Save Profile button
        self.save_btn = ctk.CTkButton(
            self, text="💾  Save Profile",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            command=self._save_profile,
        )
        self.save_btn.grid(row=row, column=0, pady=(8, 12), padx=10)
        row += 1

        # ── Separator ────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color="#444").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1

        # ── Section 2: Pending Verification ──────────────────────────────────
        pending_header = ctk.CTkFrame(self, fg_color="transparent")
        pending_header.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            pending_header, text="⏳  Pending Biometric Verification",
            font=ctk.CTkFont(size=18, weight="bold"), text_color="#FFA500",
        ).pack(side="left")
        ctk.CTkButton(
            pending_header, text="🔄", width=36, height=30,
            command=self._reload_lists,
            font=ctk.CTkFont(size=14),
        ).pack(side="right", padx=4)
        row += 1

        self.pending_container = ctk.CTkFrame(self, corner_radius=8)
        self.pending_container.grid(row=row, column=0, sticky="ew", padx=10, pady=(4, 8))
        self.pending_container.columnconfigure(0, weight=1)
        row += 1

        # ── Separator ────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color="#444").grid(
            row=row, column=0, sticky="ew", padx=10, pady=4
        )
        row += 1

        # ── Section 3: Verified Employees ────────────────────────────────────
        verified_header = ctk.CTkFrame(self, fg_color="transparent")
        verified_header.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            verified_header, text="✅  Verified Employees",
            font=ctk.CTkFont(size=18, weight="bold"), text_color="#4CAF50",
        ).pack(side="left")
        row += 1

        self.verified_container = ctk.CTkFrame(self, corner_radius=8)
        self.verified_container.grid(row=row, column=0, sticky="ew", padx=10, pady=(4, 12))
        self.verified_container.columnconfigure(0, weight=1)
        row += 1

        # ── Status / progress for enrollment ─────────────────────────────────
        self.status_var = tk.StringVar(value="")
        self.status_lbl = ctk.CTkLabel(
            self, textvariable=self.status_var,
            font=ctk.CTkFont(size=13), text_color="gray", wraplength=500,
        )
        self.status_lbl.grid(row=row, column=0, pady=(0, 4), padx=10)
        row += 1

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", width=360)
        self.progress.grid(row=row, column=0, pady=(0, 8), padx=10)
        self.progress.grid_remove()

        # Initial data load
        self._reload_lists()

    # ══════════════════════════════════════════════════════════════════════════
    #  VALIDATION + SAVE PROFILE
    # ══════════════════════════════════════════════════════════════════════════
    def _clear_errors(self):
        for key in self._error_labels:
            self._error_labels[key].configure(text="")
            self._entries[key].configure(border_color=self._default_border)

    def _show_error(self, key: str, msg: str):
        self._error_labels[key].configure(text=msg)
        self._entries[key].configure(border_color="#F44336")

    # ── Real-time input filters ───────────────────────────────────────────────
    def _filter_name(self, *_args):
        """Block any non-letter / non-space characters as the user types."""
        if self._suppress_trace:
            return
        sv = self._string_vars["name"]
        current = sv.get()
        import re
        filtered = re.sub(r"[^A-Za-z\s]", "", current)
        if filtered != current:
            self._suppress_trace = True
            sv.set(filtered)
            self._suppress_trace = False

    def _filter_cnic(self, *_args):
        """Only digits allowed; auto-insert hyphens at positions 5 and 12."""
        if self._suppress_trace:
            return
        sv = self._string_vars["cnic"]
        current = sv.get()
        import re
        digits = re.sub(r"\D", "", current)[:13]  # max 13 digits
        # Build formatted string with hyphens
        formatted = ""
        for i, d in enumerate(digits):
            if i == 5 or i == 12:
                formatted += "-"
            formatted += d
        if formatted != current:
            self._suppress_trace = True
            sv.set(formatted)
            # Move cursor to end
            self._entries["cnic"].icursor(len(formatted))
            self._suppress_trace = False

    def _filter_phone(self, *_args):
        """Only digits allowed, max 11."""
        if self._suppress_trace:
            return
        sv = self._string_vars["phone"]
        current = sv.get()
        import re
        filtered = re.sub(r"\D", "", current)[:11]  # max 11 digits
        if filtered != current:
            self._suppress_trace = True
            sv.set(filtered)
            self._suppress_trace = False

    def _save_profile(self):
        self._clear_errors()
        all_valid = True

        ok, result = validate_name(self._entries["name"].get())
        if not ok:
            self._show_error("name", result); all_valid = False
        else:
            name = result

        ok, result = validate_cnic(self._entries["cnic"].get())
        if not ok:
            self._show_error("cnic", result); all_valid = False
        else:
            cnic = result

        ok, result = validate_phone(self._entries["phone"].get())
        if not ok:
            self._show_error("phone", result); all_valid = False
        else:
            phone = result

        ok, result = validate_address(self._entries["address"].get())
        if not ok:
            self._show_error("address", result); all_valid = False
        else:
            address = result

        if not all_valid:
            return

        # All valid → save to DB
        try:
            emp_id = db.insert_employee_profile(name, cnic, phone, address)
            messagebox.showinfo(
                "Profile Saved",
                f"✅ {name} registered (ID #{emp_id}).\n"
                "Now enroll their fingerprint from the list below."
            )
            for e in self._entries.values():
                e.delete(0, "end")
            self._reload_lists()
        except Exception as exc:
            logger.error(f"Save profile error: {exc}")
            messagebox.showerror("Database Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    #  EMPLOYEE LIST RENDERING
    # ══════════════════════════════════════════════════════════════════════════
    def _reload_lists(self):
        self._render_pending_list()
        self._render_verified_list()

    def _render_pending_list(self):
        # Clear existing widgets
        for w in self.pending_container.winfo_children():
            w.destroy()

        try:
            pending = db.get_pending_employees()
        except Exception:
            pending = []

        if not pending:
            ctk.CTkLabel(
                self.pending_container,
                text="  No pending employees. Register someone above!",
                font=ctk.CTkFont(size=13), text_color="gray",
            ).grid(row=0, column=0, padx=12, pady=10, sticky="w")
            return

        for i, emp in enumerate(pending):
            row_frame = ctk.CTkFrame(
                self.pending_container,
                fg_color="#2B2B2B" if i % 2 == 0 else "#333333",
                corner_radius=6,
            )
            row_frame.grid(row=i, column=0, sticky="ew", padx=6, pady=2)
            row_frame.columnconfigure(0, weight=1)

            info = f"{emp['name']}"
            if emp.get("cnic"):
                info += f"  •  {emp['cnic']}"
            if emp.get("phone"):
                info += f"  •  {emp['phone']}"

            ctk.CTkLabel(
                row_frame, text=info, anchor="w",
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

            ctk.CTkButton(
                row_frame, text="🖐 Enroll Biometrics",
                width=160, height=32,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#E65100", hover_color="#BF360C",
                command=lambda e=emp: self._start_biometric_enrollment(e),
            ).grid(row=0, column=1, padx=10, pady=8)

    def _render_verified_list(self):
        for w in self.verified_container.winfo_children():
            w.destroy()

        try:
            verified = db.get_verified_employees()
        except Exception:
            verified = []

        if not verified:
            ctk.CTkLabel(
                self.verified_container,
                text="  No verified employees yet.",
                font=ctk.CTkFont(size=13), text_color="gray",
            ).grid(row=0, column=0, padx=12, pady=10, sticky="w")
            return

        for i, emp in enumerate(verified):
            row_frame = ctk.CTkFrame(
                self.verified_container,
                fg_color="#1B3A1B" if i % 2 == 0 else "#1E421E",
                corner_radius=6,
            )
            row_frame.grid(row=i, column=0, sticky="ew", padx=6, pady=2)
            row_frame.columnconfigure(0, weight=1)

            info = f"{emp['name']}"
            if emp.get("cnic"):
                info += f"  •  {emp['cnic']}"
            if emp.get("phone"):
                info += f"  •  {emp['phone']}"

            ctk.CTkLabel(
                row_frame, text=info, anchor="w",
                font=ctk.CTkFont(size=13),
            ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

            ctk.CTkLabel(
                row_frame, text="✅ Verified",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#4CAF50",
            ).grid(row=0, column=1, padx=10, pady=8)

    # ══════════════════════════════════════════════════════════════════════════
    #  BIOMETRIC ENROLLMENT FLOW
    # ══════════════════════════════════════════════════════════════════════════
    def _start_biometric_enrollment(self, emp: dict):
        self._set_status(
            f"Place {emp['name']}'s thumb on scanner …", color="#FFA500"
        )
        self.progress.grid()
        self.progress.start()

        threading.Thread(
            target=self._biometric_worker,
            args=(emp["id"], emp["name"]),
            daemon=True,
        ).start()

    def _biometric_worker(self, emp_id: int, name: str):
        try:
            device_id    = self.sdk.search_and_connect()
            template_b64 = self.sdk.enroll_finger(device_id)
            db.update_employee_fingerprint(emp_id, template_b64)
            self.after(0, self._on_enroll_success, emp_id, name)
        except Exception as exc:
            logger.error(f"Biometric enrollment error: {exc}")
            self.after(0, self._on_enroll_error, str(exc))

    def _on_enroll_success(self, emp_id: int, name: str):
        self.progress.stop()
        self.progress.grid_remove()
        self._set_status(
            f"✅  {name} biometrics enrolled!  (ID #{emp_id})", color="#4CAF50"
        )
        audio.play_success()
        self._reload_lists()

    def _on_enroll_error(self, msg: str):
        self.progress.stop()
        self.progress.grid_remove()
        self._set_status(f"❌  {msg}", color="#F44336")
        audio.play_failure()

    def _set_status(self, text: str, color: str = "gray"):
        self.status_var.set(text)
        self.status_lbl.configure(text_color=color)


# ═══════════════════════════════════════════════════════════════════════════════
#  ATTENDANCE TAB
# ═══════════════════════════════════════════════════════════════════════════════
STATUS_COLORS = {
    "Present":  "#4CAF50",
    "Late":     "#FFA500",
    "Half Day": "#FF5722",
}

class AttendanceTab(ctk.CTkFrame):
    """
    Event-driven attendance loop.
    Waits for a finger press → identifies → logs → displays result.
    """

    def __init__(self, master, sdk: BioStarSDK, **kwargs):
        super().__init__(master, **kwargs)
        self.sdk      = sdk
        self._running = False
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Attendance Verification",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, pady=(20, 6))

        # Clock label
        self.clock_var = tk.StringVar()
        ctk.CTkLabel(
            self, textvariable=self.clock_var,
            font=ctk.CTkFont(size=14),
            text_color="gray",
        ).grid(row=1, column=0, pady=2)
        self._tick_clock()

        # Big status display
        self.name_var   = tk.StringVar(value="Waiting for finger …")
        self.status_var = tk.StringVar(value="")

        self.name_lbl = ctk.CTkLabel(
            self, textvariable=self.name_var,
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        self.name_lbl.grid(row=2, column=0, pady=(30, 4), padx=20)

        self.status_lbl = ctk.CTkLabel(
            self, textvariable=self.status_var,
            font=ctk.CTkFont(size=20),
        )
        self.status_lbl.grid(row=3, column=0, pady=4)

        # Finger icon / animation placeholder
        self.icon_lbl = ctk.CTkLabel(
            self, text="🖐", font=ctk.CTkFont(size=72)
        )
        self.icon_lbl.grid(row=4, column=0, pady=10)

        # Start / Stop button
        self.toggle_btn = ctk.CTkButton(
            self,
            text="▶  Start Attendance Loop",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            command=self._toggle_loop,
        )
        self.toggle_btn.grid(row=5, column=0, pady=(10, 20), padx=20)

        self.log_box = ctk.CTkTextbox(self, height=140, state="disabled")
        self.log_box.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 16))

    # ── Clock ─────────────────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.datetime.now().strftime("%A, %d %b %Y   %H:%M:%S")
        self.clock_var.set(now)
        self.after(1000, self._tick_clock)

    # ── Loop control ──────────────────────────────────────────────────────────
    def _toggle_loop(self):
        if self._running:
            self._running = False
            self.toggle_btn.configure(text="▶  Start Attendance Loop")
            self._set_display("Attendance loop stopped.", "", "gray")
        else:
            self._running = True
            self.toggle_btn.configure(text="⏹  Stop")
            self._set_display("Place thumb on scanner …", "", "gray")
            threading.Thread(target=self._attendance_loop, daemon=True).start()

    def _attendance_loop(self):
        """
        Continuously: connect → scan → identify → log → repeat.
        Runs until self._running is set to False.
        """
        try:
            device_id = self.sdk.search_and_connect()
            self.after(0, lambda: self._set_display(
                "Scanner ready. Place thumb …", "", "gray"
            ))
        except Exception as exc:
            self.after(0, lambda e=exc: self._set_display(
                f"Scanner error: {e}", "", "#F44336"
            ))
            self._running = False
            return

        while self._running:
            try:
                live_fp    = self.sdk.scan_fingerprint(device_id)
                templates  = db.get_all_templates()
                matched_id = self.sdk.identify(live_fp, templates, device_id)

                if matched_id is None:
                    self.after(0, self._on_no_match)
                else:
                    emp_name = db.get_employee_name(matched_id)
                    if db.already_logged_today(matched_id):
                        self.after(0, lambda n=emp_name: self._on_already_logged(n))
                    else:
                        check_in = datetime.datetime.now().time()
                        status   = compute_status(check_in)
                        db.log_attendance(matched_id, check_in, status)
                        self.after(0, lambda n=emp_name, s=status, t=check_in:
                                   self._on_match(n, s, t))
            except Exception as exc:
                logger.warning(f"Scan cycle error: {exc}")
                # Don't break the loop on transient errors (e.g. no finger yet)
                time.sleep(1)

    # ── UI Callbacks (must run on main thread via .after()) ───────────────────
    def _on_match(self, name: str, status: str, check_in: datetime.time):
        color = STATUS_COLORS.get(status, "#4CAF50")
        self._set_display(name, status, color)
        self._append_log(f"{check_in.strftime('%H:%M:%S')}  {name:<20}  {status}")
        audio.play_success()
        self.icon_lbl.configure(text="✅")
        self.after(3000, lambda: self.icon_lbl.configure(text="🖐"))

    def _on_no_match(self):
        self._set_display("No match found", "Unknown Finger", "#F44336")
        audio.play_failure()
        self.icon_lbl.configure(text="❌")
        self.after(2000, lambda: self.icon_lbl.configure(text="🖐"))

    def _on_already_logged(self, name: str):
        self._set_display(name, "Already logged today ✓", "#2196F3")
        audio.play_already_logged()
        self.icon_lbl.configure(text="ℹ️")
        self.after(2000, lambda: self.icon_lbl.configure(text="🖐"))

    def _set_display(self, name: str, status: str, color: str):
        self.name_var.set(name)
        self.status_var.set(status)
        self.name_lbl.configure(text_color=color)
        self.status_lbl.configure(text_color=color)

    def _append_log(self, line: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class AttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("700x750")
        self.resizable(True, True)

        self.sdk = BioStarSDK()
        self.sdk.open()          # Initialize SDK on startup

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)

        tabs.add("📋  Enrollment")
        tabs.add("✅  Attendance")

        EnrollmentTab(
            tabs.tab("📋  Enrollment"),
            sdk=self.sdk,
        ).pack(fill="both", expand=True)

        AttendanceTab(
            tabs.tab("✅  Attendance"),
            sdk=self.sdk,
        ).pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.sdk.close()
        self.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = AttendanceApp()
    app.mainloop()
