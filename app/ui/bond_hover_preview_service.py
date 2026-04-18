from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

if TYPE_CHECKING:
    from core.model import Bond
    from ui.canvas_view import CanvasView


class BondHoverPreviewService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def _add_hover_preview_items(self, items) -> None:
        hover_scene_service = getattr(self.canvas, "_hover_scene_service", None)
        if hover_scene_service is not None:
            hover_scene_service.add_hover_preview_items(items)
            return
        self.canvas._add_hover_preview_items(items)

    def add_bond_style_hover_preview(self, bond: Bond) -> None:
        if self.canvas.tools.active is None or self.canvas.tools.active.name != "bond":
            return
        style = self.canvas.active_bond_style
        if style not in {"wedge", "hash"}:
            return
        a = self.canvas.model.atoms.get(bond.a)
        b = self.canvas.model.atoms.get(bond.b)
        if a is None or b is None:
            return
        self.canvas._hover_preview_style = style
        items = self.canvas._build_bond_preview_items(
            QPointF(a.x, a.y),
            QPointF(b.x, b.y),
            bond.a,
            bond.b,
        )
        self._add_hover_preview_items(items)

    def add_bond_tool_hover_preview(self, atom_id: int, pos: QPointF) -> None:
        if self.canvas.tools.active is None or self.canvas.tools.active.name != "bond":
            return
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return
        start = QPointF(atom.x, atom.y)
        end = self.canvas._bond_hover_endpoint(start, pos, atom_id)
        items = self.canvas._build_bond_preview_items(start, end, atom_id, None)
        self._add_hover_preview_items(items)

    def add_free_bond_hover_preview(self, pos: QPointF) -> None:
        start = QPointF(pos.x(), pos.y())
        end = QPointF(pos.x() + self.canvas.renderer.style.bond_length_px, pos.y())
        items = self.canvas._build_bond_preview_items(start, end)
        self._add_hover_preview_items(items)


__all__ = ["BondHoverPreviewService"]
