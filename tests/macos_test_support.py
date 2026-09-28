"""Keep AppKit's Python window restoration out of native test processes."""

import ctypes

# NSUserDefaults is in Foundation; libobjc only provides message dispatch.
_foundation = ctypes.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
_objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p


def _send(receiver, selector, *arguments):
    # Every call here returns an object pointer (or an ignored void result).
    signature = ctypes.CFUNCTYPE(
        ctypes.c_void_p, *([ctypes.c_void_p] * (2 + len(arguments)))
    )
    return signature(("objc_msgSend", _objc))(
        receiver, _objc.sel_registerName(selector), *arguments
    )


def _string(value):
    return _send(
        _objc.objc_getClass(b"NSString"),
        b"stringWithUTF8String:",
        ctypes.cast(ctypes.c_char_p(value), ctypes.c_void_p),
    )


def disable_window_restore():
    # Qt Test uses ApplePersistenceIgnoreState for this same crash-restore
    # dialog. Use a volatile domain so no Python/Chemvas user preference is
    # written and an existing persistent setting cannot override the test.
    pool = _send(_send(_objc.objc_getClass(b"NSAutoreleasePool"), b"alloc"), b"init")
    try:
        defaults = _send(
            _objc.objc_getClass(b"NSUserDefaults"), b"standardUserDefaults"
        )
        domain = _string(b"NSArgumentDomain")
        options = _send(
            _send(defaults, b"volatileDomainForName:", domain), b"mutableCopy"
        )
        try:
            _send(
                options,
                b"setObject:forKey:",
                _string(b"YES"),
                _string(b"ApplePersistenceIgnoreState"),
            )
            _send(defaults, b"setVolatileDomain:forName:", options, domain)
        finally:
            _send(options, b"release")
    finally:
        _send(pool, b"drain")
