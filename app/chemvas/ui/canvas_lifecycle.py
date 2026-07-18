from __future__ import annotations

import contextlib

from chemvas.ui.canvas_scene_reset_access import clear_scene_for


def schedule_canvas_deletion_for(canvas) -> None:
    """Make a canvas inert before scheduling Qt-owned destruction.

    The scene is a child of the view.  Without this guard, destroying selected
    graphics can emit selectionChanged after the view has already begun C++
    teardown, re-entering Python callbacks with a partially destroyed canvas.
    """
    scene = None
    block_signals = None
    try:
        with contextlib.suppress(Exception):
            scene_method = getattr(canvas, "scene", None)
            scene = scene_method() if callable(scene_method) else None
            block_signals = getattr(scene, "blockSignals", None)
        try:
            if callable(block_signals):
                with contextlib.suppress(Exception):
                    block_signals(True)
            # Registry cleanup is best-effort during an irreversible disposal.
            # A failure must not leave a removed tab alive indefinitely.
            with contextlib.suppress(Exception):
                clear_scene_for(canvas)
        finally:
            if callable(block_signals):
                with contextlib.suppress(Exception):
                    block_signals(True)
    finally:
        canvas.deleteLater()


__all__ = ["schedule_canvas_deletion_for"]
