#!/usr/bin/env python3
"""Render branding from the existing mark and the actual first-scheme export.

Run after capture_first_scheme.py has produced examples/first-scheme.svg:
    QT_QPA_PLATFORM=offscreen python scripts/generate_branding_images.py

The generated PNGs are committed. Fonts and Qt versions can change their bytes;
the reaction drawing itself comes from Chemvas's exported SVG.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_IMAGES = REPO_ROOT / "docs" / "images"

DARK = "#123e39"
TEAL = "#0d9488"
WHITE = "#ffffff"
LIGHT_TEAL = "#c5e9df"
WORDMARK = "Chemvas"
TAGLINE = "Draw interactively. Automate safely. Export exactly."

_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<polygon points="50,17 77,33.25 77,66.75 50,83 23,66.75 23,33.25" '
    'fill="none" stroke="#ffffff" stroke-width="6" stroke-linejoin="round"/>'
    '<circle cx="50" cy="50" r="14.5" fill="none" stroke="#ffffff" stroke-width="5"/>'
    "</svg>"
)


def _mark_renderer() -> QSvgRenderer:
    return QSvgRenderer(QByteArray(_MARK_SVG.encode("utf-8")))


def _new_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(DARK))
    return image


def _painter(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return painter


def _text(
    painter: QPainter,
    x: int,
    y: int,
    text: str,
    size: int,
    color: str = WHITE,
    *,
    bold: bool = False,
) -> None:
    font = QFont("DejaVu Sans")
    font.setPixelSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(x, y, text)


def _save(image: QImage, path: Path) -> None:
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"failed to write {path}")


def render_banner(out_path: Path) -> None:
    image = _new_image(1360, 270)
    painter = _painter(image)
    painter.fillRect(0, 258, 1360, 12, QColor(TEAL))
    _mark_renderer().render(painter, QRectF(54, 46, 170, 170))
    _text(painter, 265, 139, WORDMARK, 86, bold=True)
    _text(painter, 268, 194, TAGLINE, 28, LIGHT_TEAL)
    painter.end()
    _save(image, out_path)


def render_social(out_path: Path) -> None:
    scheme_path = REPO_ROOT / "examples" / "first-scheme.svg"
    if not scheme_path.is_file():
        raise RuntimeError(f"capture the first-scheme example first: {scheme_path}")
    scheme = QSvgRenderer(str(scheme_path))
    if not scheme.isValid():
        raise RuntimeError(f"invalid example SVG: {scheme_path}")
    scheme.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

    image = _new_image(1280, 640)
    painter = _painter(image)
    _mark_renderer().render(painter, QRectF(39, 39, 102, 102))
    _text(painter, 159, 119, WORDMARK, 72, bold=True)
    _text(painter, 64, 181, TAGLINE, 27, LIGHT_TEAL)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(WHITE))
    painter.drawRoundedRect(QRectF(64, 230, 1152, 265), 20, 20)
    scheme.render(painter, QRectF(102, 262, 1076, 201))
    _text(
        painter,
        64,
        551,
        "Chemical structures. Reaction schemes. Ready for the page.",
        26,
    )
    _text(painter, 64, 596, "OPEN SOURCE  /  DESKTOP CANVAS", 17, LIGHT_TEAL)
    _text(painter, 848, 596, "github.com/dhsohn/Chemvas", 18, LIGHT_TEAL)
    painter.end()
    _save(image, out_path)


def main() -> int:
    _app = QGuiApplication(sys.argv)
    DOCS_IMAGES.mkdir(parents=True, exist_ok=True)
    banner = DOCS_IMAGES / "banner.png"
    social = DOCS_IMAGES / "social-preview.png"
    render_banner(banner)
    render_social(social)
    for artifact in (banner, social):
        print(f"Generated {artifact.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
