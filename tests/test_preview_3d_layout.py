from __future__ import annotations

from PyQt6.QtCore import QRectF
from ui.preview_3d_layout import (
    preview_footer_height,
    preview_footer_item_rects,
    preview_layout_rects,
)


def test_preview_footer_height_uses_row_minimum_and_gap() -> None:
    assert preview_footer_height(0, 18.0) == 0.0
    assert preview_footer_height(2, 12.0) == 74.0
    assert preview_footer_height(1, 32.0) == 54.0


def test_preview_layout_rects_builds_ordered_sections_with_footer() -> None:
    layout = preview_layout_rects(QRectF(0.0, 0.0, 320.0, 260.0), footer_height=74.0)

    assert layout["panel"] == QRectF(8.0, 8.0, 304.0, 244.0)
    assert layout["header"].bottom() < layout["viewport"].top()
    assert layout["viewport"].bottom() < layout["footer"].top()
    assert layout["viewport"].contains(layout["molecule"])
    assert layout["footer"].height() == 74.0


def test_preview_layout_rects_uses_full_rect_for_tiny_widget_and_fallback_molecule_padding() -> None:
    layout = preview_layout_rects(QRectF(0.0, 0.0, 12.0, 12.0), footer_height=0.0)

    assert layout["panel"] == QRectF(0.0, 0.0, 12.0, 12.0)
    assert layout["viewport"].height() >= 48.0
    assert layout["molecule"].left() == layout["viewport"].left() + 10.0
    assert layout["footer"].isNull()


def test_preview_footer_item_rects_stacks_items_inside_footer() -> None:
    footer = QRectF(20.0, 100.0, 180.0, 74.0)

    items = preview_footer_item_rects(footer, 2)

    assert preview_footer_item_rects(QRectF(), 2) == []
    assert preview_footer_item_rects(footer, 0) == []
    assert len(items) == 2
    assert items[0].left() == footer.left() + 6.0
    assert items[0].right() == footer.right() - 6.0
    assert items[0].bottom() < items[1].top()
