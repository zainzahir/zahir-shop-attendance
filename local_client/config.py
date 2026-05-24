"""
config.py — Centralized configuration for the Local Attendance Client.
All paths, thresholds, and SDK constants are resolved here once.
"""

import os
import datetime
from dotenv import load_dotenv

# Load .env file (present in same directory as this script)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ─── DLL Paths ────────────────────────────────────────────────────────────────
# All three DLLs must sit in the same folder as this script.
_BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
BS2_DLL_PATH      = os.path.join(_BASE_DIR, "BS_SDK_V2.dll")
LIBCRYPTO_DLL     = os.path.join(_BASE_DIR, "libcrypto-1_1-x64.dll")
LIBSSL_DLL        = os.path.join(_BASE_DIR, "libssl-1_1-x64.dll")

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")          # postgresql://user:pass@host/db

# ─── Shift & Status Thresholds ────────────────────────────────────────────────
SHIFT_START = datetime.time(7, 30)   # 07:30 AM

#  Minutes late  │  Status
#  ─────────────────────────
#   0  –  15     │  Present
#  16  –  60     │  Late
#  61  – 240     │  Half Day
#  > 240         │  (Absent — not scanned, admin logs manually)
PRESENT_MAX_MINUTES  = 15
LATE_MAX_MINUTES     = 60
HALF_DAY_MAX_MINUTES = 240

# ─── Scanner / SDK ────────────────────────────────────────────────────────────
SCAN_TIMEOUT_MS      = 20_000   # ms to wait for a finger press (20 seconds)
TEMPLATE_FORMAT      = 2        # BS2_TEMPLATE_FORMAT_SUPREMA = 2
ENROLL_SCAN_COUNT    = 2        # capture 2 samples for reliable enrollment

# BS2Fingerprint struct sizes (from bs2_data.h)
BS2_FINGER_TEMPLATE_SIZE     = 384   # bytes per single template image
BS2_MAX_TEMPLATES_PER_FINGER = 2     # maximum templates stored per finger slot

# ─── UI / Audio ───────────────────────────────────────────────────────────────
APP_TITLE      = "Zahir Shop – Attendance System"
CTK_THEME      = "dark-blue"

SUCCESS_HZ, SUCCESS_MS = 1000, 300   # high-pitched chime on successful match
FAILURE_HZ, FAILURE_MS = 400,  600   # low-pitched buzz on failure / no match
