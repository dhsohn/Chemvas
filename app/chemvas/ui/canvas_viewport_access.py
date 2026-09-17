"""Read and restore a view's own rect, transform and pan.

The document session service captures these before a destructive document
replacement and puts them back afterwards. Services do not call
``QGraphicsView`` methods themselves; this module is the one place that reads
them, so the two-phase restore (geometry first, pan last after selection and
focus are back) is spelled out here rather than in the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRectF

from chemvas.ui.transactions.scene_rect import (
    clear_explicit_view_scene_rect,
    set_explicit_view_scene_rect,
    view_scene_rect_is_explicit,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QTransform


@dataclass(frozen=True, slots=True, kw_only=True)
class ViewportSnapshot:
    scene_rect: QRectF
    scene_rect_explicit: bool
    transform: QTransform
    horizontal_scroll: int | None
    vertical_scroll: int | None


def viewport_transform_for(canvas: Any) -> QTransform:
    return canvas.viewportTransform()


def capture_viewport_for(view: Any) -> ViewportSnapshot:
    horizontal_bar = view.horizontalScrollBar()
    vertical_bar = view.verticalScrollBar()
    return ViewportSnapshot(
        scene_rect=QRectF(view.sceneRect()),
        scene_rect_explicit=view_scene_rect_is_explicit(view),
        transform=view.transform(),
        horizontal_scroll=(
            int(horizontal_bar.value()) if horizontal_bar is not None else None
        ),
        vertical_scroll=int(vertical_bar.value()) if vertical_bar is not None else None,
    )


def restore_viewport_geometry_for(view: Any, snapshot: ViewportSnapshot) -> None:
    if snapshot.scene_rect_explicit:
        set_explicit_view_scene_rect(view, snapshot.scene_rect)
    else:
        clear_explicit_view_scene_rect(view)
    view.setTransform(snapshot.transform)


def restore_viewport_scroll_for(view: Any, snapshot: ViewportSnapshot) -> None:
    horizontal_bar = view.horizontalScrollBar()
    if snapshot.horizontal_scroll is not None and horizontal_bar is not None:
        horizontal_bar.setValue(snapshot.horizontal_scroll)
    vertical_bar = view.verticalScrollBar()
    if snapshot.vertical_scroll is not None and vertical_bar is not None:
        vertical_bar.setValue(snapshot.vertical_scroll)


__all__ = [
    "ViewportSnapshot",
    "capture_viewport_for",
    "restore_viewport_geometry_for",
    "restore_viewport_scroll_for",
    "viewport_transform_for",
]
