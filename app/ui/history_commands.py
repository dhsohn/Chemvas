from __future__ import annotations

from dataclasses import dataclass, field

from core.history import HistoryCommand

from ui.atom_label_access import add_or_update_atom_label
from ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from ui.scene_item_access import (
    create_scene_item_from_state as _create_scene_item_from_state,
)
from ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)


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
        canvas.last_smiles_input = smiles_input

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
    "UpdateSceneItemCommand",
]
