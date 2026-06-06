from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.canvas_scene_items_state import set_selected_notes_for
from ui.selection_scene_access import (
    clear_scene_selection_for,
    scene_selected_items_for,
    selected_scene_notes_for,
    set_scene_items_selected_for,
)


class _Item:
    def __init__(self, scene=None) -> None:
        self._scene = scene
        self.selected_calls = []

    def scene(self):
        return self._scene

    def setSelected(self, selected: bool) -> None:
        self.selected_calls.append(selected)


class _Scene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])
        self.block_signal_calls = []
        self.clear_selection_calls = 0

    def selectedItems(self):
        return list(self._selected_items)

    def blockSignals(self, blocked: bool) -> None:
        self.block_signal_calls.append(blocked)

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1


def test_scene_selected_items_for_reads_scene_selection() -> None:
    selected_items = [_Item()]
    scene = _Scene(selected_items)
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    assert scene_selected_items_for(canvas) == selected_items
    canvas.scene.assert_called_once_with()


def test_scene_selected_items_for_handles_deleted_canvas_wrapper() -> None:
    canvas = SimpleNamespace(scene=mock.Mock(side_effect=RuntimeError("deleted")))

    assert scene_selected_items_for(canvas) == []


def test_selected_scene_notes_for_filters_notes_attached_to_canvas_scene() -> None:
    scene = _Scene()
    note = _Item(scene)
    outside_note = _Item(object())
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    set_selected_notes_for(canvas, [note, outside_note])

    assert selected_scene_notes_for(canvas) == [note]


def test_selected_scene_notes_for_ignores_deleted_notes_and_canvas() -> None:
    scene = _Scene()
    deleted_note = mock.Mock()
    deleted_note.scene.side_effect = RuntimeError("deleted")
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    set_selected_notes_for(canvas, [deleted_note])

    assert selected_scene_notes_for(canvas) == []
    assert selected_scene_notes_for(SimpleNamespace(scene=mock.Mock(side_effect=RuntimeError("deleted")))) == []


def test_clear_scene_selection_for_clears_with_optional_signal_blocking() -> None:
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    assert clear_scene_selection_for(canvas, block_signals=True) is True

    assert scene.block_signal_calls == [True, False]
    assert scene.clear_selection_calls == 1


def test_clear_scene_selection_for_handles_missing_scene() -> None:
    assert clear_scene_selection_for(SimpleNamespace()) is False
    assert clear_scene_selection_for(SimpleNamespace(scene=mock.Mock(side_effect=RuntimeError("deleted")))) is False


def test_set_scene_items_selected_for_sets_selection_with_signal_blocking() -> None:
    first = _Item()
    second = _Item()
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    set_scene_items_selected_for(canvas, [first, second], True)

    assert scene.block_signal_calls == [True, False]
    assert first.selected_calls == [True]
    assert second.selected_calls == [True]


def test_set_scene_items_selected_for_handles_missing_scene() -> None:
    item = _Item()

    set_scene_items_selected_for(SimpleNamespace(), [item], False)

    assert item.selected_calls == [False]
