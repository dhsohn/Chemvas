from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.canvas_scene_items_state import set_selected_notes_for
from ui.selection_collection_access import (
    selection_status_count_for,
    selection_status_item_identity,
)
from ui.selection_scene_access import (
    clear_scene_selection_for,
    scene_selected_items_for,
    set_scene_items_selected_for,
)
from ui.selection_service_access import (
    select_single_structure_item_for,
    selection_targets_for_item_for,
)


class _Item:
    def __init__(self, kind: str, item_id=None, *, ring_ids=None, scene=None) -> None:
        self._kind = kind
        self._item_id = item_id
        self._ring_ids = ring_ids
        self._scene = scene
        self._selected = False
        self.selected_calls = []

    def data(self, index: int):
        if index == 0:
            return self._kind
        if index == 1:
            return self._item_id
        if index == 2:
            return self._ring_ids
        return None

    def scene(self):
        return self._scene

    def setSelected(self, selected: bool) -> None:
        self.selected_calls.append(selected)
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected


class _Scene:
    def __init__(self, selected_items: list[_Item]) -> None:
        self._selected_items = selected_items
        self.block_signal_calls = []
        self.clear_selection_calls = 0

    def selectedItems(self) -> list[_Item]:
        return self._selected_items

    def blockSignals(self, blocked: bool) -> None:
        self.block_signal_calls.append(blocked)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1


def test_selection_status_item_identity_uses_stable_structure_ids() -> None:
    atom = _Item("atom", 7)
    bond = _Item("bond", 11)
    ring = _Item("ring", ring_ids=[1, 2, 3])
    custom = _Item("arrow", "x")

    assert selection_status_item_identity(atom) == ("atom", 7)
    assert selection_status_item_identity(bond) == ("bond", 11)
    assert selection_status_item_identity(ring) == ("ring", (1, 2, 3))
    assert selection_status_item_identity(custom) == ("item", id(custom))


def test_selection_status_count_dedupes_structures_and_includes_selected_notes() -> None:
    atom = _Item("atom", 1)
    duplicate_atom = _Item("atom", 1)
    bond = _Item("bond", 2)
    ring = _Item("ring", ring_ids=[1, 2, 3, 4, 5, 6])
    custom = _Item("arrow", "a")
    handle = _Item("handle")
    outline = _Item("selection_outline")
    scene = _Scene([atom, duplicate_atom, bond, ring, custom, handle, outline])
    note = _Item("note", "n1", scene=scene)
    outside_note = _Item("note", "n2", scene=object())
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    set_selected_notes_for(canvas, [note, outside_note])

    assert selection_status_count_for(canvas) == 5


def test_selection_status_count_handles_missing_scene() -> None:
    assert selection_status_count_for(SimpleNamespace()) == 0


def test_scene_selected_items_for_reads_scene_selection() -> None:
    selected_items = [_Item("atom", 1), _Item("bond", 2)]
    scene = _Scene(selected_items)
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    assert scene_selected_items_for(canvas) == selected_items

    canvas.scene.assert_called_once_with()


def test_clear_scene_selection_for_clears_with_optional_signal_blocking() -> None:
    scene = _Scene([])
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    clear_scene_selection_for(canvas, block_signals=True)

    assert scene.block_signal_calls == [True, False]
    assert scene.clear_selection_calls == 1


def test_set_scene_items_selected_for_sets_selection_with_signal_blocking() -> None:
    first = _Item("atom", 1)
    second = _Item("bond", 2)
    scene = _Scene([])
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    set_scene_items_selected_for(canvas, [first, second], True)

    assert scene.block_signal_calls == [True, False]
    assert first.selected_calls == [True]
    assert second.selected_calls == [True]


def test_set_scene_items_selected_for_handles_missing_scene() -> None:
    item = _Item("atom", 1)

    set_scene_items_selected_for(SimpleNamespace(), [item], False)

    assert item.selected_calls == [False]


def test_select_single_structure_item_for_uses_selection_controller_targets() -> None:
    item = object()
    target = _Item("atom", 1)
    scene = _Scene([])
    selection_controller = SimpleNamespace(selection_targets_for_item=mock.Mock(return_value=[target, None]))
    canvas = SimpleNamespace(
        services=SimpleNamespace(selection_controller=selection_controller),
        scene=mock.Mock(return_value=scene),
    )

    assert selection_targets_for_item_for(canvas, item) == [target]
    assert select_single_structure_item_for(canvas, item)

    selection_controller.selection_targets_for_item.assert_has_calls([mock.call(item), mock.call(item)])
    assert scene.clear_selection_calls == 1
    assert target.selected_calls == [True]
