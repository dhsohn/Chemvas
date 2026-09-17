from __future__ import annotations


def canvas_scene_for(canvas):
    return canvas.scene()


def optional_canvas_scene_for(canvas):
    try:
        return canvas_scene_for(canvas)
    except RuntimeError:
        return None


def scene_if_present_for(canvas):
    """Scene of a canvas double that may not have a scene accessor at all."""
    scene_method = getattr(canvas, "scene", None)
    return scene_method() if callable(scene_method) else None


__all__ = [
    "canvas_scene_for",
    "optional_canvas_scene_for",
    "scene_if_present_for",
]
