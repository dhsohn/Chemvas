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
    def smiles_preview_model(self) -> MoleculeModel | None:
        return self._ensure("_smiles_preview_model", None)

    @smiles_preview_model.setter
    def smiles_preview_model(self, value: MoleculeModel | None) -> None:
        self._canvas._smiles_preview_model = value

    @property
    def smiles_preview_items(self) -> list[Any]:
        return self._ensure("_smiles_preview_items", list)

    @smiles_preview_items.setter
    def smiles_preview_items(self, value: list[Any]) -> None:
        self._canvas._smiles_preview_items = value

    @property
    def smiles_preview_bond_items(self) -> dict[int, list[Any]]:
        return self._ensure("_smiles_preview_bond_items", dict)

    @smiles_preview_bond_items.setter
    def smiles_preview_bond_items(self, value: dict[int, list[Any]]) -> None:
        self._canvas._smiles_preview_bond_items = value

    @property
    def smiles_preview_atom_items(self) -> dict[int, Any]:
        return self._ensure("_smiles_preview_atom_items", dict)

    @smiles_preview_atom_items.setter
    def smiles_preview_atom_items(self, value: dict[int, Any]) -> None:
        self._canvas._smiles_preview_atom_items = value

    @property
    def smiles_preview_center(self) -> Any | None:
        return self._ensure("_smiles_preview_center", None)

    @smiles_preview_center.setter
    def smiles_preview_center(self, value: Any | None) -> None:
        self._canvas._smiles_preview_center = value

    @property
    def smiles_preview_smiles(self) -> str | None:
        return self._ensure("_smiles_preview_smiles", None)

    @smiles_preview_smiles.setter
    def smiles_preview_smiles(self, value: str | None) -> None:
        self._canvas._smiles_preview_smiles = value

    @property
    def template_active(self) -> bool:
        return self._ensure("_template_insert_active", False)

    @template_active.setter
    def template_active(self, value: bool) -> None:
        self._canvas._template_insert_active = value

    @property
    def template_ring_size(self) -> int | None:
        return self._ensure("_template_ring_size", None)

    @template_ring_size.setter
    def template_ring_size(self, value: int | None) -> None:
        self._canvas._template_ring_size = value

    @property
    def template_ring_style(self) -> str | None:
        return self._ensure("_template_ring_style", None)

    @template_ring_style.setter
    def template_ring_style(self, value: str | None) -> None:
        self._canvas._template_ring_style = value

    @property
    def template_preview_items(self) -> list[Any]:
        return self._ensure("_template_preview_items", list)

    @template_preview_items.setter
    def template_preview_items(self, value: list[Any]) -> None:
        self._canvas._template_preview_items = value

    @property
    def template_preview_lines(self) -> list[Any]:
        return self._ensure("_template_preview_lines", list)

    @template_preview_lines.setter
    def template_preview_lines(self, value: list[Any]) -> None:
        self._canvas._template_preview_lines = value

    @property
    def template_preview_dots(self) -> list[Any]:
        return self._ensure("_template_preview_dots", list)

    @template_preview_dots.setter
    def template_preview_dots(self, value: list[Any]) -> None:
        self._canvas._template_preview_dots = value

    @property
    def benzene_preview_items(self) -> list[Any]:
        return self._ensure("_benzene_preview_items", list)

    @benzene_preview_items.setter
    def benzene_preview_items(self, value: list[Any]) -> None:
        self._canvas._benzene_preview_items = value


def insert_state_for(canvas: Any) -> CanvasInsertState | CanvasInsertStateAdapter:
    state = getattr(canvas, "_insert_state", None)
    if state is not None:
        return state
    return CanvasInsertStateAdapter(canvas)


__all__ = ["CanvasInsertState", "CanvasInsertStateAdapter", "insert_state_for"]
