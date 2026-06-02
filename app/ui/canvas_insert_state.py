from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.model import MoleculeModel


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


class CanvasInsertStateAdapter:
    def __init__(self, canvas: Any) -> None:
        self._canvas = canvas

    def _ensure(self, name: str, default):
        if not hasattr(self._canvas, name):
            setattr(self._canvas, name, default() if callable(default) else default)
        return getattr(self._canvas, name)

    @property
    def smiles_active(self) -> bool:
        return self._ensure("_smiles_insert_active", False)

    @smiles_active.setter
    def smiles_active(self, value: bool) -> None:
        self._canvas._smiles_insert_active = value

    @property
    def template_active(self) -> bool:
        return self._ensure("_template_insert_active", False)

    @template_active.setter
    def template_active(self, value: bool) -> None:
        self._canvas._template_insert_active = value


def insert_state_for(canvas: Any) -> CanvasInsertState | CanvasInsertStateAdapter:
    state = getattr(canvas, "_insert_state", None)
    if state is not None:
        return state
    return CanvasInsertStateAdapter(canvas)


__all__ = ["CanvasInsertState", "CanvasInsertStateAdapter", "insert_state_for"]
