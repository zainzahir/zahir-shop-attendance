"""
scanner.py — ctypes Bridge for Suprema BioMini SDK (UFScanner.dll / UFMatcher.dll)
==================================================================================
Platform : Windows 64-bit (AMD64)
DLL conv  : __stdcall convention -> use ctypes.WinDLL
"""

import ctypes
import base64
import logging
import os
import sys
import time
from typing import Optional, List, Tuple

from config import SCAN_TIMEOUT_MS

logger = logging.getLogger(__name__)

# ─── BioMini SDK Error Codes & Constants ──────────────────────────────────────
UFS_OK = 0
UFS_PARAM_TIMEOUT = 201
UFS_TEMPLATE_TYPE_SUPREMA = 2001
MAX_TEMPLATE_SIZE = 1024

UFM_OK = 0
UFM_TEMPLATE_TYPE_SUPREMA = 2001

class BioMiniSDK:
    """
    Python wrapper around Suprema BioMini SDK DLLs.
    Exposes the same interface expected by main.py.
    """

    def __init__(self):
        self._h_scanner = None
        self._h_matcher = None
        self._scanner_lib = None
        self._matcher_lib = None
        self._device_idx = None

    def open(self) -> None:
        """Load DLLs, initialize scanner and matcher modules."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # Add base_dir to PATH so the DLL loader can find dependencies (like libeay32, ssleay32, NFIQ2)
        os.environ["PATH"] = base_dir + os.path.pathsep + os.environ["PATH"]

        scanner_dll = os.path.join(base_dir, "UFScanner.dll")
        matcher_dll = os.path.join(base_dir, "UFMatcher.dll")

        logger.info(f"Loading scanner DLL from: {scanner_dll}")
        logger.info(f"Loading matcher DLL from: {matcher_dll}")

        try:
            # WinDLL uses the __stdcall calling convention on Windows
            self._scanner_lib = ctypes.WinDLL(scanner_dll)
            self._matcher_lib = ctypes.WinDLL(matcher_dll)
        except Exception as e:
            logger.error(f"Failed to load BioMini SDK DLLs: {e}")
            raise RuntimeError(f"Failed to load BioMini SDK DLLs: {e}")

        # Bind functions with explicit argtypes and restype
        self._bind_functions()

        # Initialize Scanner Module
        ret = self._scanner_lib.UFS_Init()
        if ret != UFS_OK:
            raise RuntimeError(f"UFS_Init failed with status code {ret}")
        logger.info("UFScanner module initialized successfully.")

        # Create Matcher Instance
        h_matcher = ctypes.c_void_p(None)
        ret = self._matcher_lib.UFM_Create(ctypes.byref(h_matcher))
        if ret != UFM_OK:
            self._scanner_lib.UFS_Uninit()
            raise RuntimeError(f"UFM_Create failed with status code {ret}")
        self._h_matcher = h_matcher
        logger.info("UFMatcher instance created successfully.")

        # Set default matcher template type to SUPREMA
        self._matcher_lib.UFM_SetTemplateType(self._h_matcher, UFM_TEMPLATE_TYPE_SUPREMA)

    def close(self) -> None:
        """Clean up matcher and scanner resources."""
        if self._h_matcher and self._matcher_lib:
            try:
                self._matcher_lib.UFM_Delete(self._h_matcher)
            except Exception as e:
                logger.warning(f"Error deleting matcher: {e}")
            self._h_matcher = None
            logger.info("UFMatcher instance deleted.")

        if self._scanner_lib:
            try:
                self._scanner_lib.UFS_Uninit()
            except Exception as e:
                logger.warning(f"Error uninitializing scanner module: {e}")
            self._scanner_lib = None
            logger.info("UFScanner module uninitialized.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def _bind_functions(self) -> None:
        """Set argument and return types for the SDK functions."""
        # --- UFScanner.dll ---
        self._scanner_lib.UFS_Init.argtypes = []
        self._scanner_lib.UFS_Init.restype = ctypes.c_int

        self._scanner_lib.UFS_Uninit.argtypes = []
        self._scanner_lib.UFS_Uninit.restype = ctypes.c_int

        self._scanner_lib.UFS_GetScannerNumber.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self._scanner_lib.UFS_GetScannerNumber.restype = ctypes.c_int

        self._scanner_lib.UFS_GetScannerHandle.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        self._scanner_lib.UFS_GetScannerHandle.restype = ctypes.c_int

        self._scanner_lib.UFS_GetScannerID.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._scanner_lib.UFS_GetScannerID.restype = ctypes.c_int

        self._scanner_lib.UFS_SetParameter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self._scanner_lib.UFS_SetParameter.restype = ctypes.c_int

        self._scanner_lib.UFS_ClearCaptureImageBuffer.argtypes = [ctypes.c_void_p]
        self._scanner_lib.UFS_ClearCaptureImageBuffer.restype = ctypes.c_int

        self._scanner_lib.UFS_IsFingerOn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self._scanner_lib.UFS_IsFingerOn.restype = ctypes.c_int

        self._scanner_lib.UFS_CaptureSingleImage.argtypes = [ctypes.c_void_p]
        self._scanner_lib.UFS_CaptureSingleImage.restype = ctypes.c_int

        self._scanner_lib.UFS_ExtractEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int)
        ]
        self._scanner_lib.UFS_ExtractEx.restype = ctypes.c_int

        self._scanner_lib.UFS_SetTemplateType.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._scanner_lib.UFS_SetTemplateType.restype = ctypes.c_int

        self._scanner_lib.UFS_GetErrorString.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self._scanner_lib.UFS_GetErrorString.restype = ctypes.c_int

        # --- UFMatcher.dll ---
        self._matcher_lib.UFM_Create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self._matcher_lib.UFM_Create.restype = ctypes.c_int

        self._matcher_lib.UFM_Delete.argtypes = [ctypes.c_void_p]
        self._matcher_lib.UFM_Delete.restype = ctypes.c_int

        self._matcher_lib.UFM_SetTemplateType.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._matcher_lib.UFM_SetTemplateType.restype = ctypes.c_int

        self._matcher_lib.UFM_SetParameter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self._matcher_lib.UFM_SetParameter.restype = ctypes.c_int

        self._matcher_lib.UFM_Verify.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int)
        ]
        self._matcher_lib.UFM_Verify.restype = ctypes.c_int

        self._matcher_lib.UFM_GetErrorString.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self._matcher_lib.UFM_GetErrorString.restype = ctypes.c_int

    def search_and_connect(self) -> int:
        """
        Check for connected BioMini scanners, connect to the first one.
        Returns scanner index (0) or handle.
        """
        count = ctypes.c_int(0)
        ret = self._scanner_lib.UFS_GetScannerNumber(ctypes.byref(count))
        self._check_scanner(ret, "UFS_GetScannerNumber")

        if count.value == 0:
            raise RuntimeError("No BioMini scanner found. Ensure the device is plugged in.")

        h_scanner = ctypes.c_void_p(None)
        ret = self._scanner_lib.UFS_GetScannerHandle(0, ctypes.byref(h_scanner))
        self._check_scanner(ret, "UFS_GetScannerHandle")

        self._h_scanner = h_scanner
        self._device_idx = 0
        logger.info("Connected to BioMini scanner.")

        # Set Suprema template type for the scanner
        self._scanner_lib.UFS_SetTemplateType(self._h_scanner, UFS_TEMPLATE_TYPE_SUPREMA)

        # Set default timeout parameter from config (20 seconds)
        timeout_val = ctypes.c_int(SCAN_TIMEOUT_MS)
        self._scanner_lib.UFS_SetParameter(self._h_scanner, UFS_PARAM_TIMEOUT, ctypes.byref(timeout_val))

        return 0

    def scan_fingerprint(self, device_id: Optional[int] = None) -> Tuple[bytes, int]:
        """
        Wait for a finger press, capture the image, extract the template.
        Returns a tuple of (template_bytes, template_size).
        """
        if not self._h_scanner:
            raise RuntimeError("No scanner connected. Call search_and_connect() first.")

        logger.info("Clearing capture buffer and waiting for finger placement...")
        self._scanner_lib.UFS_ClearCaptureImageBuffer(self._h_scanner)

        # Blocks until finger is detected or timeout expires
        ret = self._scanner_lib.UFS_CaptureSingleImage(self._h_scanner)
        self._check_scanner(ret, "UFS_CaptureSingleImage")

        # Extract fingerprint template
        template_buf = (ctypes.c_ubyte * MAX_TEMPLATE_SIZE)()
        template_size = ctypes.c_int(0)
        quality = ctypes.c_int(0)

        ret = self._scanner_lib.UFS_ExtractEx(
            self._h_scanner,
            MAX_TEMPLATE_SIZE,
            template_buf,
            ctypes.byref(template_size),
            ctypes.byref(quality)
        )
        self._check_scanner(ret, "UFS_ExtractEx")

        logger.info(f"Scan completed. Size: {template_size.value}, Quality: {quality.value}")

        if quality.value < 40:
            raise RuntimeError("Fingerprint quality too low. Please place your finger flat and try again.")

        # Slice the buffer to the exact extracted size
        raw_template = bytes(template_buf)[:template_size.value]
        return raw_template, template_size.value

    def enroll_finger(self, device_id: Optional[int] = None) -> str:
        """
        Performs 2 scans for reliable enrollment.
        Returns the second (last) template serialized to a base64 string.
        """
        templates = []
        for i in range(2):
            logger.info(f"Enrollment scan {i+1}/2 — place finger...")
            template_bytes, size = self.scan_fingerprint(device_id)
            templates.append(template_bytes)
            
            if i == 0:
                logger.info("Please lift your finger...")
                self._wait_for_finger_release()

        # Serialize the last captured template to base64
        final_template = templates[-1]
        return base64.b64encode(final_template).decode("utf-8")

    def identify(
        self,
        live_fp: Tuple[bytes, int],
        stored_templates: List[Tuple[int, str]],
        device_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Compare live_fp (tuple of bytes and size) against all stored base64 templates.
        Returns the matched employee ID, or None if no match.
        """
        if not self._h_matcher:
            raise RuntimeError("Matcher module not initialized.")

        live_bytes, live_size = live_fp

        # Build ctypes buffer for live template
        live_buf = (ctypes.c_ubyte * len(live_bytes)).from_buffer_copy(live_bytes)

        for emp_id, b64_str in stored_templates:
            if not b64_str:
                continue
            try:
                stored_bytes = base64.b64decode(b64_str)
                stored_size = len(stored_bytes)
                stored_buf = (ctypes.c_ubyte * stored_size).from_buffer_copy(stored_bytes)

                verify_succeed = ctypes.c_int(0)
                ret = self._matcher_lib.UFM_Verify(
                    self._h_matcher,
                    live_buf,
                    live_size,
                    stored_buf,
                    stored_size,
                    ctypes.byref(verify_succeed)
                )
                if ret == UFM_OK and verify_succeed.value == 1:
                    logger.info(f"Match found! Matched Employee ID: {emp_id}")
                    return emp_id
            except Exception as e:
                logger.error(f"Error matching template for employee ID {emp_id}: {e}")

        logger.info("No match found.")
        return None

    def _wait_for_finger_release(self) -> None:
        """Wait until the finger is lifted off the scanner sensor."""
        if not self._h_scanner:
            return
        finger_on = ctypes.c_int(0)
        # Check every 100ms for up to 5 seconds
        for _ in range(50):
            ret = self._scanner_lib.UFS_IsFingerOn(self._h_scanner, ctypes.byref(finger_on))
            if ret != UFS_OK or finger_on.value == 0:
                break
            time.sleep(0.1)

    def _check_scanner(self, ret: int, fn_name: str) -> None:
        """Raise RuntimeError if any SDK function fails."""
        if ret != UFS_OK:
            buf = ctypes.create_string_buffer(256)
            try:
                self._scanner_lib.UFS_GetErrorString(ret, buf)
                err_msg = buf.value.decode("utf-8", errors="ignore")
            except Exception:
                err_msg = "Unknown error"
            raise RuntimeError(f"[{fn_name}] failed with status code {ret}: {err_msg}")

# Alias to BioStarSDK to maintain transparent drop-in compatibility with main.py
BioStarSDK = BioMiniSDK
