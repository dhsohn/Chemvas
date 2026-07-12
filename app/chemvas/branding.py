"""Application branding: identity strings and the window/app icon.

The icon assets live in ``assets/icon`` inside this package (so they ship in the
wheel) and are regenerated from ``chemvas.svg`` by ``scripts/generate_icons.py``.
``app_icon`` assembles a multi-resolution ``QIcon`` from the runtime PNG set,
falling back to the master SVG if the PNGs are missing. A ``QApplication`` must
already exist before this is called.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon

from chemvas import __version__

APP_NAME = "Chemvas"
APP_VERSION = __version__

_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icon"
_ICON_PNG_SIZES = (16, 32, 64, 128, 256, 512)


def app_icon() -> QIcon:
    """A multi-resolution app icon, or an empty ``QIcon`` if assets are absent."""
    icon = QIcon()
    for size in _ICON_PNG_SIZES:
        png = _ICON_DIR / f"chemvas-{size}.png"
        if png.exists():
            icon.addFile(str(png), QSize(size, size))
    if icon.isNull():
        svg = _ICON_DIR / "chemvas.svg"
        if svg.exists():
            icon.addFile(str(svg))
    return icon


__all__ = ["APP_NAME", "APP_VERSION", "app_icon"]
