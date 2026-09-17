from __future__ import annotations


def canvas_scene_for(canvas):
    return canvas.scene()


def optional_canvas_scene_for(canvas):
    try:
        return canvas_scene_for(canvas)
    except RuntimeError:
        return None


def scene_if_present_for(canvas):
    """Scene of a canvas that may lack a scene accessor, or None.

    Only the detached-scene snapshot needs this: it is captured over canvas
    doubles built without a scene. Production lookups use canvas_scene_for.
    """
    scene_method = getattr(canvas, "scene", None)
    return scene_method() if callable(scene_method) else None


__all__ = [
    "canvas_scene_for",
    "optional_canvas_scene_for",
    "scene_if_present_for",
]
