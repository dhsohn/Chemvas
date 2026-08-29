from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.canvas_history_recording_service import (
    CanvasHistoryRecordingService,
)

if TYPE_CHECKING:
    from PyQt6.QtCore import QPointF


class _DeleteSessionRollbackErrors(list[BaseException]):
    def __init__(
        self,
        errors: list[BaseException],
        *,
        completed: bool,
    ) -> None:
        super().__init__(errors)
        self.completed = completed


class ToolContext:
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
        self.hit_testing_service = hit_testing_service
        self.selection_controller = selection_controller
        self.note_controller = note_controller
        self.handle_controller = handle_controller
        self.selection_rotation_controller = selection_rotation_controller
        self.scene_delete_controller = scene_delete_controller
        self.scene_transform_controller = scene_transform_controller
        self.style_controller = style_controller
        self._bond_sets_for_atoms = bond_sets_for_atoms
        self.color_mutation_service = color_mutation_service
        self._selected_scene_items = selected_scene_items
        self._select_single_structure_item = select_single_structure_item
        self._atom_symbol_provider = atom_symbol_provider
        self.history_service = history_service
        self._set_drag_mode = set_drag_mode
        self._rubber_band_drag_mode = rubber_band_drag_mode

    @staticmethod
    def _require_port(port, name: str):
        if port is None:
            raise AttributeError(f"ToolContext requires an injected '{name}' port")
        return port

    def scene_pos_from_event(self, event) -> QPointF:
        return self.hit_testing_service.scene_pos_from_event(event)

    def item_at_scene_pos(self, pos: QPointF):
        return self.hit_testing_service.item_at_scene_pos(pos)

    def item_at_event(self, event):
        return self.hit_testing_service.item_at_event(event)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        return self.hit_testing_service.find_atom_near(x, y, max_dist)

    def find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        return self.hit_testing_service.find_bond_near(pos, max_dist)

    def toggle_item_selection(self, item) -> bool:
        return bool(self.selection_controller.toggle_item_selection(item))

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF):
        return self.selection_controller.preferred_structure_hit_at_scene_pos(pos)

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        return self.selection_controller.preferred_structure_item_at_scene_pos(pos)

    def selection_hit_test(self, pos: QPointF, snapshot=None) -> bool:
        return bool(
            self.selection_controller.selection_hit_test(pos, snapshot=snapshot)
        )

    def select_structure_for_item(self, item) -> bool:
        return bool(self.selection_controller.select_structure_for_item(item))

    def select_single_structure_item(self, item) -> bool:
        port = self._require_port(
            self._select_single_structure_item, "select_single_structure_item"
        )
        return bool(port(item))

    def create_text_note(self, pos: QPointF, text: str):
        return self.note_controller.create_text_note(pos, text)

    def begin_note_edit(self, item) -> None:
        self.note_controller.begin_note_edit(item)

    def push_history(self, command) -> None:
        if self.history_service is None:
            raise AttributeError("ToolContext requires an injected history_service")
        CanvasHistoryRecordingService(
            self.canvas,
            history_service=self.history_service,
        ).push_history(command)

    def begin_delete_tool_session(self):
        # SceneDeleteController.begin_delete_tool_session returns a
        # SceneDeleteTransactionSession, which is never None and always carries
        # the delete/commit/rollback ports.
        return self.scene_delete_controller.begin_delete_tool_session()

    @staticmethod
    def _attempt_delete_tool_session_rollback(
        session,
    ) -> tuple[bool, list[BaseException]]:
        errors: list[BaseException] = []
        try:
            errors.extend(session.rollback())
            # A rollback whose absolute restore was not authoritative, or whose
            # observer ports did not come back, deliberately leaves the session
            # active so the caller can retry it.
            completed = not session.active
        except Exception as rollback_error:
            errors.append(rollback_error)
            completed = False
        if completed:
            return True, errors
        errors.append(
            RuntimeError("Delete tool session remained active after rollback")
        )
        return False, errors

    @staticmethod
    def commit_delete_tool_session(session, command=None) -> None:
        session.commit(command)

    @staticmethod
    def rollback_delete_tool_session(session) -> list[BaseException]:
        completed, rollback_errors = ToolContext._attempt_delete_tool_session_rollback(
            session
        )
        return _DeleteSessionRollbackErrors(
            rollback_errors,
            completed=completed,
        )

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        port = self._require_port(self._bond_sets_for_atoms, "bond_sets_for_atoms")
        return port(atom_ids)

    def suspend_selection_outline(self, suspend: bool) -> None:
        self.style_controller.suspend_selection_outline(suspend)

    def apply_color_to_item(self, item, color) -> None:
        self.color_mutation_service.apply_color_to_item(item, color)

    def apply_color_to_items(self, items, color) -> None:
        self.color_mutation_service.apply_color_to_items(items, color)

    def selected_scene_items(self, *, excluded_kinds: set[str]) -> list:
        port = self._require_port(self._selected_scene_items, "selected_scene_items")
        return list(port(excluded_kinds=excluded_kinds))

    def current_atom_symbol(self) -> str:
        port = self._require_port(self._atom_symbol_provider, "atom_symbol_provider")
        return str(port())

    def set_drag_mode(self, mode) -> None:
        port = self._require_port(self._set_drag_mode, "set_drag_mode")
        port(mode)

    def set_rubber_band_drag_mode(self) -> None:
        mode = self._rubber_band_drag_mode
        if mode is None:
            raise AttributeError(
                "ToolContext requires an injected 'rubber_band_drag_mode' port"
            )
        self.set_drag_mode(mode)

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        self.handle_controller.update_handle_drag(handle, scene_pos)

    def begin_selection_3d_rotation(
        self, *, axis_hint: int | None = None, press_pos=None
    ) -> bool:
        return bool(
            self.selection_rotation_controller.begin_selection_3d_rotation(
                axis_hint=axis_hint,
                press_pos=press_pos,
            )
        )

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        self.selection_rotation_controller.update_selection_3d_rotation(
            delta_x, delta_y
        )

    def end_selection_3d_rotation(self) -> None:
        self.selection_rotation_controller.end_selection_3d_rotation()

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        self.scene_transform_controller.apply_bond_style(bond_id, style, order)

    def cycle_bond_style(self, bond_id: int) -> None:
        self.scene_transform_controller.cycle_bond_style(bond_id)

    def flip_bond_direction(self, bond_id: int) -> None:
        self.scene_transform_controller.flip_bond_direction(bond_id)


__all__ = ["ToolContext"]
