"""Pure hover planning policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from chemvas.features.selection import StructureHit

PREVIEW_COLOR_RGBA = (120, 120, 120, 140)
# Template insert previews draw at this opacity on top of the color.
PREVIEW_OPACITY = 0.5
HOVER_PREVIEW_OPACITY = 0.55
HOVER_PREVIEW_Z = 4.5
ATOM_HOVER_Z = 5.0
ATOM_HOVER_RADIUS_RATIO = 0.25
BOND_HOVER_Z = 4.0
BOND_HOVER_RADIUS_RATIO = 0.22
ATOM_HOVER_PEN_RGBA = (13, 148, 136, 150)
ATOM_HOVER_BRUSH_RGBA = (13, 148, 136, 30)

HoverAction = Literal["clear", "free_bond_preview", "atom_hit", "bond_hit", "noop"]


@dataclass(slots=True)
class HoverState:
    """Transient hover state without a dependency on the Qt adapter."""

    style: str | None = None
    items: list[object] = field(default_factory=list)
    atom_id: int | None = None
    bond_id: int | None = None


@dataclass(frozen=True)
class HoverUpdatePlan:
    action: HoverAction
    hover_atom_id: int | None = None
    hover_bond_id: int | None = None
    preview_key: str | None = None


def plan_structure_hover_update(
    *,
    has_atoms: bool,
    current_hover_atom_id: int | None,
    current_hover_bond_id: int | None,
    current_preview_key: str | None,
    preferred_hit: StructureHit | None,
    free_preview_key: str | None = None,
    atom_preview_signature: str | None = None,
    atom_preview_key: str | None = None,
    bond_preview_key: str | None = None,
) -> HoverUpdatePlan:
    if not has_atoms:
        if free_preview_key is None:
            return HoverUpdatePlan(action="clear")
        if free_preview_key == current_preview_key:
            return HoverUpdatePlan(action="noop")
        return HoverUpdatePlan(action="free_bond_preview", preview_key=free_preview_key)

    if preferred_hit is None:
        if free_preview_key is None:
            return HoverUpdatePlan(action="clear")
        if free_preview_key == current_preview_key:
            return HoverUpdatePlan(action="noop")
        return HoverUpdatePlan(action="free_bond_preview", preview_key=free_preview_key)

    if preferred_hit.kind == "atom" and isinstance(preferred_hit.id, int):
        if atom_preview_signature is not None and atom_preview_key is None:
            return HoverUpdatePlan(action="clear")
        if (
            preferred_hit.id == current_hover_atom_id
            and atom_preview_key == current_preview_key
        ):
            return HoverUpdatePlan(action="noop")
        return HoverUpdatePlan(
            action="atom_hit",
            hover_atom_id=preferred_hit.id,
            preview_key=atom_preview_key,
        )

    if preferred_hit.kind != "bond" or not isinstance(preferred_hit.id, int):
        if free_preview_key is None:
            return HoverUpdatePlan(action="clear")
        if free_preview_key == current_preview_key:
            return HoverUpdatePlan(action="noop")
        return HoverUpdatePlan(action="free_bond_preview", preview_key=free_preview_key)

    if (
        preferred_hit.id == current_hover_bond_id
        and bond_preview_key == current_preview_key
    ):
        return HoverUpdatePlan(action="noop")
    return HoverUpdatePlan(
        action="bond_hit",
        hover_bond_id=preferred_hit.id,
        preview_key=bond_preview_key,
    )


__all__ = [
    "ATOM_HOVER_BRUSH_RGBA",
    "ATOM_HOVER_PEN_RGBA",
    "ATOM_HOVER_RADIUS_RATIO",
    "ATOM_HOVER_Z",
    "BOND_HOVER_RADIUS_RATIO",
    "BOND_HOVER_Z",
    "HOVER_PREVIEW_OPACITY",
    "HOVER_PREVIEW_Z",
    "PREVIEW_COLOR_RGBA",
    "PREVIEW_OPACITY",
    "HoverState",
    "HoverUpdatePlan",
    "plan_structure_hover_update",
]
