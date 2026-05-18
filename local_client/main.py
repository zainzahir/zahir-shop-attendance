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


# ─── Enrollment Tab ───────────────────────────────────────────────────────────
class EnrollmentTab(ctk.CTkFrame):
    """Form to capture personal details + scan + upload to Supabase."""

    def __init__(self, master, sdk: BioStarSDK, **kwargs):
        super().__init__(master, **kwargs)
        self.sdk = sdk
        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        ctk.CTkLabel(
            self, text="Employee Enrollment",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(20, 10), padx=20)

        # ── Form fields ──
        fields = [
            ("Full Name *",   "name"),
            ("CNIC",          "cnic"),
            ("Phone Number",  "phone"),
            ("Address",       "address"),
        ]
        self._entries: dict[str, ctk.CTkEntry] = {}

        for i, (label, key) in enumerate(fields, start=1):
            ctk.CTkLabel(self, text=label, anchor="w").grid(
                row=i, column=0, padx=(20, 8), pady=6, sticky="w"
            )
            entry = ctk.CTkEntry(self, width=300, placeholder_text=label)
            entry.grid(row=i, column=1, padx=(0, 20), pady=6, sticky="ew")
            self._entries[key] = entry

        self.columnconfigure(1, weight=1)

        # ── Status label ──
        self.status_var = tk.StringVar(value="Fill the form, then click Enroll Finger.")
        self.status_lbl = ctk.CTkLabel(
            self, textvariable=self.status_var,
            font=ctk.CTkFont(size=13),
            text_color="gray",
            wraplength=420,
        )
        self.status_lbl.grid(row=6, column=0, columnspan=2, pady=(10, 4), padx=20)

        # ── Progress bar (hidden until scanning) ──
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", width=360)
        self.progress.grid(row=7, column=0, columnspan=2, pady=4, padx=20)
        self.progress.grid_remove()

        # ── Enroll button ──
        self.enroll_btn = ctk.CTkButton(
            self,
            text="🖐  Enroll Finger",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=44,
            command=self._start_enrollment,
        )
        self.enroll_btn.grid(row=8, column=0, columnspan=2, pady=(12, 20), padx=20)

    # ── Enrollment flow ───────────────────────────────────────────────────────
    def _start_enrollment(self):
        name    = self._entries["name"].get().strip()
        cnic    = self._entries["cnic"].get().strip()
        phone   = self._entries["phone"].get().strip()
        address = self._entries["address"].get().strip()

        if not name:
            messagebox.showwarning("Missing Field", "Full Name is required.")
            return

        self.enroll_btn.configure(state="disabled")
        self._set_status("Place thumb on scanner …", color="#FFA500")
        self.progress.grid()
        self.progress.start()

        # Run in background thread to keep UI responsive
        threading.Thread(
            target=self._enrollment_worker,
            args=(name, cnic, phone, address),
            daemon=True,
        ).start()

    def _enrollment_worker(self, name, cnic, phone, address):
        try:
            device_id    = self.sdk.search_and_connect()
            template_b64 = self.sdk.enroll_finger(device_id)
            emp_id       = db.insert_employee(name, cnic, phone, address, template_b64)
            self.after(0, self._on_success, emp_id, name)
        except Exception as exc:
            logger.error(f"Enrollment error: {exc}")
            self.after(0, self._on_error, str(exc))

    def _on_success(self, emp_id: int, name: str):
        self.progress.stop()
        self.progress.grid_remove()
        self._set_status(
            f"✅  {name} enrolled successfully!  (ID #{emp_id})", color="#4CAF50"
        )
        audio.play_success()
        self.enroll_btn.configure(state="normal")
        for e in self._entries.values():
            e.delete(0, "end")

    def _on_error(self, msg: str):
        self.progress.stop()
        self.progress.grid_remove()
        self._set_status(f"❌  {msg}", color="#F44336")
        audio.play_failure()
        self.enroll_btn.configure(state="normal")

    def _set_status(self, text: str, color: str = "gray"):
        self.status_var.set(text)
        self.status_lbl.configure(text_color=color)


# ─── Attendance Tab ───────────────────────────────────────────────────────────
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


# ─── Main Application ─────────────────────────────────────────────────────────
class AttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x620")
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
