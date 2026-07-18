from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from chemvas.ui.bond_preview_access import bond_hover_endpoint_for
from chemvas.ui.canvas_hover_state import (
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
)
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id, has_atoms_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.hover_highlight_access import clear_hover_highlight_for
from chemvas.ui.hover_highlight_logic import plan_structure_hover_update
from chemvas.ui.hover_interaction_access import (
    add_atom_hover_indicator_for,
    add_bond_hover_indicator_for,
    add_bond_style_hover_preview_for,
    add_bond_tool_hover_preview_for,
    add_free_bond_hover_preview_for,
    add_mark_hover_preview_for,
    bond_preview_signature_for,
)
from chemvas.ui.sheet_setup_access import scene_pos_in_sheet_for

if TYPE_CHECKING:
    from chemvas.domain.document import Bond
    from chemvas.ui.canvas_view import CanvasView


class HoverInteractionService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        selection_controller=None,
        active_tool_provider: Callable[[], object | None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.selection_controller = selection_controller
        self._active_tool = active_tool_provider or (lambda: None)

    def _active_tool_name(self) -> str | None:
        name = getattr(self._active_tool(), "name", None)
        return str(name) if name else None

    def update_hover_highlight(self, pos: QPointF) -> None:
        if not scene_pos_in_sheet_for(self.canvas, pos):
            clear_hover_highlight_for(self.canvas)
            return

        if self._active_tool_name() == "mark":
            add_mark_hover_preview_for(self.canvas, pos)
            return

        has_atoms = has_atoms_for(self.canvas)
        preferred_hit = (
            self._preferred_structure_hit_at_scene_pos(pos) if has_atoms else None
        )
        free_preview_key = self._free_preview_key(pos)
        atom_preview_signature, atom_preview_key = self._atom_preview(
            pos, preferred_hit
        )
        bond_preview_key = self._bond_preview_key(preferred_hit)
        hover_state = hover_state_for(self.canvas)

        plan = plan_structure_hover_update(
            has_atoms=has_atoms,
            current_hover_atom_id=hover_state.atom_id,
            current_hover_bond_id=hover_state.bond_id,
            current_preview_key=hover_state.style,
            preferred_hit=preferred_hit,
            free_preview_key=free_preview_key,
            atom_preview_signature=atom_preview_signature,
            atom_preview_key=atom_preview_key,
            bond_preview_key=bond_preview_key,
        )
        self._apply_plan(plan, pos)

    def _preferred_structure_hit_at_scene_pos(self, pos: QPointF):
        selection = self.selection_controller
        if selection is None:
            return None
        return selection.preferred_structure_hit_at_scene_pos(pos)

    def _free_preview_key(self, pos: QPointF) -> str | None:
        preview_style = bond_preview_signature_for(
            self.canvas,
            active_tool_name=self._active_tool_name(),
        )
        if preview_style is None:
            return None
        return f"{preview_style}:{round(pos.x(), 1)}:{round(pos.y(), 1)}"

    def _atom_preview(
        self, pos: QPointF, preferred_hit
    ) -> tuple[str | None, str | None]:
        if (
            preferred_hit is None
            or preferred_hit.kind != "atom"
            or not isinstance(preferred_hit.id, int)
        ):
            return None, None
        atom_preview_signature = bond_preview_signature_for(
            self.canvas,
            active_tool_name=self._active_tool_name(),
        )
        if atom_preview_signature is None:
            return None, None
        atom = atom_for_id(self.canvas, preferred_hit.id)
        if atom is None:
            return atom_preview_signature, None
        end = bond_hover_endpoint_for(
            self.canvas, QPointF(atom.x, atom.y), pos, preferred_hit.id
        )
        return (
            atom_preview_signature,
            f"{atom_preview_signature}:{round(end.x(), 1)}:{round(end.y(), 1)}",
        )

    def _bond_preview_key(self, preferred_hit) -> str | None:
        if (
            preferred_hit is None
            or preferred_hit.kind != "bond"
            or not isinstance(preferred_hit.id, int)
        ):
            return None
        if self._active_tool_name() != "bond":
            return None
        active_bond_style = tool_settings_state_for(self.canvas).active_bond_style
        if active_bond_style not in {"wedge", "hash"}:
            return None
        return active_bond_style

    def _apply_plan(self, plan, pos: QPointF) -> None:
        if plan.action == "noop":
            return
        if plan.action == "clear":
            clear_hover_highlight_for(self.canvas)
            return
        if plan.action == "free_bond_preview":
            clear_hover_highlight_for(self.canvas)
            hover_state_for(self.canvas).style = plan.preview_key
            add_free_bond_hover_preview_for(self.canvas, pos)
            return
        if plan.action == "atom_hit":
            atom_id = plan.hover_atom_id
            if atom_id is None:
                clear_hover_highlight_for(self.canvas)
                return
            clear_hover_highlight_for(self.canvas)
            set_hover_atom_id_for(self.canvas, atom_id)
            add_atom_hover_indicator_for(self.canvas, atom_id)
            if plan.preview_key is not None:
                hover_state_for(self.canvas).style = plan.preview_key
                add_bond_tool_hover_preview_for(self.canvas, atom_id, pos)
            return
        bond_id = plan.hover_bond_id
        clear_hover_highlight_for(self.canvas)
        if bond_id is None:
            return
        set_hover_bond_id_for(self.canvas, bond_id)
        bond = self._bond_for_id(bond_id)
        if bond is None:
            return
        add_bond_hover_indicator_for(self.canvas, bond_id)
        if plan.preview_key:
            add_bond_style_hover_preview_for(self.canvas, bond)

    def _bond_for_id(self, bond_id: int) -> Bond | None:
        return bond_for_id(self.canvas, bond_id)


__all__ = ["HoverInteractionService"]
