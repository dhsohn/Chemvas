from __future__ import annotations

from typing import TYPE_CHECKING

from core.document_state import model_bond_pairs, ring_atom_ids_form_cycle
from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
)
from PyQt6.QtWidgets import QGraphicsPolygonItem

from ui.atom_coords_access import atom_coords_3d_for
from ui.canvas_delete_transaction import canvas_delete_transaction
from ui.canvas_group_state import (
    CanvasSceneGroup,
    group_ids_for_members_for,
    remove_group_for,
)
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import (
    atom_for_id,
    bonds_for,
    model_for,
    next_atom_id_for,
)
from ui.canvas_scene_items_state import ring_items_for
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.handle_overlay_access import clear_handles_for
from ui.history_commands import DeleteSceneItemsCommand, UngroupSceneItemsCommand
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
from ui.selection_collection_access import selected_scene_items_for
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

    def _push_history(self, command: HistoryCommand) -> None:
        self.history.push(command)

    def _remove_overlapping_groups(
        self,
        *,
        atom_ids: set[int] | None = None,
        items: list | None = None,
    ) -> list[tuple[int, CanvasSceneGroup]]:
        group_ids = group_ids_for_members_for(
            self.canvas,
            atom_ids or set(),
            items or [],
        )
        removed: list[tuple[int, CanvasSceneGroup]] = []
        for group_id in sorted(group_ids):
            group = remove_group_for(self.canvas, group_id)
            if group is not None:
                removed.append((group_id, group))
        return removed

    @staticmethod
    def _with_group_cleanup(
        command: HistoryCommand,
        removed_groups: list[tuple[int, CanvasSceneGroup]],
    ) -> HistoryCommand:
        if not removed_groups:
            return command
        group_command = UngroupSceneItemsCommand(removed=removed_groups)
        if isinstance(command, CompositeCommand):
            return CompositeCommand([group_command, *command.commands])
        return CompositeCommand([group_command, command])

    def _delete_broken_ring_fills(
        self,
        *,
        removed_groups: list[tuple[int, CanvasSceneGroup]] | None = None,
    ) -> DeleteSceneItemsCommand | None:
        ring_items = list(ring_items_for(self.canvas))
        if not ring_items:
            return None
        model = model_for(self.canvas)
        atom_ids = set(model.atoms)
        bond_pairs = model_bond_pairs(model)
        broken_items = []
        broken_states = []
        for item in ring_items:
            try:
                ring_atom_ids = item.data(2)
            except RuntimeError:
                continue
            if (
                isinstance(ring_atom_ids, list)
                and all(type(atom_id) is int for atom_id in ring_atom_ids)
                and ring_atom_ids_form_cycle(ring_atom_ids, atom_ids, bond_pairs)
            ):
                continue
            broken_items.append(item)
            broken_states.append(self._ring_state(item))
        if not broken_items:
            return None
        if removed_groups is not None:
            removed_groups.extend(
                self._remove_overlapping_groups(items=broken_items)
            )
        command = DeleteSceneItemsCommand(item_states=broken_states, items=broken_items)
        for item in broken_items:
            self._remove_scene_item(item)
        return command

    def _with_broken_ring_cleanup(
        self,
        command: HistoryCommand,
        *,
        removed_groups: list[tuple[int, CanvasSceneGroup]],
    ) -> HistoryCommand:
        ring_command = self._delete_broken_ring_fills(
            removed_groups=removed_groups,
        )
        if ring_command is None:
            return command
        if isinstance(command, CompositeCommand):
            return CompositeCommand([ring_command, *command.commands])
        return CompositeCommand([ring_command, command])

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_atom(atom_id, record=record)

    def _delete_atom(self, atom_id: int, *, record: bool) -> HistoryCommand | None:
        if not isinstance(atom_id, int) or not self._has_atom(atom_id):
            return None
        removed_groups = self._remove_overlapping_groups(atom_ids={atom_id})
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
            atom_coords_3d_getter=lambda atom_id: atom_coords_3d_for(self.canvas).get(atom_id),
        )
        command = self._with_broken_ring_cleanup(
            command,
            removed_groups=removed_groups,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_bond(bond_id, record=record)

    def _delete_bond(self, bond_id: int, *, record: bool) -> HistoryCommand | None:
        if not isinstance(bond_id, int):
            return None
        removed_groups: list[tuple[int, CanvasSceneGroup]] = []
        before_smiles_input = last_smiles_input_for(self.canvas)
        bond_command = delete_bond_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
        )
        if bond_command is None:
            return None
        command = self._with_broken_ring_cleanup(
            bond_command,
            removed_groups=removed_groups,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_ring(item, record=record)

    def _delete_ring(self, item: QGraphicsPolygonItem, *, record: bool) -> HistoryCommand | None:
        removed_groups = self._remove_overlapping_groups(items=[item])
        command: HistoryCommand = delete_ring_with_history(
            item,
            ring_state_getter=self._ring_state,
            remove_scene_item=self._remove_scene_item,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def delete_selected_items(self) -> bool:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_selected_items()

    def _selection_delete_cleanup_errors(self) -> list[tuple[str, BaseException]]:
        errors: list[tuple[str, BaseException]] = []
        actions = (
            (
                "selection-outline resume",
                lambda: self._style_controller().suspend_selection_outline(False),
            ),
            (
                "selection-outline refresh",
                lambda: refresh_selection_outline_for(self.canvas),
            ),
        )
        for phase, action in actions:
            try:
                action()
            except BaseException as exc:
                errors.append((phase, exc))
        return errors

    @staticmethod
    def _add_cleanup_error_notes(
        primary_error: BaseException,
        cleanup_errors: list[tuple[str, BaseException]],
    ) -> None:
        for phase, cleanup_error in cleanup_errors:
            primary_error.add_note(
                "Delete selection cleanup also failed during "
                f"{phase}: {type(cleanup_error).__name__}: {cleanup_error}"
            )

    def _delete_selected_items(self) -> bool:
        items = selected_scene_items_for(self.canvas, excluded_kinds={"handle", "note_box", "note_select"})
        if not items:
            return False
        self._style_controller().suspend_selection_outline(True)
        body_error: BaseException | None = None
        try:
            selection = classify_delete_selection(items)
            plan = build_delete_selection_plan(
                selection,
                bonds=self._bonds,
                marks_by_atom=self.marks.by_atom,
                mark_state_getter=self._mark_state,
            )

            if plan.single_bond_id is not None:
                self._delete_bond(plan.single_bond_id, record=True)
                return True

            removed_groups = self._remove_overlapping_groups(
                atom_ids=set(plan.atom_ids),
                items=plan.scene_items,
            )
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
                atom_coords_3d_getter=lambda atom_id: atom_coords_3d_for(self.canvas).get(atom_id),
            )

            if any(isinstance(command, (DeleteAtomsCommand, DeleteBondCommand)) for command in commands):
                ring_command = self._delete_broken_ring_fills(
                    removed_groups=removed_groups,
                )
                if ring_command is not None:
                    commands.insert(0, ring_command)

            if not commands:
                return False
            command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
            command = self._with_group_cleanup(command, removed_groups)
            self._push_history(command)
            return True
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            cleanup_errors = self._selection_delete_cleanup_errors()
            if body_error is not None:
                self._add_cleanup_error_notes(body_error, cleanup_errors)
            elif cleanup_errors:
                _, primary_error = cleanup_errors[0]
                self._add_cleanup_error_notes(primary_error, cleanup_errors[1:])
                raise primary_error


__all__ = ["SceneDeleteController"]
