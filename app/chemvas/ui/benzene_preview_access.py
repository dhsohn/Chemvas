from __future__ import annotations

from chemvas.ui.canvas_service_access import optional_canvas_service_method
from chemvas.ui.canvas_service_ports import benzene_preview_service_for_access


def _benzene_preview_method(canvas, name: str):
    return optional_canvas_service_method(
        canvas, benzene_preview_service_for_access, name
    )


def clear_benzene_preview_for(canvas) -> None:
    clear_preview = _benzene_preview_method(canvas, "clear_preview")
    if clear_preview is not None:
        clear_preview()


def render_benzene_preview_for(
    canvas, pos, *, attach_atom_id=None, attach_bond_id=None
) -> None:
    render_preview = _benzene_preview_method(canvas, "render_preview")
    if render_preview is not None:
        render_preview(
            pos, attach_atom_id=attach_atom_id, attach_bond_id=attach_bond_id
        )


__all__ = ["clear_benzene_preview_for", "render_benzene_preview_for"]
