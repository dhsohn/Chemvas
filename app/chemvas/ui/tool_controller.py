from __future__ import annotations

from chemvas.ui.benzene_tool import BenzeneTool
from chemvas.ui.bond_tool import BondTool
from chemvas.ui.edit_tools import ColorTool, FlipTool
from chemvas.ui.interaction_tools import MarkTool, NoteTool
from chemvas.ui.move_tool import MoveTool
from chemvas.ui.perspective_tool import PerspectiveTool
from chemvas.ui.preview_tools import ArrowTool, OrbitalTool, ShapeTool, TSBracketTool
from chemvas.ui.select_tool import SelectTool
from chemvas.ui.text_tool import TextTool
from chemvas.ui.tool_base import Tool
from chemvas.ui.tool_context import ToolContext


class ToolController:
    def __init__(
        self,
        canvas,
        *,
        hit_testing_service,
        selection_controller,
        note_controller,
        handle_controller,
        selection_rotation_controller,
        scene_delete_controller=None,
        scene_transform_controller=None,
        style_controller=None,
        bond_sets_for_atoms=None,
        color_mutation_service=None,
        selected_scene_items=None,
        select_single_structure_item=None,
        atom_symbol_provider=None,
        history_service=None,
        set_drag_mode=None,
        rubber_band_drag_mode=None,
    ) -> None:
        self.canvas = canvas
        self.context = ToolContext(
            canvas,
            hit_testing_service=hit_testing_service,
            selection_controller=selection_controller,
            note_controller=note_controller,
            handle_controller=handle_controller,
            selection_rotation_controller=selection_rotation_controller,
            scene_delete_controller=scene_delete_controller,
            scene_transform_controller=scene_transform_controller,
            style_controller=style_controller,
            bond_sets_for_atoms=bond_sets_for_atoms,
            color_mutation_service=color_mutation_service,
            selected_scene_items=selected_scene_items,
            select_single_structure_item=select_single_structure_item,
            atom_symbol_provider=atom_symbol_provider,
            history_service=history_service,
            set_drag_mode=set_drag_mode,
            rubber_band_drag_mode=rubber_band_drag_mode,
        )
        self.tools: dict[str, Tool] = {
            "select": SelectTool(canvas, context=self.context),
            "bond": BondTool(canvas, context=self.context),
            "text": TextTool(canvas, context=self.context),
            "mark": MarkTool(canvas, context=self.context),
            "note": NoteTool(canvas, context=self.context),
            "benzene": BenzeneTool(canvas, context=self.context),
            "color": ColorTool(canvas, context=self.context),
            "flip": FlipTool(canvas, context=self.context),
            "move": MoveTool(canvas, context=self.context),
            "arrow": ArrowTool(canvas, "auto", context=self.context),
            "equilibrium": ArrowTool(canvas, "equilibrium", context=self.context),
            "ts_bracket": TSBracketTool(canvas, context=self.context),
            "shape": ShapeTool(canvas, context=self.context),
            "orbital": OrbitalTool(canvas, context=self.context),
            "perspective": PerspectiveTool(canvas, context=self.context),
        }
        self.active: Tool | None = None

    def set_active(self, name: str) -> None:
        if self.active:
            self.active.deactivate()
        self.active = self.tools.get(name, self.tools["select"])
        self.active.activate()


__all__ = ["ToolController"]
