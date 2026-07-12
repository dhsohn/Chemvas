#!/usr/bin/env python3
"""Regenerate the README banner and GitHub social-preview image.

Both reuse the benzene mark from the app icon and add the "Chemvas" wordmark +
tagline with QPainter, on the brand teal so they read the same in GitHub's light
and dark themes. Run after changing the mark or the strings below:

    QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/generate_branding_images.py

The wordmark uses the host's system sans; the generated PNGs are committed so
contributors don't need to reproduce the font. Outputs land in docs/images/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QRectF  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
)
from PyQt6.QtSvg import QSvgRenderer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_IMAGES = REPO_ROOT / "docs" / "images"

TEAL = "#0d9488"
WHITE = "#ffffff"
LIGHT_TEAL = "#bfe6dd"
WORDMARK = "Chemvas"
TAGLINE = "2D chemical structure drawing canvas"
WORDMARK_FONT = "Helvetica Neue"

# White benzene mark (no tile) for drawing straight onto the teal field.
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
    image.fill(0)
    return image


def _painter(image: QImage) -> QPainter:
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return painter


def _fonts() -> tuple[QFont, QFont]:
    wordmark_font = QFont(WORDMARK_FONT)
    wordmark_font.setBold(True)
    tagline_font = QFont(WORDMARK_FONT)
    return wordmark_font, tagline_font


def render_banner(out_path: Path) -> None:
    width, height, radius, pad, mark_size = 1360, 340, 44, 96, 184
    image = _new_image(width, height)
    painter = _painter(image)
    painter.setPen(QColor(0, 0, 0, 0))
    painter.setBrush(QColor(TEAL))
    painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

    mark_y = (height - mark_size) / 2
    _mark_renderer().render(painter, QRectF(pad, mark_y, mark_size, mark_size))

    wordmark_font, tagline_font = _fonts()
    wordmark_font.setPixelSize(96)
    tagline_font.setPixelSize(34)
    wordmark_metrics = QFontMetrics(wordmark_font)
    tagline_metrics = QFontMetrics(tagline_font)
    gap = 12
    block_height = (
        wordmark_metrics.ascent()
        + wordmark_metrics.descent()
        + gap
        + tagline_metrics.ascent()
        + tagline_metrics.descent()
    )
    top = (height - block_height) / 2
    text_x = int(pad + mark_size + 56)
    wordmark_baseline = top + wordmark_metrics.ascent()
    tagline_baseline = wordmark_baseline + wordmark_metrics.descent() + gap + tagline_metrics.ascent()

    painter.setFont(wordmark_font)
    painter.setPen(QColor(WHITE))
    painter.drawText(text_x, int(wordmark_baseline), WORDMARK)
    painter.setFont(tagline_font)
    painter.setPen(QColor(LIGHT_TEAL))
    painter.drawText(text_x + 2, int(tagline_baseline), TAGLINE)
    painter.end()

    if not image.save(str(out_path), "PNG"):
        raise RuntimeError(f"failed to write {out_path}")


def render_social(out_path: Path) -> None:
    width, height, mark_size = 1280, 640, 232
    image = _new_image(width, height)
    painter = _painter(image)
    painter.fillRect(0, 0, width, height, QColor(TEAL))

    wordmark_font, tagline_font = _fonts()
    wordmark_font.setPixelSize(132)
    tagline_font.setPixelSize(44)
    wordmark_metrics = QFontMetrics(wordmark_font)
    tagline_metrics = QFontMetrics(tagline_font)
    gap_mark = 40
    gap_text = 24
    block_height = (
        mark_size
        + gap_mark
        + wordmark_metrics.ascent()
        + wordmark_metrics.descent()
        + gap_text
        + tagline_metrics.ascent()
        + tagline_metrics.descent()
    )
    top = (height - block_height) / 2

    _mark_renderer().render(painter, QRectF((width - mark_size) / 2, top, mark_size, mark_size))

    wordmark_baseline = top + mark_size + gap_mark + wordmark_metrics.ascent()
    tagline_baseline = wordmark_baseline + wordmark_metrics.descent() + gap_text + tagline_metrics.ascent()

    painter.setFont(wordmark_font)
    painter.setPen(QColor(WHITE))
    wordmark_x = (width - wordmark_metrics.horizontalAdvance(WORDMARK)) / 2
    painter.drawText(int(wordmark_x), int(wordmark_baseline), WORDMARK)
    painter.setFont(tagline_font)
    painter.setPen(QColor(LIGHT_TEAL))
    tagline_x = (width - tagline_metrics.horizontalAdvance(TAGLINE)) / 2
    painter.drawText(int(tagline_x), int(tagline_baseline), TAGLINE)
    painter.end()

    if not image.save(str(out_path), "PNG"):
        raise RuntimeError(f"failed to write {out_path}")


def main() -> int:
    _app = QGuiApplication(sys.argv)
    DOCS_IMAGES.mkdir(parents=True, exist_ok=True)
    banner = DOCS_IMAGES / "banner.png"
    social = DOCS_IMAGES / "social-preview.png"
    render_banner(banner)
    render_social(social)
    print("Generated:")
    for artifact in (banner, social):
        print(f"  {artifact.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
