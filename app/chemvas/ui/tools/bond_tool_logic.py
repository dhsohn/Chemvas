from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    DOTTED_DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    bold_double_style_for_style,
    is_dotted_double_bond_style,
    style_for_double_position,
    style_for_existing_bond_overlay,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.domain.document import Bond, MoleculeModel


BOND_PICK_RADIUS_RATIO = 0.35
BOND_SNAP_RADIUS_RATIO = 0.2


@dataclass(frozen=True)
class BondSnapTarget:
    pos: tuple[float, float]
    start_atom_id: int | None


def is_short_bond_gesture(
    press: tuple[float, float] | None,
    release: tuple[float, float],
    bond_length: float,
) -> bool:
    distance = (
        math.hypot(press[0] - release[0], press[1] - release[1])
        if press is not None
        else 0.0
    )
    return distance < bond_length * 0.1


def resolve_bond_press_target(
    *,
    atom_id: int | None,
    item_kind: str | None,
    item_bond_id: object,
    nearby_bond_id: object,
    hover_bond_id: object,
) -> int | None:
    if atom_id is not None:
        return None
    if item_kind == "bond" and isinstance(item_bond_id, int):
        return item_bond_id
    if isinstance(nearby_bond_id, int):
        return nearby_bond_id
    if isinstance(hover_bond_id, int):
        return hover_bond_id
    return None


def resolve_bond_snap_target(
    model: MoleculeModel,
    *,
    pos: tuple[float, float],
    atom_id: int | None,
    bond_id: int | None,
    start_atom_id: int | None,
    ignore_start: bool,
) -> BondSnapTarget:
    if atom_id is not None:
        if ignore_start and atom_id == start_atom_id:
            return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)
        atom = model.atoms.get(atom_id)
        if atom is None:
            return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)
        return BondSnapTarget(
            pos=(atom.x, atom.y),
            start_atom_id=start_atom_id if ignore_start else atom_id,
        )

    if bond_id is None or not (0 <= bond_id < len(model.bonds)):
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    bond = model.bonds[bond_id]
    if bond is None:
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    atom_a = model.atoms.get(bond.a)
    atom_b = model.atoms.get(bond.b)
    if atom_a is None or atom_b is None:
        return BondSnapTarget(pos=pos, start_atom_id=start_atom_id)

    x, y = pos
    da = (x - atom_a.x) ** 2 + (y - atom_a.y) ** 2
    db = (x - atom_b.x) ** 2 + (y - atom_b.y) ** 2
    target = atom_a if da <= db else atom_b
    return BondSnapTarget(pos=(target.x, target.y), start_atom_id=start_atom_id)


def resolve_bond_endpoint_target(
    model: MoleculeModel,
    *,
    start: tuple[float, float],
    end: tuple[float, float],
    atom_id: int | None,
    start_atom_id: int | None,
    snap_angle_step: int | float | None,
    bond_length: float,
) -> tuple[float, float]:
    if atom_id is not None and atom_id != start_atom_id:
        atom = model.atoms.get(atom_id)
        if atom is not None:
            return (atom.x, atom.y)

    start_x, start_y = start
    end_x, end_y = end
    dx = end_x - start_x
    dy = end_y - start_y
    length = (dx**2 + dy**2) ** 0.5
    if length == 0:
        return end

    angle = math.degrees(math.atan2(dy, dx))
    step = snap_angle_step or 30
    snap_angle = round(angle / step) * step
    rad = math.radians(snap_angle)
    return (
        start_x + math.cos(rad) * bond_length,
        start_y + math.sin(rad) * bond_length,
    )


def apply_active_bond_style(
    bond: Bond | None,
    active_bond_style: str,
    active_bond_order: int,
    *,
    apply_style: Callable[[str, int], None],
    cycle_style: Callable[[], None],
    notify_error: Callable[[str], object],
) -> bool:
    """Apply the existing bond-tool click policy through the presentation adapter."""
    if bond is None:
        return False
    if bond.style == "double_either" and (
        active_bond_style in BOLD_BOND_STYLES or active_bond_style == "dotted"
    ):
        notify_error(
            "This appearance change would erase unknown double-bond stereo. "
            "Choose Double (2) first to clear it explicitly.",
        )
        return True
    if active_bond_style in {"wedge", "hash"}:
        apply_style(active_bond_style, 1)
        return True
    if active_bond_style in BOLD_BOND_STYLES:
        next_style, next_order = style_for_existing_bond_overlay(
            bond.style, bond.order, active_bond_style, active_bond_order
        )
        apply_style(next_style, next_order)
        return True
    if active_bond_style == "dotted":
        next_style, next_order = style_for_existing_bond_overlay(
            bond.style,
            bond.order,
            "dotted",
            1,
        )
        if bond.order == 2 and not is_dotted_double_bond_style(next_style, next_order):
            notify_error(
                "Dotted overlay needs an inner or outer plain double bond. "
                "Choose Double, then its position, and try Dotted again.",
            )
            return True
        apply_style(next_style, next_order)
        return True
    if active_bond_style in {"single", "double", "triple"}:
        if (bond.style, bond.order) != (
            active_bond_style,
            active_bond_order,
        ):
            apply_style(active_bond_style, active_bond_order)
        return True
    cycle_style()
    return True


__all__ = [
    "BOND_PICK_RADIUS_RATIO",
    "BOND_SNAP_RADIUS_RATIO",
    "BondSnapTarget",
    "apply_active_bond_style",
    "is_short_bond_gesture",
    "resolve_bond_endpoint_target",
    "resolve_bond_press_target",
    "resolve_bond_snap_target",
]


BOND_STYLE_HOTKEYS = {
    "1": ("single", 1),
    "2": ("double", 2),
    "3": ("triple", 3),
    "b": ("bold_in", 1),
    "w": ("wedge", 1),
    "h": ("hash", 1),
    "d": ("dotted", 1),
    "H": ("hash", 1),
    "D": (DOTTED_DOUBLE_STYLE_DEFAULT, 2),
}
BOND_POSITION_HOTKEYS = {
    "c": DOUBLE_STYLE_CENTER,
    "l": DOUBLE_STYLE_DEFAULT,
    "r": DOUBLE_STYLE_OUTER,
}
BOND_SHORTCUT_KEYS = (
    frozenset(BOND_STYLE_HOTKEYS) | frozenset(BOND_POSITION_HOTKEYS) | {"B"}
)


def bond_shortcut_style(bond: Bond, text: str) -> tuple[str, int] | None:
    """The native hover-bond shortcut decision, shared by both input adapters."""
    if bond.style == "double_either" and text in {
        "b",
        "d",
        "B",
        "D",
        *BOND_POSITION_HOTKEYS,
    }:
        raise ValueError(
            "This appearance change would erase unknown double-bond stereo. "
            "Choose Double (2) first to clear it explicitly."
        )
    if text == "B":
        return bold_double_style_for_style(bond.style, bond.order), 2
    if text in BOND_POSITION_HOTKEYS:
        if bond.order != 2:
            return None
        position_style = BOND_POSITION_HOTKEYS[text]
        target_style = style_for_double_position(bond.style, bond.order, position_style)
        return target_style or position_style, 2
    return BOND_STYLE_HOTKEYS.get(text)
