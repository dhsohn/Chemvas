from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chemvas.features.selection import selected_atom_ids_with_bond_endpoints
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

SELECTION_OUTLINE_SCREEN_PX = 1.5


def selection_arrow_overlay_width(
    pen_width: float, pad: float, atom_radius: float
) -> float:
    return max(pen_width + pad * 1.5, atom_radius * 0.7)


def selection_bond_overlay_width(
    pen_width: float, spacing: float, radius: float
) -> float:
    return max(pen_width + spacing * 1.05, radius * 0.75)


def selection_bond_overlay_width_for(canvas, base_pen) -> float:
    return selection_bond_overlay_width(
        base_pen.widthF(),
        canvas.renderer.style.bond_spacing_px,
        atom_pick_radius_for(canvas),
    )


def atom_center_point_for(canvas, atom_id: int):
    from PyQt6.QtCore import QPointF

    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return None
    return QPointF(atom.x, atom.y)


def selection_indicator_rect_for_atom_for(canvas, atom_id: int):
    from PyQt6.QtCore import QRectF

    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return None
    item = visible_atom_item_for(canvas, atom_id)
    label_rect = None
    if item is not None:
        try:
            rect = item.sceneBoundingRect()
            label_rect = (rect.x(), rect.y(), rect.width(), rect.height())
        except (RuntimeError, AttributeError):
            pass
    return QRectF(
        *selection_atom_rect(atom.x, atom.y, atom_pick_radius_for(canvas), label_rect)
    )


def selection_atom_rect(
    x: float, y: float, radius: float, label_rect: Sequence[float] | None = None
) -> tuple[float, float, float, float]:
    """Keep short labels circular; widen only long text that overflows it."""
    left, top, width, height = x - radius, y - radius, radius * 2.0, radius * 2.0
    if label_rect is not None and label_rect[2] > width * 3.0 and label_rect[3] > 0:
        lx, ly, lw, lh = label_rect
        right, bottom = max(left + width, lx + lw), max(top + height, ly + lh)
        left, top = min(left, lx), min(top, ly)
        width, height = right - left, bottom - top
    return left, top, width, height


def selection_structure_ids(
    model: Any,
    atom_ids: set[int],
    bond_ids: set[int],
    atom_bond_ids: Mapping[int, set[int]],
) -> tuple[set[int], set[int]]:
    atom_ids = selected_atom_ids_with_bond_endpoints(
        atom_ids, bond_ids, bonds=model.bonds
    )
    candidates = set(bond_ids)
    for atom_id in atom_ids:
        candidates.update(atom_bond_ids.get(atom_id, ()))
    overlay_bonds = {
        bond_id
        for bond_id in candidates
        if (bond := model.bond_for_id(bond_id)) is not None
        and bond.a in atom_ids
        and bond.b in atom_ids
    }
    return atom_ids, overlay_bonds


__all__ = [
    "SELECTION_OUTLINE_SCREEN_PX",
    "atom_center_point_for",
    "selection_arrow_overlay_width",
    "selection_atom_rect",
    "selection_bond_overlay_width",
    "selection_bond_overlay_width_for",
    "selection_bond_parts",
    "selection_indicator_rect_for_atom_for",
    "selection_structure_ids",
]


def selection_bond_parts(
    parts: list[dict[str, Any]],
    *,
    bond: Any,
    atom_a: Any,
    atom_b: Any,
    trim_line: Callable[..., tuple[float, float]],
    spacing: float,
    in_ring: bool,
) -> list[dict[str, Any]]:
    """Choose the native selection band over already materialized bond parts."""
    import math

    if not parts:
        return []
    if in_ring and not parts[0]["empty"]:
        return parts[:1]
    if bond.order >= 2 and all("line" in part for part in parts):
        if atom_a is not None and atom_b is not None:
            t0, t1 = trim_line(bond.a, bond.b, atom_a.x, atom_a.y, atom_b.x, atom_b.y)
            x1 = atom_a.x + (atom_b.x - atom_a.x) * t0
            y1 = atom_a.y + (atom_b.y - atom_a.y) * t0
            x2 = atom_a.x + (atom_b.x - atom_a.x) * t1
            y2 = atom_a.y + (atom_b.y - atom_a.y) * t1
            length = math.hypot(x2 - x1, y2 - y1)
            if length > 1e-6:
                nx, ny = -(y2 - y1) / length, (x2 - x1) / length
                mid_x, mid_y = (x1 + x2) * 0.5, (y1 + y2) * 0.5
                offsets = [
                    ((part["line"][0] + part["line"][2]) * 0.5 - mid_x) * nx
                    + ((part["line"][1] + part["line"][3]) * 0.5 - mid_y) * ny
                    for part in parts
                ]
                # Ring/outer pairs retain their on-axis line; symmetric pairs
                # retain the midpoint of the two rendered lines.
                shift = (
                    0.0
                    if any(abs(offset) <= spacing * 0.25 for offset in offsets)
                    else (min(offsets) + max(offsets)) * 0.5
                )
                return [
                    {
                        "line": (
                            x1 + nx * shift,
                            y1 + ny * shift,
                            x2 + nx * shift,
                            y2 + ny * shift,
                        ),
                        "width": max(part["width"] for part in parts),
                        "empty": False,
                    }
                ]
    return parts
