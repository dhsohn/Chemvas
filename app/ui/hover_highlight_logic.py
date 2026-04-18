from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ui.selection_hit_logic import StructureHit

HoverAction = Literal["clear", "free_bond_preview", "atom_hit", "bond_hit", "noop"]


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
        return HoverUpdatePlan(action="clear")

    if preferred_hit.kind == "atom" and isinstance(preferred_hit.id, int):
        if atom_preview_signature is not None and atom_preview_key is None:
            return HoverUpdatePlan(action="clear")
        if preferred_hit.id == current_hover_atom_id and atom_preview_key == current_preview_key:
            return HoverUpdatePlan(action="noop")
        return HoverUpdatePlan(
            action="atom_hit",
            hover_atom_id=preferred_hit.id,
            preview_key=atom_preview_key,
        )

    if preferred_hit.kind != "bond" or not isinstance(preferred_hit.id, int):
        return HoverUpdatePlan(action="clear")

    if preferred_hit.id == current_hover_bond_id and bond_preview_key == current_preview_key:
        return HoverUpdatePlan(action="noop")
    return HoverUpdatePlan(
        action="bond_hit",
        hover_bond_id=preferred_hit.id,
        preview_key=bond_preview_key,
    )


__all__ = [
    "HoverUpdatePlan",
    "plan_structure_hover_update",
]
