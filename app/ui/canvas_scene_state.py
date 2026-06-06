from __future__ import annotations


def canvas_scene_for(canvas):
    return canvas.scene()


def optional_canvas_scene_for(canvas):
    try:
        return canvas_scene_for(canvas)
    except RuntimeError:
        return None


__all__ = ["canvas_scene_for", "optional_canvas_scene_for"]
