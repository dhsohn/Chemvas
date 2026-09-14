from __future__ import annotations

from chemvas.features.export import ExportPlan, render_export_plan
from chemvas.ui.scene_item_access import canvas_scene_for


def export_canvas_scene_for(
    canvas,
    path: str,
    *,
    fmt: str,
    items,
    plan: ExportPlan,
    dpi: int,
    background: str,
    title: str,
):
    return render_export_plan(
        canvas_scene_for(canvas),
        path,
        fmt=fmt,
        items=items,
        plan=plan,
        dpi=dpi,
        background=background,
        title=title,
    )


__all__ = ["export_canvas_scene_for"]
