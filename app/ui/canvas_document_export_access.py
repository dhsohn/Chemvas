from __future__ import annotations

from ui.export_render_service import export_scene
from ui.scene_item_access import canvas_scene_for


def export_canvas_scene_for(
    canvas,
    path: str,
    *,
    fmt: str,
    items,
    margin: float,
    dpi: int,
    background: str,
    title: str,
    unit_scale: float,
    target_width_pt: float | None,
):
    return export_scene(
        canvas_scene_for(canvas),
        path,
        fmt=fmt,
        items=items,
        margin=margin,
        dpi=dpi,
        background=background,
        title=title,
        unit_scale=unit_scale,
        target_width_pt=target_width_pt,
    )


__all__ = ["export_canvas_scene_for"]
