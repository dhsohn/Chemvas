from __future__ import annotations

from dataclasses import dataclass, field

from core.history import HistoryCommand

from ui.atom_label_access import add_or_update_atom_label
from ui.canvas_group_state import (
    CanvasSceneGroup,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.move_access import (
    move_item_for,
    refresh_selection_outline_for_canvas,
)
from ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from ui.scene_item_access import (
    create_scene_item_from_state as _create_scene_item_from_state,
)
from ui.scene_item_access import (
    item_is_in_canvas_scene as _item_is_in_canvas_scene,
)
from ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)


@dataclass
class MoveItemsCommand(HistoryCommand):
    items: list
    dx: float
    dy: float

    def _apply(self, canvas, dx: float, dy: float) -> None:
        for item in self.items:
            if item is None:
                continue
            if not _item_is_in_canvas_scene(canvas, item):
                continue
            move_item_for(canvas, item, dx, dy, update_selection=False)
        refresh_selection_outline_for_canvas(canvas)

    def undo(self, canvas) -> None:
        self._apply(canvas, -self.dx, -self.dy)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.dx, self.dy)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    item: object
    before_state: dict
    after_state: dict

    def undo(self, canvas) -> None:
        _apply_scene_item_state(canvas, self.item, self.before_state)

    def redo(self, canvas) -> None:
        _apply_scene_item_state(canvas, self.item, self.after_state)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        if not self.items:
            for state in self.item_states:
                self.items.append(_create_scene_item_from_state(canvas, state))
            return
        for item in self.items:
            if item is None:
                continue
            _restore_scene_item(canvas, item)

    def undo(self, canvas) -> None:
        for item in self.items:
            _remove_scene_item(canvas, item)


@dataclass
class DeleteSceneItemsCommand(HistoryCommand):
    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        for item in self.items:
            _remove_scene_item(canvas, item)

    def undo(self, canvas) -> None:
        if not self.items:
            for state in self.item_states:
                self.items.append(_create_scene_item_from_state(canvas, state))
            return
        for item in self.items:
            if item is None:
                continue
            _restore_scene_item(canvas, item)


@dataclass
class GroupSceneItemsCommand(HistoryCommand):
    atom_ids: set[int]
    items: list
    absorbed: list[tuple[int, CanvasSceneGroup]] = field(default_factory=list)
    group_id: int | None = None

    def redo(self, canvas) -> None:
        for absorbed_id, _ in self.absorbed:
            remove_group_for(canvas, absorbed_id)
        if self.group_id is None:
            self.group_id = register_group_for(canvas, self.atom_ids, self.items)
            return
        restore_group_for(
            canvas,
            self.group_id,
            CanvasSceneGroup(set(self.atom_ids), list(self.items)),
        )

    def undo(self, canvas) -> None:
        if self.group_id is not None:
            remove_group_for(canvas, self.group_id)
        for absorbed_id, group in self.absorbed:
            restore_group_for(canvas, absorbed_id, group)


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    def redo(self, canvas) -> None:
        for group_id, _ in self.removed:
            remove_group_for(canvas, group_id)

    def undo(self, canvas) -> None:
        for group_id, group in self.removed:
            restore_group_for(canvas, group_id, group)


@dataclass
class ChangeAtomLabelCommand(HistoryCommand):
    atom_id: int
    before_element: str
    after_element: str
    before_explicit_label: bool
    after_explicit_label: bool
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _apply(
        self,
        canvas,
        element: str,
        explicit_label: bool,
        smiles_input: str | None,
    ) -> None:
        add_or_update_atom_label(
            canvas,
            self.atom_id,
            element,
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=explicit_label,
        )
        set_last_smiles_input_for(canvas, smiles_input)

    def undo(self, canvas) -> None:
        self._apply(
            canvas,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
        )

    def redo(self, canvas) -> None:
        self._apply(
            canvas,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
        )


__all__ = [
    "AddSceneItemsCommand",
    "ChangeAtomLabelCommand",
    "DeleteSceneItemsCommand",
    "GroupSceneItemsCommand",
    "MoveItemsCommand",
    "UngroupSceneItemsCommand",
    "UpdateSceneItemCommand",
]
