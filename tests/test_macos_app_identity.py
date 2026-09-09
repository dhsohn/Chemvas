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


def _current_bundle_value(key_name: str) -> str | None:
    """Read a string from the live main bundle, or None if unset."""
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

    key = ctypes.c_void_p(
        cf.CFStringCreateWithCString(None, key_name.encode("utf-8"), _UTF8)
    )
    value = cf.CFBundleGetValueForInfoDictionaryKey(cf.CFBundleGetMainBundle(), key)
    if not value:
        return None
    buffer = ctypes.create_string_buffer(256)
    if not cf.CFStringGetCString(value, buffer, len(buffer), _UTF8):
        return None
    return buffer.value.decode("utf-8")


def _bundle_runtime(bundle_name: str | None, bundle_id: str | None):
    """Model CF string handles and the mutable in-memory bundle dictionary."""
    strings: dict[int, str] = {}
    info = {"CFBundleName": bundle_name}

    def cf_string(text: str | None) -> int | None:
        if text is None:
            return None
        pointer = len(strings) + 100
        strings[pointer] = text
        return pointer

    def string_value(pointer):
        if isinstance(pointer, ctypes.c_void_p):
            pointer = pointer.value
        return strings[pointer]

    def set_value(_info, key, value):
        info[string_value(key)] = string_value(value)

    cf = mock.Mock()
    cf.CFBundleGetMainBundle.return_value = 1
    cf.CFBundleGetInfoDictionary.return_value = 2
    cf.CFBundleGetIdentifier.side_effect = lambda _bundle: cf_string(bundle_id)
    cf.CFStringCreateWithCString.side_effect = lambda _alloc, text, _encoding: (
        cf_string(text.decode("utf-8"))
    )
    cf.CFBundleGetValueForInfoDictionaryKey.side_effect = lambda _bundle, key: (
        cf_string(info.get(string_value(key)))
    )
    cf.CFEqual.side_effect = lambda left, right: (
        string_value(left) == string_value(right)
    )
    cf.CFDictionarySetValue.side_effect = set_value
    return cf, info


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

    def test_names_the_framework_python_launcher_once(self) -> None:
        cf, info = _bundle_runtime("Python", "org.python.python")
        with (
            mock.patch.object(macos_app_identity, "_core_foundation", return_value=cf),
            mock.patch.object(macos_app_identity, "_objc_runtime"),
            mock.patch.object(macos_app_identity, "_set_process_name") as set_name,
        ):
            self.assertTrue(apply_macos_app_name("Chemvas", platform="darwin"))
            self.assertEqual(info["CFBundleName"], "Chemvas")
            self.assertFalse(apply_macos_app_name("SomethingElse", platform="darwin"))
            self.assertEqual(info["CFBundleName"], "Chemvas")
            self.assertEqual(set_name.call_args.args[1], "Chemvas")
            set_name.assert_called_once()
            cf.CFDictionarySetValue.assert_called_once()

    def test_preserves_application_bundle_names_and_unknown_identifiers(self) -> None:
        for name, identifier in (
            ("Chemvas", "org.example.chemvas"),
            ("Chemvas", "org.python.python"),
            ("Python", "org.example.other"),
            ("Python", None),
            ("Chemvas", None),
        ):
            with self.subTest(name=name, identifier=identifier):
                cf, info = _bundle_runtime(name, identifier)
                with (
                    mock.patch.object(
                        macos_app_identity, "_core_foundation", return_value=cf
                    ),
                    mock.patch.object(
                        macos_app_identity, "_set_process_name"
                    ) as set_name,
                ):
                    self.assertFalse(
                        apply_macos_app_name("Replacement", platform="darwin")
                    )
                    self.assertEqual(info["CFBundleName"], name)
                    cf.CFDictionarySetValue.assert_not_called()
                    set_name.assert_not_called()

    def test_still_names_a_bundle_without_a_name(self) -> None:
        cf, info = _bundle_runtime(None, None)
        with (
            mock.patch.object(macos_app_identity, "_core_foundation", return_value=cf),
            mock.patch.object(macos_app_identity, "_objc_runtime"),
            mock.patch.object(macos_app_identity, "_set_process_name") as set_name,
        ):
            self.assertTrue(apply_macos_app_name("Chemvas", platform="darwin"))
            self.assertEqual(info["CFBundleName"], "Chemvas")
            self.assertEqual(set_name.call_args.args[1], "Chemvas")

    def test_returns_false_without_writing_when_bundle_identifier_lookup_fails(
        self,
    ) -> None:
        cf, info = _bundle_runtime("Python", "org.python.python")
        cf.CFBundleGetIdentifier.side_effect = OSError("bundle identifier unavailable")
        with mock.patch.object(macos_app_identity, "_core_foundation", return_value=cf):
            self.assertFalse(apply_macos_app_name("Chemvas", platform="darwin"))
        self.assertEqual(info["CFBundleName"], "Python")
        cf.CFDictionarySetValue.assert_not_called()

    def test_returns_false_when_the_bundle_has_no_info_dictionary(self) -> None:
        cf, _info = _bundle_runtime(None, None)
        cf.CFBundleGetInfoDictionary.return_value = None
        with mock.patch.object(macos_app_identity, "_core_foundation", return_value=cf):
            self.assertFalse(apply_macos_app_name("Chemvas", platform="darwin"))
        cf.CFDictionarySetValue.assert_not_called()

    def test_reports_dictionary_write_failure_without_changing_the_process_name(
        self,
    ) -> None:
        cf, info = _bundle_runtime("Python", "org.python.python")
        cf.CFDictionarySetValue.side_effect = OSError("bundle dictionary unavailable")
        with (
            mock.patch.object(macos_app_identity, "_core_foundation", return_value=cf),
            mock.patch.object(macos_app_identity, "_set_process_name") as set_name,
        ):
            self.assertFalse(apply_macos_app_name("Chemvas", platform="darwin"))
        self.assertEqual(info["CFBundleName"], "Python")
        set_name.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "macOS-only behaviour")
    def test_names_the_running_process_and_leaves_an_existing_name_alone(self) -> None:
        before = _current_bundle_value("CFBundleName")
        identifier = _current_bundle_value("CFBundleIdentifier")
        expected_application = before is None or (
            before == "Python" and identifier == "org.python.python"
        )
        self.assertEqual(apply_macos_app_name("Chemvas"), expected_application)
        expected_name = "Chemvas" if expected_application else before
        self.assertEqual(_current_bundle_value("CFBundleName"), expected_name)
        self.assertFalse(
            apply_macos_app_name("SomethingElse"),
            "an already-named bundle must not be renamed",
        )
        self.assertEqual(_current_bundle_value("CFBundleName"), expected_name)
