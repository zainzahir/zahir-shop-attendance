"""
scanner.py — ctypes Bridge for Suprema BioStar 2 SDK  (BS_SDK_V2.dll)
======================================================================
Platform : Windows 64-bit (AMD64)
DLL conv  : C calling convention (__cdecl) → use ctypes.CDLL

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW ctypes PASSES VARIABLES TO A C DLL — QUICK REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. SCALAR TYPES
   Define .argtypes = [ctypes.c_uint32, ...] so ctypes auto-converts
   Python ints/floats to the right C type before the call.
   Define .restype  = ctypes.c_int  so the return value is read correctly.

2. OUTPUT POINTERS  (int*, void**)
   Create a ctypes variable, then pass it with ctypes.byref():
       device_id = ctypes.c_uint32(0)
       sdk.BS2_SomeFunc(ctx, ctypes.byref(device_id))
       result = device_id.value          # Python reads C-written value

3. STRUCTS  (ctypes.Structure)
   Mirror the C struct field-by-field with _fields_.  The order and types
   MUST match the C header exactly (padding included).
   Pass instances with ctypes.byref(my_struct).

4. RAW BYTE BUFFERS  (uint8_t*)
   ctypes.create_string_buffer(size) → mutable byte array.
   Pass it directly; ctypes converts it to char*/void* automatically.
   Read back with bytes(buf).

5. DOUBLE POINTER ARRAYS  (uint32_t**)
   Use ctypes.POINTER(ctypes.c_uint32)() and pass with byref().
   Iterate with array[i] syntax up to the returned count.
   Always call BS2_ReleaseMem() afterwards to avoid SDK memory leaks.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import ctypes
import base64
import logging
from typing import Optional, List, Tuple

from config import (
    BS2_DLL_PATH, LIBCRYPTO_DLL, LIBSSL_DLL,
    TEMPLATE_FORMAT, SCAN_TIMEOUT_MS, ENROLL_SCAN_COUNT,
    BS2_FINGER_TEMPLATE_SIZE, BS2_MAX_TEMPLATES_PER_FINGER,
)

logger = logging.getLogger(__name__)

# ─── SDK Error / Status Codes ─────────────────────────────────────────────────
BS_SDK_SUCCESS = 0

BS2_ERROR_MESSAGES = {
    0:      "Success",
    -1:     "Unknown error",
    -16:    "Device not found",
    -17:    "Device not connected",
    -32:    "Timeout — no finger detected",
    -33:    "Fingerprint quality too low, try again",
    -100:   "No matching fingerprint found",
    -114:   "License error — check UFLicense.dat / SDK activation",
}


def _sdk_msg(code: int) -> str:
    return BS2_ERROR_MESSAGES.get(code, f"SDK error code {code}")


# ─── ctypes Struct: BS2Fingerprint ────────────────────────────────────────────
# Mirrors bs2_data.h → BS2Fingerprint
#   Total size = 1+1+2 + (384*2) = 772 bytes
class BS2Fingerprint(ctypes.Structure):
    """
    C definition (bs2_data.h):
        typedef struct {
            uint8_t templateCount;                    // 1 or 2 templates stored
            uint8_t isEncrypted;                      // 1 = AES-encrypted
            uint8_t reserved[2];                      // alignment padding
            uint8_t data[BS2_FINGER_TEMPLATE_SIZE
                         * BS2_MAX_TEMPLATES_PER_FINGER];
        } BS2Fingerprint;
    """
    _fields_ = [
        ("templateCount", ctypes.c_uint8),
        ("isEncrypted",   ctypes.c_uint8),
        ("reserved",      ctypes.c_uint8 * 2),
        ("data",          ctypes.c_uint8 * (BS2_FINGER_TEMPLATE_SIZE
                                            * BS2_MAX_TEMPLATES_PER_FINGER)),
    ]


# ─── SDK Loader ───────────────────────────────────────────────────────────────
class BioStarSDK:
    """
    Thin wrapper around BS_SDK_V2.dll.

    Usage:
        with BioStarSDK() as sdk:
            device_id = sdk.connect_first_device()
            fp = sdk.scan_fingerprint(device_id)
            template_b64 = sdk.fingerprint_to_b64(fp)
    """

    def __init__(self):
        self._ctx    = ctypes.c_void_p(None)
        self._lib    = None
        self._device = None          # currently connected device ID

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def open(self) -> None:
        """Load DLL, allocate SDK context, and initialize."""
        # Pre-load SSL dependencies so the main DLL finds them
        ctypes.CDLL(LIBCRYPTO_DLL)
        ctypes.CDLL(LIBSSL_DLL)

        self._lib = ctypes.CDLL(BS2_DLL_PATH)
        logger.info("BS_SDK_V2.dll loaded successfully.")
        self._bind_functions()

        ret = self._lib.BS2_AllocateContext(ctypes.byref(self._ctx))
        self._check(ret, "BS2_AllocateContext")

        ret = self._lib.BS2_Initialize(self._ctx)
        self._check(ret, "BS2_Initialize")
        logger.info("SDK context initialized.")

    def close(self) -> None:
        """Disconnect device and release SDK context."""
        if self._device and self._lib:
            try:
                self._lib.BS2_DisconnectDevice(self._ctx, self._device)
            except Exception:
                pass
            self._device = None
        if self._lib and self._ctx:
            try:
                self._lib.BS2_ReleaseContext(self._ctx)
            except Exception:
                pass
        logger.info("SDK context released.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Function Binding ──────────────────────────────────────────────────────
    def _bind_functions(self) -> None:
        """
        Bind every DLL function with explicit .argtypes and .restype.
        This is MANDATORY on 64-bit Windows — without it ctypes cannot
        correctly marshal arguments across the ABI boundary.
        """
        lib = self._lib
        vp  = ctypes.c_void_p
        u32 = ctypes.c_uint32
        i32 = ctypes.c_int

        # Context management
        lib.BS2_AllocateContext.argtypes = [ctypes.POINTER(vp)]
        lib.BS2_AllocateContext.restype  = i32

        lib.BS2_Initialize.argtypes = [vp]
        lib.BS2_Initialize.restype  = i32

        lib.BS2_ReleaseContext.argtypes = [vp]
        lib.BS2_ReleaseContext.restype  = None

        # Device discovery
        lib.BS2_SearchDevices.argtypes = [vp]
        lib.BS2_SearchDevices.restype  = i32

        lib.BS2_GetDevices.argtypes = [
            vp,
            ctypes.POINTER(ctypes.POINTER(u32)),   # uint32_t** deviceIds
            ctypes.POINTER(u32),                   # uint32_t*  numDevices
        ]
        lib.BS2_GetDevices.restype = i32

        # Connection
        lib.BS2_ConnectDevice.argtypes = [vp, u32]
        lib.BS2_ConnectDevice.restype  = i32

        lib.BS2_DisconnectDevice.argtypes = [vp, u32]
        lib.BS2_DisconnectDevice.restype  = i32

        # Fingerprint scan
        lib.BS2_ScanFingerprint.argtypes = [
            vp,                                    # context
            u32,                                   # deviceId
            ctypes.POINTER(BS2Fingerprint),        # BS2Fingerprint* out
            u32,                                   # templateFormat
            u32,                                   # timeout (ms)
            vp,                                    # BS2SimpleDeviceInfo* (NULL ok)
        ]
        lib.BS2_ScanFingerprint.restype = i32

        # 1:1 verification (used during 1:N identification loop)
        lib.BS2_VerifyFingerprint.argtypes = [
            vp,
            u32,
            ctypes.POINTER(BS2Fingerprint),        # stored template
            ctypes.POINTER(BS2Fingerprint),        # live template
        ]
        lib.BS2_VerifyFingerprint.restype = i32

        # Memory release for SDK-allocated buffers
        lib.BS2_ReleaseMem.argtypes = [vp]
        lib.BS2_ReleaseMem.restype  = None

    # ── Device Management ─────────────────────────────────────────────────────
    def search_and_connect(self) -> int:
        """
        Discover all connected Suprema USB devices and connect to the first one.
        Returns the device ID on success; raises RuntimeError on failure.
        """
        ret = self._lib.BS2_SearchDevices(self._ctx)
        self._check(ret, "BS2_SearchDevices")

        # Retrieve the list of discovered device IDs
        DevicePtrType = ctypes.POINTER(ctypes.c_uint32)
        device_ids    = DevicePtrType()
        num_devices   = ctypes.c_uint32(0)

        ret = self._lib.BS2_GetDevices(
            self._ctx,
            ctypes.byref(device_ids),
            ctypes.byref(num_devices),
        )
        self._check(ret, "BS2_GetDevices")

        count = num_devices.value
        if count == 0:
            raise RuntimeError(
                "No Suprema device found. Ensure the BioMini Slim 2 is plugged in."
            )

        first_id = device_ids[0]
        logger.info(f"Found {count} device(s). Connecting to device ID={first_id}.")

        # Release SDK-allocated device list memory
        self._lib.BS2_ReleaseMem(device_ids)

        ret = self._lib.BS2_ConnectDevice(self._ctx, first_id)
        self._check(ret, "BS2_ConnectDevice")

        self._device = first_id
        logger.info(f"Connected to device {first_id}.")
        return first_id

    # ── Fingerprint Capture ───────────────────────────────────────────────────
    def scan_fingerprint(self, device_id: Optional[int] = None) -> BS2Fingerprint:
        """
        Prompt the user to place their finger and return a BS2Fingerprint struct.
        Raises RuntimeError on timeout or quality failure.
        """
        dev = device_id or self._device
        if dev is None:
            raise RuntimeError("No device connected. Call search_and_connect() first.")

        fp  = BS2Fingerprint()
        ret = self._lib.BS2_ScanFingerprint(
            self._ctx,
            ctypes.c_uint32(dev),
            ctypes.byref(fp),
            ctypes.c_uint32(TEMPLATE_FORMAT),
            ctypes.c_uint32(SCAN_TIMEOUT_MS),
            None,                                   # optional device info ptr
        )
        self._check(ret, "BS2_ScanFingerprint")
        return fp

    def enroll_finger(self, device_id: Optional[int] = None) -> str:
        """
        Run ENROLL_SCAN_COUNT scans and return a base64 string of the
        last (highest quality) BS2Fingerprint struct for DB storage.
        Each scan improves accuracy; only the final template is stored.
        """
        dev = device_id or self._device
        templates = []
        for i in range(ENROLL_SCAN_COUNT):
            logger.info(f"Enrollment scan {i+1}/{ENROLL_SCAN_COUNT} — place finger …")
            fp = self.scan_fingerprint(dev)
            templates.append(fp)
            logger.info(f"  Scan {i+1} OK  (templateCount={fp.templateCount})")

        # Use the last captured struct as the stored template
        stored = templates[-1]
        return self.fingerprint_to_b64(stored)

    # ── 1:N Identification ────────────────────────────────────────────────────
    def identify(
        self,
        live_fp: BS2Fingerprint,
        stored_templates: List[Tuple[int, str]],
        device_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Compare *live_fp* against every stored template (1:N loop).
        *stored_templates* is a list of (employee_id, base64_template_string).
        Returns the matched employee_id, or None if no match found.
        """
        dev = device_id or self._device
        if dev is None:
            raise RuntimeError("No device connected.")

        for emp_id, b64 in stored_templates:
            stored_fp = self.b64_to_fingerprint(b64)
            ret = self._lib.BS2_VerifyFingerprint(
                self._ctx,
                ctypes.c_uint32(dev),
                ctypes.byref(stored_fp),
                ctypes.byref(live_fp),
            )
            if ret == BS_SDK_SUCCESS:
                logger.info(f"Match found → employee_id={emp_id}")
                return emp_id

        logger.info("No matching fingerprint found in database.")
        return None

    # ── Template Serialization ────────────────────────────────────────────────
    @staticmethod
    def fingerprint_to_b64(fp: BS2Fingerprint) -> str:
        """Serialize a BS2Fingerprint struct to a base64 string for DB storage."""
        raw = bytes(fp)                  # ctypes struct → raw bytes
        return base64.b64encode(raw).decode("utf-8")

    @staticmethod
    def b64_to_fingerprint(b64: str) -> BS2Fingerprint:
        """Deserialize a base64 string from the DB back into a BS2Fingerprint struct."""
        raw = base64.b64decode(b64)
        fp  = BS2Fingerprint.from_buffer_copy(raw)
        return fp

    # ── Internal Helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _check(ret: int, fn_name: str) -> None:
        """Raise RuntimeError if the SDK did not return BS_SDK_SUCCESS."""
        if ret != BS_SDK_SUCCESS:
            msg = _sdk_msg(ret)
            raise RuntimeError(f"[{fn_name}] failed — {msg}")
