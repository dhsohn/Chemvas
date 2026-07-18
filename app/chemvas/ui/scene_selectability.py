from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsItem


def make_item_selectable(item) -> None:
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)


__all__ = ["make_item_selectable"]
