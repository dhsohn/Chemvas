#!/usr/bin/env python3
"""Regenerate every Chemvas app-icon asset from the master SVG.

Single source of truth: ``app/chemvas/assets/icon/chemvas.svg``. Everything else
(runtime PNGs, the macOS ``.icns`` bundle icon, the Windows ``.ico``) is derived
from it, so edits to the mark only need to touch the SVG followed by a re-run:

    QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/generate_icons.py

Rasterisation goes through Qt's own SVG renderer (the same one the app uses for
toolbar glyphs) so the shipped icon matches what Qt would draw. ``.icns`` packing
uses macOS ``iconutil``; ``.ico`` packing uses Pillow. Both generated binaries are
committed so contributors don't need the toolchain to build a bundle.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = REPO_ROOT / "app" / "chemvas" / "assets" / "icon"
PACKAGING_DIR = REPO_ROOT / "packaging" / "icons"
MASTER_SVG = ICON_DIR / "chemvas.svg"

# Sizes shipped inside the wheel and loaded at runtime by chemvas.branding.
RUNTIME_PNG_SIZES = (16, 32, 64, 128, 256, 512)
# Windows .ico members (Pillow rescales the master render to each).
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# macOS .iconset members: (filename, pixel size). iconutil is strict about names.
ICONSET_MEMBERS = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def _render_png(renderer: QSvgRenderer, size: int, out_path: Path) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)  # transparent background
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    if not image.save(str(out_path), "PNG"):
        raise RuntimeError(f"failed to write {out_path}")


def main() -> int:
    if not MASTER_SVG.exists():
        print(f"master SVG not found: {MASTER_SVG}", file=sys.stderr)
        return 1

    _app = QGuiApplication(sys.argv)  # QImage/QPainter need a QGuiApplication.
    renderer = QSvgRenderer(str(MASTER_SVG))
    if not renderer.isValid():
        print(f"master SVG failed to parse: {MASTER_SVG}", file=sys.stderr)
        return 1

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGING_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Runtime PNGs shipped in the package.
    for size in RUNTIME_PNG_SIZES:
        _render_png(renderer, size, ICON_DIR / f"chemvas-{size}.png")

    # 2. A 1024 master render reused for .ico packing and docs/store listings.
    master_png = PACKAGING_DIR / "chemvas-1024.png"
    _render_png(renderer, 1024, master_png)

    # 3. Windows .ico (Pillow downsamples the 1024 render to each member size).
    from PIL import Image

    with Image.open(master_png) as base:
        base.convert("RGBA").save(
            PACKAGING_DIR / "chemvas.ico",
            sizes=[(s, s) for s in ICO_SIZES],
        )

    # 4. macOS .icns via iconutil over a temporary .iconset.
    icns_path = PACKAGING_DIR / "chemvas.icns"
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "chemvas.iconset"
        iconset.mkdir()
        for name, size in ICONSET_MEMBERS:
            _render_png(renderer, size, iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)],
            check=True,
        )

    print("Generated:")
    for size in RUNTIME_PNG_SIZES:
        print(f"  {ICON_DIR.relative_to(REPO_ROOT)}/chemvas-{size}.png")
    for artifact in (master_png, PACKAGING_DIR / "chemvas.ico", icns_path):
        print(f"  {artifact.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
