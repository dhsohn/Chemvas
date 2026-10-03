"""Native tests must not restore windows belonging to earlier Python runs."""

import ctypes
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit is macOS-only")
def test_window_restore_is_disabled_only_in_this_test_process():
    from tests.macos_test_support import _objc, _send, _string, disable_window_restore

    defaults = _send(_objc.objc_getClass(b"NSUserDefaults"), b"standardUserDefaults")
    domain = _string(b"NSArgumentDomain")
    key = _string(b"ApplePersistenceIgnoreState")
    arguments = _send(defaults, b"volatileDomainForName:", domain)
    value = _send(arguments, b"objectForKey:", key)
    assert value
    # Compare NSString values, not object addresses or a persisted defaults file.
    assert ctypes.string_at(_send(value, b"UTF8String")) == b"YES"

    # Reconfiguration is harmless and preserves unrelated command-line defaults.
    _send(arguments, b"retain")
    options = _send(arguments, b"mutableCopy")
    try:
        _send(
            options,
            b"setObject:forKey:",
            _string(b"kept"),
            _string(b"ChemvasTestMarker"),
        )
        _send(defaults, b"setVolatileDomain:forName:", options, domain)
        disable_window_restore()
        assert _send(defaults, b"objectForKey:", _string(b"ChemvasTestMarker"))
    finally:
        _send(defaults, b"setVolatileDomain:forName:", arguments, domain)
        _send(options, b"release")
        _send(arguments, b"release")

    # A fresh Python process has no inherited override. It imports no pytest
    # conftest, and reading the volatile domain cannot change user preferences.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from tests.macos_test_support import _objc, _send, _string; "
                "defaults = _send(_objc.objc_getClass(b'NSUserDefaults'), b'standardUserDefaults'); "
                "domain = _send(defaults, b'volatileDomainForName:', _string(b'NSArgumentDomain')); "
                "assert not _send(domain, b'objectForKey:', _string(b'ApplePersistenceIgnoreState'))"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stdout + child.stderr
