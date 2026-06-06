from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.preview_3d import Preview3D


def preview_for_window(window) -> Preview3D:
    return window._preview_3d


__all__ = ["preview_for_window"]
