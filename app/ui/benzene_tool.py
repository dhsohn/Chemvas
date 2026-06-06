from core.tool_overlay_logic import activate_tool_no_drag
from PyQt6.QtCore import Qt

from ui.benzene_preview_access import (
    clear_benzene_preview_for,
    render_benzene_preview_for,
)
from ui.canvas_hover_state import hover_state_for
from ui.structure_mutation_access import add_benzene_ring_for
from ui.tool_base import Tool


class BenzeneTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("benzene", canvas, context=context)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)
        clear_benzene_preview_for(self.canvas)

    def deactivate(self) -> None:
        clear_benzene_preview_for(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        hover_state = hover_state_for(self.canvas)
        if hover_state.bond_id is not None:
            add_benzene_ring_for(self.canvas, pos, attach_bond_id=hover_state.bond_id)
        elif hover_state.atom_id is not None:
            add_benzene_ring_for(self.canvas, pos, attach_atom_id=hover_state.atom_id)
        else:
            add_benzene_ring_for(self.canvas, pos)
        clear_benzene_preview_for(self.canvas)
        return True

    def on_mouse_move(self, event) -> bool:
        if event.buttons() != Qt.MouseButton.NoButton:
            return False
        pos = self.context.scene_pos_from_event(event)
        hover_state = hover_state_for(self.canvas)
        attach_bond_id = hover_state.bond_id
        attach_atom_id = None if attach_bond_id is not None else hover_state.atom_id
        render_benzene_preview_for(
            self.canvas,
            pos,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )
        return True


__all__ = ["BenzeneTool"]
