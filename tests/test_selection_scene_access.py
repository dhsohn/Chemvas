from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from chemvas.ui.canvas_scene_items_state import set_selected_notes_for
from chemvas.ui.selection_scene_access import (
    clear_scene_selection_for,
    scene_selected_items_for,
    selected_scene_notes_for,
    set_scene_items_selected_for,
)
from PyQt6 import sip
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)


class _Item:
    def __init__(self, scene=None) -> None:
        self._scene = scene
        self._selected = False
        self.selected_calls = []

    def scene(self):
        return self._scene

    def setSelected(self, selected: bool) -> None:
        self.selected_calls.append(selected)
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected


class _Scene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])
        self.block_signal_calls = []
        self.clear_selection_calls = 0
        self.blocked = False

    def selectedItems(self):
        return list(self._selected_items)

    def signalsBlocked(self) -> bool:
        return self.blocked

    def blockSignals(self, blocked: bool) -> bool:
        self.block_signal_calls.append(blocked)
        previous = self.blocked
        self.blocked = blocked
        return previous

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1


def _qt_scene_with_selected_rects(count: int) -> tuple[QGraphicsScene, list]:
    scene = QGraphicsScene()
    items = []
    for index in range(count):
        item = QGraphicsRectItem(0, 0, 10 + index, 10 + index)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
        item.setSelected(True)
        items.append(item)
    return scene, items


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
    assert (
        selected_scene_notes_for(
            SimpleNamespace(scene=mock.Mock(side_effect=RuntimeError("deleted")))
        )
        == []
    )


def test_clear_scene_selection_for_clears_with_optional_signal_blocking() -> None:
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    assert clear_scene_selection_for(canvas, block_signals=True) is True

    assert scene.block_signal_calls == [True, False]
    assert scene.clear_selection_calls == 1


def test_clear_scene_selection_for_handles_missing_scene() -> None:
    assert clear_scene_selection_for(SimpleNamespace()) is False
    with pytest.raises(RuntimeError, match="live scene failed"):
        clear_scene_selection_for(
            SimpleNamespace(
                scene=mock.Mock(side_effect=RuntimeError("live scene failed"))
            )
        )


def test_clear_scene_selection_for_tolerates_deleted_qt_canvas() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = QGraphicsView(QGraphicsScene())
    sip.delete(canvas)

    assert clear_scene_selection_for(canvas, block_signals=True) is False


def test_clear_scene_selection_for_clears_a_real_qt_scene() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene, items = _qt_scene_with_selected_rects(2)
    canvas = QGraphicsView(scene)

    assert clear_scene_selection_for(canvas, block_signals=True) is True

    assert scene.selectedItems() == []
    assert not any(item.isSelected() for item in items)
    assert scene.signalsBlocked() is False


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


def test_set_scene_items_selected_for_selects_real_qt_items() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene, items = _qt_scene_with_selected_rects(2)
    canvas = QGraphicsView(scene)
    set_scene_items_selected_for(canvas, items, False)
    assert scene.selectedItems() == []

    set_scene_items_selected_for(canvas, items, True, block_signals=False)

    assert set(scene.selectedItems()) == set(items)
    assert scene.signalsBlocked() is False


def test_set_scene_items_selected_for_preserves_an_already_blocked_scene() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene, items = _qt_scene_with_selected_rects(1)
    canvas = QGraphicsView(scene)
    scene.blockSignals(True)

    set_scene_items_selected_for(canvas, items, False)

    assert scene.selectedItems() == []
    assert scene.signalsBlocked() is True
    scene.blockSignals(False)
