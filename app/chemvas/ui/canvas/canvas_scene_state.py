from __future__ import annotations


def optional_canvas_scene_for(canvas):
    try:
        return canvas.scene()
    except RuntimeError:
        return None


def scene_if_present_for(canvas):
    """Scene of a canvas that may lack a scene accessor, or None.

    Only the detached-scene snapshot needs this: it is captured over canvas
    doubles built without a scene. Production code calls ``canvas.scene()``.
    """
    scene_method = getattr(canvas, "scene", None)
    return scene_method() if callable(scene_method) else None


__all__ = [
    "optional_canvas_scene_for",
    "scene_if_present_for",
]
