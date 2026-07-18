from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_state_lookup import ensure_canvas_state


@dataclass
class CanvasInsertState:
    smiles_active: bool = False
    smiles_preview_model: MoleculeModel | None = None
    smiles_preview_items: list[Any] = field(default_factory=list)
    smiles_preview_bond_items: dict[int, list[Any]] = field(default_factory=dict)
    smiles_preview_atom_items: dict[int, Any] = field(default_factory=dict)
    smiles_preview_center: Any | None = None
    smiles_preview_smiles: str | None = None
    template_active: bool = False
    template_ring_size: int | None = None
    template_ring_style: str | None = None
    template_preview_items: list[Any] = field(default_factory=list)
    template_preview_lines: list[Any] = field(default_factory=list)
    template_preview_dots: list[Any] = field(default_factory=list)
    benzene_preview_items: list[Any] = field(default_factory=list)


def insert_state_for(canvas: Any) -> CanvasInsertState:
    return ensure_canvas_state(canvas, "insert_state", CanvasInsertState)


__all__ = ["CanvasInsertState", "insert_state_for"]
