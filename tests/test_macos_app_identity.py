"""The macOS application name injected before QApplication is built.

The behavioural check runs only on macOS, where CoreFoundation is real: it
applies the name and reads ``CFBundleName`` back out of the live process bundle.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
import unittest
from unittest import mock

from chemvas.adapters import macos_app_identity
from chemvas.adapters.macos_app_identity import apply_macos_app_name

_UTF8 = 0x08000100


def _current_bundle_name() -> str | None:
    """Read ``CFBundleName`` from the live main bundle, or None if unset."""
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cf.CFBundleGetMainBundle.restype = ctypes.c_void_p
    cf.CFBundleGetValueForInfoDictionaryKey.restype = ctypes.c_void_p
    cf.CFBundleGetValueForInfoDictionaryKey.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    # CFStringGetCStringPtr is a fast path that may decline; the copying
    # variant always answers.
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]

    key = ctypes.c_void_p(cf.CFStringCreateWithCString(None, b"CFBundleName", _UTF8))
    value = cf.CFBundleGetValueForInfoDictionaryKey(cf.CFBundleGetMainBundle(), key)
    if not value:
        return None
    buffer = ctypes.create_string_buffer(256)
    if not cf.CFStringGetCString(value, buffer, len(buffer), _UTF8):
        return None
    return buffer.value.decode("utf-8")


class MacosAppIdentityTest(unittest.TestCase):
    def test_is_a_noop_off_macos(self) -> None:
        self.assertFalse(apply_macos_app_name("Chemvas", platform="linux"))
        self.assertFalse(apply_macos_app_name("Chemvas", platform="win32"))

    def test_reports_failure_instead_of_raising_when_the_runtime_is_unavailable(
        self,
    ) -> None:
        with mock.patch.object(
            macos_app_identity,
            "_core_foundation",
            side_effect=OSError("CoreFoundation is unavailable"),
        ):
            self.assertFalse(apply_macos_app_name("Chemvas", platform="darwin"))

    def test_returns_false_when_the_process_has_no_bundle(self) -> None:
        bundleless = mock.Mock()
        bundleless.CFBundleGetMainBundle.return_value = None
        with mock.patch.object(
            macos_app_identity, "_core_foundation", return_value=bundleless
        ):
            self.assertFalse(apply_macos_app_name("Chemvas", platform="darwin"))

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only behaviour")
    def test_names_the_running_process_and_leaves_an_existing_name_alone(self) -> None:
        # Deterministic from any starting state: either this call installs the
        # name, or a previous one already did. Afterwards the key is always set,
        # and a second call must decline to overwrite it.
        applied = apply_macos_app_name("Chemvas")

        if applied:
            self.assertEqual(_current_bundle_name(), "Chemvas")
        self.assertIsNotNone(_current_bundle_name())
        self.assertFalse(
            apply_macos_app_name("SomethingElse"),
            "an already-named bundle must not be renamed",
        )
        self.assertNotEqual(_current_bundle_name(), "SomethingElse")
