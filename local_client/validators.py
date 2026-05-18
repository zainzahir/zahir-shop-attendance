"""
validators.py — Front-end data validation for the Zahir Shop Attendance System.
All validators return (is_valid: bool, result_or_error: str).
  • On success: (True,  cleaned/formatted value)
  • On failure: (False, human-readable error message)
"""

import re
from typing import Tuple

# ─── Name ─────────────────────────────────────────────────────────────────────
def validate_name(value: str) -> Tuple[bool, str]:
    """Only letters and spaces, non-empty."""
    v = value.strip()
    if not v:
        return False, "Name is required."
    if not re.fullmatch(r"[A-Za-z\s]+", v):
        return False, "Name must contain only letters and spaces."
    return True, v


# ─── CNIC ─────────────────────────────────────────────────────────────────────
def format_cnic(digits: str) -> str:
    """Insert hyphens into a 13-digit string → XXXXX-XXXXXXX-X."""
    d = re.sub(r"\D", "", digits)
    if len(d) >= 13:
        return f"{d[:5]}-{d[5:12]}-{d[12]}"
    return d  # partial input, return as-is


def validate_cnic(value: str) -> Tuple[bool, str]:
    """Exactly 13 digits (hyphens stripped). Returns formatted XXXXX-XXXXXXX-X."""
    v = value.strip()
    if not v:
        return False, "CNIC is required."
    digits = re.sub(r"\D", "", v)
    if len(digits) != 13:
        return False, "CNIC must be exactly 13 digits."
    if not digits.isdigit():
        return False, "CNIC must contain only numbers."
    return True, format_cnic(digits)


# ─── Phone ────────────────────────────────────────────────────────────────────
def validate_phone(value: str) -> Tuple[bool, str]:
    """Exactly 11 digits, numeric only."""
    v = value.strip()
    if not v:
        return False, "Phone number is required."
    digits = re.sub(r"\D", "", v)
    if len(digits) != 11:
        return False, "Phone must be exactly 11 digits."
    return True, digits


# ─── Address ──────────────────────────────────────────────────────────────────
_ADDRESS_RE = re.compile(r"^[A-Za-z0-9\s,/\#.\-]+$")

def validate_address(value: str) -> Tuple[bool, str]:
    """Non-empty, alphanumeric + typical address punctuation."""
    v = value.strip()
    if not v:
        return False, "Address is required."
    if not _ADDRESS_RE.fullmatch(v):
        return False, "Address contains invalid characters. Use letters, numbers, spaces, commas, slashes, #, dots, or hyphens."
    return True, v
