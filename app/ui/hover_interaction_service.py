from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.hover_highlight_logic import plan_structure_hover_update

if TYPE_CHECKING:
    from core.model import Bond
    from ui.canvas_view import CanvasView


class HoverInteractionService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def update_hover_highlight(self, pos: QPointF) -> None:
        if self.canvas.tools.active is not None and self.canvas.tools.active.name == "mark":
            self.canvas._add_mark_hover_preview(pos)
            return

        preferred_hit = self.canvas.preferred_structure_hit_at_scene_pos(pos) if self.canvas.model.atoms else None
        free_preview_key = self._free_preview_key(pos)
        atom_preview_signature, atom_preview_key = self._atom_preview(pos, preferred_hit)
        bond_preview_key = self._bond_preview_key(preferred_hit)

        plan = plan_structure_hover_update(
            has_atoms=bool(self.canvas.model.atoms),
            current_hover_atom_id=self.canvas.hover_atom_id,
            current_hover_bond_id=self.canvas.hover_bond_id,
            current_preview_key=self.canvas._hover_preview_style,
            preferred_hit=preferred_hit,
            free_preview_key=free_preview_key,
            atom_preview_signature=atom_preview_signature,
            atom_preview_key=atom_preview_key,
            bond_preview_key=bond_preview_key,
        )
        self._apply_plan(plan, pos)

    def _free_preview_key(self, pos: QPointF) -> str | None:
        if self.canvas.model.atoms:
            return None
        preview_style = self.canvas._bond_preview_signature()
        if preview_style is None:
            return None
        return f"{preview_style}:{round(pos.x(), 1)}:{round(pos.y(), 1)}"

    def _atom_preview(self, pos: QPointF, preferred_hit) -> tuple[str | None, str | None]:
        if preferred_hit is None or preferred_hit.kind != "atom" or not isinstance(preferred_hit.id, int):
            return None, None
        atom_preview_signature = self.canvas._bond_preview_signature()
        if atom_preview_signature is None:
            return None, None
        atom = self.canvas.model.atoms.get(preferred_hit.id)
        if atom is None:
            return atom_preview_signature, None
        end = self.canvas._bond_hover_endpoint(QPointF(atom.x, atom.y), pos, preferred_hit.id)
        return atom_preview_signature, f"{atom_preview_signature}:{round(end.x(), 1)}:{round(end.y(), 1)}"

    def _bond_preview_key(self, preferred_hit) -> str | None:
        if preferred_hit is None or preferred_hit.kind != "bond" or not isinstance(preferred_hit.id, int):
            return None
        if self.canvas.tools.active is None or self.canvas.tools.active.name != "bond":
            return None
        if self.canvas.active_bond_style not in {"wedge", "hash"}:
            return None
        return self.canvas.active_bond_style

    def _apply_plan(self, plan, pos: QPointF) -> None:
        if plan.action == "noop":
            return
        if plan.action == "clear":
            self.canvas._clear_hover_highlight()
            return
        if plan.action == "free_bond_preview":
            self.canvas._clear_hover_highlight()
            self.canvas._hover_preview_style = plan.preview_key
            self.canvas._bond_hover_preview_service.add_free_bond_hover_preview(pos)
            return
        if plan.action == "atom_hit":
            atom_id = plan.hover_atom_id
            if atom_id is None:
                self.canvas._clear_hover_highlight()
                return
            self.canvas._clear_hover_highlight()
            self.canvas.hover_atom_id = atom_id
            self.canvas._add_atom_hover_indicator(atom_id)
            if plan.preview_key is not None:
                self.canvas._hover_preview_style = plan.preview_key
                self.canvas._add_bond_tool_hover_preview(atom_id, pos)
            return
        bond_id = plan.hover_bond_id
        self.canvas._clear_hover_highlight()
        if bond_id is None:
            return
        self.canvas.hover_bond_id = bond_id
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        add_bond_hover_indicator = getattr(self.canvas, "_add_bond_hover_indicator", None)
        if add_bond_hover_indicator is not None:
            add_bond_hover_indicator(bond_id)
        if plan.preview_key:
            self.canvas._add_bond_style_hover_preview(bond)

    def _bond_for_id(self, bond_id: int) -> Bond | None:
        try:
            bond = self.canvas.model.bonds[bond_id]
        except (IndexError, KeyError, TypeError):
            return None
        return bond


__all__ = ["HoverInteractionService"]
