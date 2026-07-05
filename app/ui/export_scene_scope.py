from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

# Transient overlays that must never appear in an exported figure. Mirrors the
# exclusion set used by the clipboard copy path (``_selection_items_for_copy``).
EXPORT_EXCLUDED_KINDS = frozenset({"handle", "note_select", "selection_outline"})


def collect_export_items(scene: QGraphicsScene) -> list[QGraphicsItem]:
    """Visible content items only: real content always carries a role, while
    transient overlays are either role-less (hover/preview) or in the exclusion
    set, so both are dropped."""
    items: list[QGraphicsItem] = []
    for item in scene.items():
        if not item.isVisible():
            continue
        role = item.data(0)
        if role is None or role in EXPORT_EXCLUDED_KINDS:
            continue
        items.append(item)
    return items


def item_export_bounds(item: QGraphicsItem) -> QRectF:
    bounds_getter = getattr(item, "export_scene_bounding_rect", None)
    if callable(bounds_getter):
        rect = bounds_getter()
        if isinstance(rect, QRectF):
            return QRectF(rect)
    return item.sceneBoundingRect()


def content_bounds(items: Sequence[QGraphicsItem]) -> QRectF | None:
    rect = QRectF()
    for item in items:
        item_rect = item_export_bounds(item)
        if item_rect.isNull():
            continue
        rect = QRectF(item_rect) if rect.isNull() else rect.united(item_rect)
    if rect.isNull() or rect.width() <= 0.0 or rect.height() <= 0.0:
        return None
    return rect


def set_label_outline_mode(items: Sequence[QGraphicsItem], enabled: bool) -> list[QGraphicsItem]:
    changed: list[QGraphicsItem] = []
    for item in items:
        setter = getattr(item, "set_outline_mode", None)
        if callable(setter):
            setter(enabled)
            changed.append(item)
    return changed


def _item_with_descendants(item: QGraphicsItem) -> list[QGraphicsItem]:
    items = [item]
    for child in item.childItems():
        items.extend(_item_with_descendants(child))
    return items


def export_item_closure(items: Sequence[QGraphicsItem]) -> list[QGraphicsItem]:
    expanded: list[QGraphicsItem] = []
    seen: set[QGraphicsItem] = set()
    for item in items:
        for descendant in _item_with_descendants(item):
            if descendant in seen:
                continue
            seen.add(descendant)
            expanded.append(descendant)
    return expanded


@contextmanager
def exported_scene(scene: QGraphicsScene, export_items: Sequence[QGraphicsItem]):
    expanded_export_items = export_item_closure(export_items)
    export_set = set(expanded_export_items)
    hidden = [item for item in scene.items() if item.isVisible() and item not in export_set]
    outlined = set_label_outline_mode(expanded_export_items, True)
    for item in hidden:
        item.setVisible(False)
    try:
        yield
    finally:
        for item in hidden:
            item.setVisible(True)
        set_label_outline_mode(outlined, False)


__all__ = [
    "EXPORT_EXCLUDED_KINDS",
    "collect_export_items",
    "content_bounds",
    "export_item_closure",
    "exported_scene",
    "item_export_bounds",
    "set_label_outline_mode",
]
