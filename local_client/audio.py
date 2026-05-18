"""
audio.py — Windows audio feedback helpers using the built-in winsound module.
No third-party dependencies required.
"""

import winsound
import threading
import logging

from config import SUCCESS_HZ, SUCCESS_MS, FAILURE_HZ, FAILURE_MS

logger = logging.getLogger(__name__)


def _beep(hz: int, ms: int) -> None:
    """Internal: emit a synchronous PC-speaker beep."""
    try:
        winsound.Beep(hz, ms)
    except RuntimeError as exc:
        # Beep() can fail on some systems without a speaker — non-fatal
        logger.warning(f"winsound.Beep failed: {exc}")


def play_success() -> None:
    """
    Play a short ascending two-tone chime in a background thread
    so the UI remains responsive during audio playback.

    Tone sequence: 800 Hz → 1 000 Hz (pleasant "ding-ding")
    """
    def _play():
        _beep(800,  150)
        _beep(SUCCESS_HZ, SUCCESS_MS)

    threading.Thread(target=_play, daemon=True).start()


def play_failure() -> None:
    """
    Play a low double-buzz to signal a failed match or scan error.
    Runs in a background thread.
    """
    def _play():
        _beep(FAILURE_HZ, FAILURE_MS)
        _beep(FAILURE_HZ, FAILURE_MS // 2)

    threading.Thread(target=_play, daemon=True).start()


def play_already_logged() -> None:
    """
    Play a gentle single mid-tone to indicate the employee
    has already been logged in today.
    """
    threading.Thread(
        target=lambda: _beep(600, 400), daemon=True
    ).start()
