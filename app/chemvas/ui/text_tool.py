from __future__ import annotations

from typing import cast

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QInputDialog

from chemvas.core.text_tool_logic import (
    build_created_atom_command,
    normalize_text_symbol,
    plan_text_input,
    resolve_text_tool_target,
)
from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_model_access import atom_for_id, model_for, next_atom_id_for
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_item_state import atom_state_dict_for
from chemvas.ui.structure_mutation_access import add_atom_for
from chemvas.ui.tool_base import Tool


class TextTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("text", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        pick_radius = bond_length_px_for(self.canvas) * 0.9
        bond_pick_radius = bond_length_px_for(self.canvas) * 0.6
        item = self.context.item_at_event(event)
        item_atom_id = None
        if item is not None and item.data(0) == "atom":
            data_id = item.data(1)
            if isinstance(data_id, int):
                item_atom_id = data_id
        nearby_bond_id = None
        nearby_atom_id = None
        hover_state = hover_state_for(self.canvas)
        if hover_state.atom_id is None and item_atom_id is None:
            nearby_bond_id = self.context.find_bond_near(pos, bond_pick_radius)
            nearby_atom_id = self.context.find_atom_near(pos.x(), pos.y(), pick_radius)
        target = resolve_text_tool_target(
            model_for(self.canvas),
            pos=(pos.x(), pos.y()),
            hover_atom_id=hover_state.atom_id,
            item_atom_id=item_atom_id,
            hover_bond_id=hover_state.bond_id,
            nearby_bond_id=nearby_bond_id,
            nearby_atom_id=nearby_atom_id,
        )
        atom_id = target.atom_id
        pos = QPointF(*target.pos)
        atom = atom_for_id(self.canvas, atom_id)
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
        created_atom = False
        if atom_id is None:
            if not text:
                return True
            before_smiles_input = last_smiles_input_for(self.canvas)
            before_next_atom_id = next_atom_id_for(self.canvas)
            atom_id = add_atom_for(self.canvas, text, pos.x(), pos.y())
            created_atom = True
        if created_atom:
            add_or_update_atom_label(
                self.canvas, atom_id, cast(str, text), show_carbon=True, record=False
            )
            atom_state = atom_state_dict_for(self.canvas, atom_id)
            command = build_created_atom_command(
                atom_id=atom_id,
                atom_state=atom_state,
                before_next_atom_id=before_next_atom_id,
                after_next_atom_id=next_atom_id_for(self.canvas),
                before_smiles_input=before_smiles_input,
                after_smiles_input=last_smiles_input_for(self.canvas),
            )
            self.context.push_history(command)
        else:
            add_or_update_atom_label(
                self.canvas, atom_id, cast(str, text), show_carbon=True
            )
        return True


__all__ = ["TextTool"]
