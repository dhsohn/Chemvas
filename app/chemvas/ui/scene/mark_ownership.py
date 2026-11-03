"""Read-only ownership feedback; moving a glyph never changes its atom."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.domain.document import MoleculeModel
    from chemvas.domain.points import PointLike
    from chemvas.ui.canvas.canvas_view import CanvasView


DISTANT_MARK_COLOR = "#b45309"
MARK_OWNER_GUIDANCE = (
    "Amber means far from owner. Moving keeps this owner. "
    "Right-click the mark to reassign it."
)


def mark_is_distant(
    model: MoleculeModel,
    data: Mapping[str, object],
    center: PointLike,
    *,
    bond_length: float,
    label_distance: Callable[[int, float, float, str], float],
) -> bool:
    """Whether a mark sits visibly far from its owner atom.

    ``label_distance`` gives the label-aware mark offset from the atom in a
    direction, so a long alias's legitimate offset is not called distant.
    Either editor passes its own model, mark data, centre and measurements.
    """
    atom_id = data.get("atom_id")
    if not isinstance(atom_id, int):
        return False
    atom = model.atom_for_id(atom_id)
    if atom is None:
        return False
    dx, dy = center.x() - atom.x, center.y() - atom.y
    distance = math.hypot(dx, dy)
    if distance == 0:
        return False
    kind = data.get("kind", "plus")
    # A long alias has a legitimate label-aware offset. This is a visual
    # warning threshold, not a binding radius or a chemical validation rule.
    label_offset = label_distance(
        atom_id, dx / distance, dy / distance, kind if isinstance(kind, str) else "plus"
    )
    return distance > max(bond_length, label_offset + bond_length * 0.5)


def mark_owner_text(
    model: MoleculeModel, data: Mapping[str, object], *, distant: bool
) -> str:
    atom_id = data.get("atom_id")
    atom = model.atom_for_id(atom_id) if isinstance(atom_id, int) else None
    if atom is None:
        return "Free mark (no chemical owner)"
    warning = " — far from owner" if distant else ""
    return f"Owner: {atom.element} #{atom_id}{warning}"


def mark_is_distant_for(canvas: CanvasView, item: QGraphicsItem) -> bool:
    return mark_is_distant(
        canvas.model,
        item.data(1) or {},
        canvas.services.scene_decoration_build_service.mark_center(item),
        bond_length=canvas.renderer.style.bond_length_px,
        label_distance=canvas.render_context.geometry.mark_target_distance_for_atom,
    )


def mark_owner_text_for(canvas: CanvasView, item: QGraphicsItem) -> str:
    return mark_owner_text(
        canvas.model,
        item.data(1) or {},
        distant=mark_is_distant_for(canvas, item),
    )
