from __future__ import annotations

from typing import TYPE_CHECKING

from core.history import CompositeCommand, HistoryCommand
from PyQt6.QtWidgets import QGraphicsPolygonItem

from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import (
    atom_for_id,
    bonds_for,
    next_atom_id_for,
)
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.handle_overlay_access import clear_handles_for
from ui.scene_delete_apply_logic import apply_delete_selection_plan
from ui.scene_delete_logic import build_delete_selection_plan, classify_delete_selection
from ui.scene_item_access import remove_scene_item as remove_scene_item_helper
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    mark_state_dict_for,
    ring_state_dict_for,
    scene_item_state_for,
)
from ui.scene_single_item_mutation_logic import (
    delete_atom_with_history,
    delete_bond_with_history,
    delete_ring_with_history,
)
from ui.selection_scene_access import scene_selected_items_for
from ui.selection_service_access import refresh_selection_outline_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneDeleteController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        atom_mutation_service=None,
        bond_mutation_service=None,
        style_controller=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.atom_mutation_service = atom_mutation_service
        self.bond_mutation_service = bond_mutation_service
        self.style_controller = style_controller
        self.history = history_service
        self.marks = mark_registry_for(canvas)

    @property
    def _bonds(self):
        return bonds_for(self.canvas)

    @property
    def _next_atom_id(self) -> int:
        return next_atom_id_for(self.canvas)

    def _has_atom(self, atom_id: int) -> bool:
        return atom_for_id(self.canvas, atom_id) is not None

    def _redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id, skip_bond_id=skip_bond_id)

    def _mark_state(self, item) -> dict:
        return mark_state_dict_for(self.canvas, item)

    def _bond_state(self, bond) -> dict:
        return bond_state_dict(bond)

    def _atom_state(self, atom_id: int) -> dict:
        return atom_state_dict_for(self.canvas, atom_id)

    def _scene_item_state(self, item) -> dict:
        return scene_item_state_for(self.canvas, item)

    def _ring_state(self, item) -> dict:
        return ring_state_dict_for(self.canvas, item)

    def _atom_mutation_service(self):
        if self.atom_mutation_service is None:
            msg = "SceneDeleteController requires atom_mutation_service"
            raise RuntimeError(msg)
        return self.atom_mutation_service

    def _bond_mutation_service(self):
        if self.bond_mutation_service is None:
            msg = "SceneDeleteController requires bond_mutation_service"
            raise RuntimeError(msg)
        return self.bond_mutation_service

    def _style_controller(self):
        if self.style_controller is None:
            msg = "SceneDeleteController requires style_controller"
            raise RuntimeError(msg)
        return self.style_controller

    def _remove_bond(self, bond_id: int) -> None:
        self._bond_mutation_service().remove_bond_by_id(bond_id)

    def _remove_atom(self, atom_id: int, remove_marks: bool = True) -> None:
        self._atom_mutation_service().remove_atom_only(atom_id, remove_marks=remove_marks)

    def _remove_scene_item(self, item) -> None:
        remove_scene_item_helper(self.canvas, item)

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        if not isinstance(atom_id, int) or not self._has_atom(atom_id):
            return None
        before_smiles_input = last_smiles_input_for(self.canvas)
        command = delete_atom_with_history(
            atom_id,
            bonds=self._bonds,
            marks_by_atom=self.marks.by_atom,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            mark_state_getter=self._mark_state,
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
            atom_state_getter=self._atom_state,
            next_atom_id_getter=lambda: self._next_atom_id,
            remove_atom_only=self._remove_atom,
        )
        if record:
            self.history.push(command)
        return command

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        if not isinstance(bond_id, int):
            return None
        before_smiles_input = last_smiles_input_for(self.canvas)
        command = delete_bond_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
        )
        if command is None:
            return None
        if record:
            self.history.push(command)
        return command

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        command = delete_ring_with_history(
            item,
            ring_state_getter=self._ring_state,
            remove_scene_item=self._remove_scene_item,
        )
        if record:
            self.history.push(command)
        return command

    def delete_selected_items(self) -> bool:
        items = scene_selected_items_for(self.canvas)
        if not items:
            return False
        self._style_controller().suspend_selection_outline(True)
        try:
            selection = classify_delete_selection(items)
            plan = build_delete_selection_plan(
                selection,
                bonds=self._bonds,
                marks_by_atom=self.marks.by_atom,
                mark_state_getter=self._mark_state,
            )

            if plan.single_bond_id is not None:
                self.delete_bond(plan.single_bond_id, record=True)
                return True

            before_smiles_input = last_smiles_input_for(self.canvas)
            if plan.clear_smiles_input:
                clear_last_smiles_input_for(self.canvas)
            commands = apply_delete_selection_plan(
                plan,
                bonds=self._bonds,
                before_smiles_input=before_smiles_input,
                current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
                bond_state_getter=self._bond_state,
                remove_bond_by_id=self._remove_bond,
                redraw_connected_bonds=self._redraw_connected_bonds,
                atom_state_getter=self._atom_state,
                next_atom_id_getter=lambda: self._next_atom_id,
                remove_atom_only=self._remove_atom,
                scene_item_state_getter=self._scene_item_state,
                remove_scene_item=self._remove_scene_item,
                clear_handles=lambda: clear_handles_for(self.canvas),
            )

            if not commands:
                return False
            if len(commands) == 1:
                self.history.push(commands[0])
                return True
            self.history.push(CompositeCommand(commands))
            return True
        finally:
            self._style_controller().suspend_selection_outline(False)
            refresh_selection_outline_for(self.canvas)


__all__ = ["SceneDeleteController"]
