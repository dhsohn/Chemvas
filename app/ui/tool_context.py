from __future__ import annotations

from PyQt6.QtCore import QPointF

_MISSING = object()


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
    def _callable_attr(target, name: str):
        if target is None:
            return None
        candidate = getattr(target, name, None)
        return candidate if callable(candidate) else None

    def _call_port(self, port, name: str, *args, default=_MISSING, **kwargs):
        method = self._callable_attr(port, name)
        if method is not None:
            return method(*args, **kwargs)
        if default is not _MISSING:
            return default
        raise AttributeError(f"ToolContext requires an injected '{name}' port")

    def scene_pos_from_event(self, event) -> QPointF:
        method = self._callable_attr(self.hit_testing_service, "scene_pos_from_event")
        if method is not None:
            return method(event)
        raise AttributeError("ToolContext requires an injected 'scene_pos_from_event' port")

    def item_at_scene_pos(self, pos: QPointF):
        return self._call_port(self.hit_testing_service, "item_at_scene_pos", pos, default=None)

    def item_at_event(self, event):
        method = self._callable_attr(self.hit_testing_service, "item_at_event")
        if method is not None:
            return method(event)
        item_at_scene_pos = self._callable_attr(self.hit_testing_service, "item_at_scene_pos")
        if item_at_scene_pos is not None:
            scene_pos = _MISSING
            try:
                scene_pos = self.scene_pos_from_event(event)
            except AttributeError:
                pass
            if scene_pos is not _MISSING:
                return item_at_scene_pos(scene_pos)
        return self._call_port(self.hit_testing_service, "item_at_event", event, default=None)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        return self._call_port(self.hit_testing_service, "find_atom_near", x, y, max_dist, default=None)

    def find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        return self._call_port(self.hit_testing_service, "find_bond_near", pos, max_dist, default=None)

    def bond_id_from_event(self, event) -> int | None:
        return self._call_port(self.hit_testing_service, "bond_id_from_event", event, default=None)

    def toggle_item_selection(self, item) -> bool:
        return bool(self._call_port(self.selection_controller, "toggle_item_selection", item, default=False))

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF):
        return self._call_port(
            self.selection_controller,
            "preferred_structure_hit_at_scene_pos",
            pos,
            default=None,
        )

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        return self._call_port(
            self.selection_controller,
            "preferred_structure_item_at_scene_pos",
            pos,
            default=None,
        )

    def selection_hit_test(self, pos: QPointF, snapshot=None) -> bool:
        method = self._callable_attr(self.selection_controller, "selection_hit_test")
        if method is None:
            return False
        try:
            return bool(method(pos, snapshot=snapshot))
        except TypeError as exc:
            if snapshot is None and "snapshot" in str(exc):
                return bool(method(pos))
            raise

    def select_structure_for_item(self, item) -> bool:
        return bool(self._call_port(self.selection_controller, "select_structure_for_item", item, default=False))

    def select_single_structure_item(self, item) -> bool:
        if callable(self._select_single_structure_item):
            return bool(self._select_single_structure_item(item))
        return False

    def create_text_note(self, pos: QPointF, text: str):
        return self.note_controller.create_text_note(pos, text)

    def begin_note_edit(self, item) -> None:
        self.note_controller.begin_note_edit(item)

    def push_history(self, command) -> None:
        if self.history_service is None:
            raise AttributeError("ToolContext requires an injected history_service")
        self.history_service.push(command)

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        if callable(self._bond_sets_for_atoms):
            return self._bond_sets_for_atoms(atom_ids)
        raise AttributeError("ToolContext requires an injected 'bond_sets_for_atoms' port")

    def suspend_selection_outline(self, suspend: bool) -> None:
        self._call_port(self.style_controller, "suspend_selection_outline", suspend)

    def apply_color_to_item(self, item, color) -> None:
        self._call_port(self.color_mutation_service, "apply_color_to_item", item, color)

    def selected_scene_items(self, *, excluded_kinds: set[str]) -> list:
        if callable(self._selected_scene_items):
            return list(self._selected_scene_items(excluded_kinds=excluded_kinds))
        return []

    def current_atom_symbol(self) -> str:
        if callable(self._atom_symbol_provider):
            return str(self._atom_symbol_provider())
        return ""

    def set_drag_mode(self, mode) -> None:
        if callable(self._set_drag_mode):
            self._set_drag_mode(mode)
            return
        raise AttributeError("ToolContext requires an injected 'set_drag_mode' port")

    def set_rubber_band_drag_mode(self) -> None:
        mode = self._rubber_band_drag_mode
        if mode is None:
            raise AttributeError("ToolContext requires an injected 'rubber_band_drag_mode' port")
        self.set_drag_mode(mode)

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        self.handle_controller.update_handle_drag(handle, scene_pos)

    def begin_selection_3d_rotation(self, *, axis_hint: int | None = None, press_pos=None) -> bool:
        return bool(
            self.selection_rotation_controller.begin_selection_3d_rotation(
                axis_hint=axis_hint,
                press_pos=press_pos,
            )
        )

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        self.selection_rotation_controller.update_selection_3d_rotation(delta_x, delta_y)

    def end_selection_3d_rotation(self) -> None:
        self.selection_rotation_controller.end_selection_3d_rotation()

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        self.scene_transform_controller.apply_bond_style(bond_id, style, order)

    def cycle_bond_style(self, bond_id: int) -> None:
        self.scene_transform_controller.cycle_bond_style(bond_id)

    def flip_bond_direction(self, bond_id: int) -> None:
        self.scene_transform_controller.flip_bond_direction(bond_id)


__all__ = ["ToolContext"]
