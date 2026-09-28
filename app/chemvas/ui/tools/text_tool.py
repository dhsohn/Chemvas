from __future__ import annotations

from typing import cast, override

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QInputDialog

from chemvas.ui.canvas.canvas_window_access import notify_error_for
from chemvas.ui.molecule.atom_label_access import (
    add_labelled_atom_for,
    add_or_update_atom_label,
)
from chemvas.ui.tools.text_tool_logic import (
    apply_text_input,
    normalize_text_symbol,
    plan_text_input,
    resolve_text_tool_target,
)
from chemvas.ui.tools.tool_base import Tool
from chemvas.ui.tools.tool_overlay_logic import activate_tool_no_drag


class TextTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("text", canvas, context=context)

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        pick_radius = self.canvas.renderer.style.bond_length_px * 0.9
        bond_pick_radius = self.canvas.renderer.style.bond_length_px * 0.6
        item = self.context.item_at_event(event)
        item_atom_id = None
        if item is not None and item.data(0) == "atom":
            data_id = item.data(1)
            if isinstance(data_id, int):
                item_atom_id = data_id
        nearby_bond_id = None
        nearby_atom_id = None
        hover_state = self.canvas.runtime_state.hover_preview_state
        if hover_state.atom_id is None and item_atom_id is None:
            nearby_bond_id = self.context.find_bond_near(pos, bond_pick_radius)
            nearby_atom_id = self.context.find_atom_near(pos.x(), pos.y(), pick_radius)
        target = resolve_text_tool_target(
            self.canvas.model,
            pos=(pos.x(), pos.y()),
            hover_atom_id=hover_state.atom_id,
            item_atom_id=item_atom_id,
            hover_bond_id=hover_state.bond_id,
            nearby_bond_id=nearby_bond_id,
            nearby_atom_id=nearby_atom_id,
        )
        atom_id = target.atom_id
        pos = QPointF(*target.pos)
        atom = self.canvas.model.atom_for_id(atom_id)
        existing_element = atom.element if atom is not None else ""
        input_plan = plan_text_input(
            self.context.current_atom_symbol(),
            existing_element=existing_element,
        )
        text = input_plan.text
        if input_plan.needs_prompt:
            text, ok = QInputDialog.getText(
                self.canvas,
                "Atom Label",
                "Enter atom symbol:",
                text=input_plan.initial,
            )
            if not ok:
                return True
            text = normalize_text_symbol(text)
        apply_text_input(
            target,
            cast("str", text),
            existing_element,
            add_atom=lambda text, x, y: add_labelled_atom_for(self.canvas, text, x, y),
            update_label=lambda atom_id, text, **kwargs: add_or_update_atom_label(
                self.canvas, atom_id, text, **kwargs
            ),
            notify_error=lambda message: notify_error_for(self.canvas, message),
        )
        return True


__all__ = ["TextTool"]
