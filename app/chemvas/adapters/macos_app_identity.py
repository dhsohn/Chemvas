"""Give a non-bundled macOS process a proper application name.

macOS reads the name it shows in the menu bar — and Qt reads the name it puts
in the application menu — from the main bundle's ``CFBundleName``, not from
``QApplication.setApplicationName()``. A ``pip install``ed or run-from-source
Chemvas has no ``Info.plist`` at all, so Qt falls back to the basename of
``argv[0]`` and macOS falls back to the process name: the menu ends up reading
"python" or "main.py" instead of "Chemvas".

Writing ``CFBundleName`` into the main bundle's info dictionary (and setting the
process name to match) before the ``QApplication`` is constructed fixes both.
A real ``.app`` bundle already carries the key, so this leaves it alone.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

_CF_STRING_ENCODING_UTF8 = 0x08000100


def _core_foundation() -> ctypes.CDLL:
    path = ctypes.util.find_library("CoreFoundation")
    if path is None:
        raise OSError("CoreFoundation is unavailable")
    library = ctypes.cdll.LoadLibrary(path)
    library.CFBundleGetMainBundle.restype = ctypes.c_void_p
    library.CFBundleGetMainBundle.argtypes = []
    library.CFBundleGetInfoDictionary.restype = ctypes.c_void_p
    library.CFBundleGetInfoDictionary.argtypes = [ctypes.c_void_p]
    library.CFBundleGetValueForInfoDictionaryKey.restype = ctypes.c_void_p
    library.CFBundleGetValueForInfoDictionaryKey.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    library.CFStringCreateWithCString.restype = ctypes.c_void_p
    library.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    library.CFDictionarySetValue.restype = None
    library.CFDictionarySetValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    return library


def _objc_runtime() -> ctypes.CDLL:
    path = ctypes.util.find_library("objc")
    if path is None:
        raise OSError("the Objective-C runtime is unavailable")
    library = ctypes.cdll.LoadLibrary(path)
    library.objc_getClass.restype = ctypes.c_void_p
    library.objc_getClass.argtypes = [ctypes.c_char_p]
    library.sel_registerName.restype = ctypes.c_void_p
    library.sel_registerName.argtypes = [ctypes.c_char_p]
    return library


def _set_process_name(objc: ctypes.CDLL, name: str) -> None:
    send = objc.objc_msgSend
    send.restype = ctypes.c_void_p
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    process_info = send(
        objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo")
    )

    send.restype = ctypes.c_void_p
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
    ns_name = send(
        objc.objc_getClass(b"NSString"),
        objc.sel_registerName(b"stringWithUTF8String:"),
        name.encode("utf-8"),
    )

    send.restype = None
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    send(process_info, objc.sel_registerName(b"setProcessName:"), ns_name)


def apply_macos_app_name(name: str, *, platform: str | None = None) -> bool:
    """Name this process ``name`` for the macOS menu bar. True if applied.

    Must be called before the ``QApplication`` is constructed: Qt reads the name
    once, while it builds the Cocoa menu bar. A no-op off macOS, and a no-op
    inside a real ``.app`` bundle, whose ``Info.plist`` already names it.

    Failures are swallowed: this is cosmetic, and reaching into CoreFoundation
    by hand is exactly the kind of call that a future macOS could stop honoring.
    Losing the menu title there is acceptable; refusing to start is not.
    """
    if (platform or sys.platform) != "darwin":
        return False
    try:
        cf = _core_foundation()
        bundle = cf.CFBundleGetMainBundle()
        if not bundle:
            return False
        info = cf.CFBundleGetInfoDictionary(bundle)
        if not info:
            return False

        def cfstr(text: str) -> ctypes.c_void_p:
            return ctypes.c_void_p(
                cf.CFStringCreateWithCString(
                    None, text.encode("utf-8"), _CF_STRING_ENCODING_UTF8
                )
            )

        bundle_name_key = cfstr("CFBundleName")
        if cf.CFBundleGetValueForInfoDictionaryKey(bundle, bundle_name_key):
            return False
        cf.CFDictionarySetValue(info, bundle_name_key, cfstr(name))
        _set_process_name(_objc_runtime(), name)
    except Exception:
        return False
    return True


__all__ = ["apply_macos_app_name"]
