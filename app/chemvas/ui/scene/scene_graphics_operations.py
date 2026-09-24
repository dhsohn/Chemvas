"""Graphics-scene operations shared by rendering and editor adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QObject

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene


def detach_graphics_item(
    scene: QGraphicsScene | None,
    item: QGraphicsItem | None,
    *,
    unresolved: bool | None = False,
) -> bool | None:
    """Detach only from the given scene, tolerating already-deleted Qt objects.

    The editor's lifecycle adapter distinguishes a definitely detached item
    from unavailable Qt state; drawing callers treat either as no removal.
    """
    if item is None:
        return False
    if scene is None or (isinstance(scene, QObject) and sip.isdeleted(scene)):
        return unresolved
    scene_method = getattr(item, "scene", None)
    if callable(scene_method):
        try:
            if scene_method() is not scene:
                return False
        except RuntimeError:
            return unresolved
    scene.removeItem(item)
    return True


__all__ = ["detach_graphics_item"]
