from __future__ import annotations

from PyQt6.QtCore import QRectF


def preview_footer_height(line_count: int, line_spacing: float) -> float:
    if line_count <= 0:
        return 0.0
    row_height = max(28.0, line_spacing + 10.0)
    gap = 6.0
    return row_height * line_count + gap * (line_count + 1)


def preview_layout_rects(widget_rect: QRectF, *, footer_height: float) -> dict[str, QRectF]:
    panel = QRectF(widget_rect).adjusted(8.0, 8.0, -8.0, -8.0)
    if panel.width() <= 0.0 or panel.height() <= 0.0:
        panel = QRectF(widget_rect)

    pad = 12.0
    header_height = 42.0
    footer_gap = 8.0 if footer_height > 0.0 else 0.0

    header = QRectF(panel.left() + pad, panel.top() + 10.0, max(20.0, panel.width() - pad * 2.0), header_height)
    footer = QRectF()
    viewport_bottom = panel.bottom() - pad - footer_height - footer_gap
    viewport_top = header.bottom() + 8.0
    viewport_height = max(48.0, viewport_bottom - viewport_top)
    viewport = QRectF(panel.left() + pad, viewport_top, max(20.0, panel.width() - pad * 2.0), viewport_height)
    if footer_height > 0.0:
        footer_top = min(panel.bottom() - pad - footer_height, viewport.bottom() + footer_gap)
        footer = QRectF(panel.left() + pad, footer_top, max(20.0, panel.width() - pad * 2.0), footer_height)

    molecule = viewport.adjusted(18.0, 22.0, -18.0, -14.0)
    if molecule.width() < 36.0 or molecule.height() < 36.0:
        molecule = viewport.adjusted(10.0, 16.0, -10.0, -10.0)

    return {
        "panel": panel,
        "header": header,
        "viewport": viewport,
        "molecule": molecule,
        "footer": footer,
    }


def preview_footer_item_rects(rect: QRectF, item_count: int) -> list[QRectF]:
    if rect.isNull() or item_count <= 0:
        return []
    gap = 6.0
    available_height = max(18.0, rect.height() - gap * (item_count + 1))
    item_height = available_height / item_count
    item_width = max(18.0, rect.width() - gap * 2.0)
    x = rect.left() + gap
    y = rect.top() + gap
    return [
        QRectF(x, y + index * (item_height + gap), item_width, item_height)
        for index in range(item_count)
    ]


__all__ = [
    "preview_footer_height",
    "preview_footer_item_rects",
    "preview_layout_rects",
]
