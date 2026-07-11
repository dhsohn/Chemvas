from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsWidget,
)
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


def test_set_scene_items_selected_for_sets_selection_with_signal_blocking() -> None:
    first = _Item()
    second = _Item()
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    set_scene_items_selected_for(canvas, [first, second], True)

    assert scene.block_signal_calls == [True, False]
    assert first.selected_calls == [True]
    assert second.selected_calls == [True]


def test_blocked_fake_selection_failure_restores_callback_mutated_peer() -> None:
    primary = RuntimeError("target failed after selecting a peer")

    class FailingItem(_Item):
        def __init__(self, peer: _Item) -> None:
            super().__init__()
            self.peer = peer

        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                self.peer._selected = True
                raise primary

    peer = _Item()
    target = FailingItem(peer)
    scene = _Scene()
    scene.items = [target, peer]
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(canvas, [target], True, block_signals=True)

    assert raised.value is primary
    assert target.isSelected() is False
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_blocked_fake_selection_rejects_successful_peer_mutation() -> None:
    peer = _Item()

    class MutatingItem(_Item):
        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                peer._selected = True

    target = MutatingItem()
    scene = _Scene()
    scene.items = [target, peer]

    with pytest.raises(RuntimeError, match="changed a non-target peer"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
            block_signals=True,
        )

    assert target.isSelected() is False
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_blocked_qt_selection_bypasses_failing_peer_mutating_override() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    primary = RuntimeError("Qt target failed after selecting a peer")

    class FailingItem(QGraphicsRectItem):
        def __init__(self, peer: QGraphicsItem) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.peer = peer
            self.override_calls = 0

        def setSelected(self, selected: bool) -> None:
            self.override_calls += 1
            QGraphicsItem.setSelected(self, selected)
            if selected:
                QGraphicsItem.setSelected(self.peer, True)
                raise primary

    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)
    target = FailingItem(peer)
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [target],
        True,
        block_signals=True,
    )

    assert target.override_calls == 0
    assert QGraphicsItem.isSelected(target) is True
    assert QGraphicsItem.isSelected(peer) is False
    assert scene.signalsBlocked() is False


def test_blocked_qt_selection_bypasses_successful_peer_mutating_override() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)

    class MutatingItem(QGraphicsRectItem):
        override_calls = 0

        def setSelected(self, selected: bool) -> None:
            self.override_calls += 1
            QGraphicsItem.setSelected(self, selected)
            if selected:
                QGraphicsItem.setSelected(peer, True)

    target = MutatingItem(0.0, 0.0, 10.0, 10.0)
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [target],
        True,
        block_signals=True,
    )

    assert target.override_calls == 0
    assert QGraphicsItem.isSelected(target) is True
    assert QGraphicsItem.isSelected(peer) is False
    assert QGraphicsScene.selectedItems(scene) == [target]
    assert scene.signalsBlocked() is False


def test_qt_selection_bypasses_membership_detaching_override() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    primary = RuntimeError("selection detached a peer before failing")
    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)

    class DetachingItem(QGraphicsRectItem):
        override_calls = 0

        def setSelected(self, selected: bool) -> None:
            self.override_calls += 1
            QGraphicsItem.setSelected(self, selected)
            if selected:
                QGraphicsScene.removeItem(scene, peer)
                raise primary

    target = DetachingItem(0.0, 0.0, 10.0, 10.0)
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    expected_order = tuple(QGraphicsScene.items(scene))

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [target],
        True,
    )

    assert target.override_calls == 0
    assert tuple(QGraphicsScene.items(scene)) == expected_order
    assert all(item.scene() is scene for item in expected_order)
    assert QGraphicsItem.isSelected(target)


def test_qt_selection_uses_base_port_before_override_can_delete_peer() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)

    class DeletingOverrideItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.override_calls = 0

        def setSelected(self, selected: bool) -> None:
            self.override_calls += 1
            QGraphicsItem.setSelected(self, selected)
            if selected:
                QGraphicsScene.removeItem(scene, peer)
                sip.delete(peer)
                raise RuntimeError("Qt selection override deleted a peer")

    target = DeletingOverrideItem()
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    expected_items = tuple(QGraphicsScene.items(scene))

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [target],
        True,
        block_signals=True,
    )

    assert target.override_calls == 0
    assert tuple(QGraphicsScene.items(scene)) == expected_items
    assert not sip.isdeleted(peer)
    assert QGraphicsItem.isSelected(target)
    assert not QGraphicsItem.isSelected(peer)
    assert not scene.signalsBlocked()
    QGraphicsScene.clear(scene)


def test_qt_selection_rejects_deleting_item_change_before_mutation() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)

    class DeletingItemChangeItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.armed = False

        def itemChange(self, change, value):
            if (
                self.armed
                and change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange
                and bool(value)
            ):
                self.armed = False
                QGraphicsScene.removeItem(scene, peer)
                sip.delete(peer)
            return QGraphicsRectItem.itemChange(self, change, value)

    target = DeletingItemChangeItem()
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    expected_items = tuple(QGraphicsScene.items(scene))
    target.armed = True

    with pytest.raises(RuntimeError, match="Python itemChange override"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
            block_signals=True,
        )

    assert target.armed is True
    assert not sip.isdeleted(peer)
    assert tuple(QGraphicsScene.items(scene)) == expected_items
    assert not QGraphicsItem.isSelected(target)
    assert not scene.signalsBlocked()
    target.armed = False
    QGraphicsScene.clear(scene)


def test_qt_clear_rejects_deleting_item_change_before_mutation() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)

    class DeletingItemChangeItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.armed = False

        def itemChange(self, change, value):
            if (
                self.armed
                and change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange
                and not bool(value)
            ):
                self.armed = False
                QGraphicsScene.removeItem(scene, peer)
                sip.delete(peer)
            return QGraphicsRectItem.itemChange(self, change, value)

    target = DeletingItemChangeItem()
    scene.addItem(target)
    for item in (target, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    QGraphicsItem.setSelected(target, True)
    expected_items = tuple(QGraphicsScene.items(scene))
    target.armed = True

    with pytest.raises(RuntimeError, match="Python itemChange override"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert target.armed is True
    assert not sip.isdeleted(peer)
    assert tuple(QGraphicsScene.items(scene)) == expected_items
    assert QGraphicsItem.isSelected(target)
    assert not scene.signalsBlocked()
    target.armed = False
    QGraphicsScene.clear(scene)


def test_qt_selection_allows_standard_cpp_item_change_override() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = QGraphicsWidget()
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(item)
    canvas = SimpleNamespace(scene=lambda: scene)

    set_scene_items_selected_for(canvas, [item], True, block_signals=True)

    assert QGraphicsItem.isSelected(item)
    assert clear_scene_selection_for(canvas, block_signals=True)
    assert not QGraphicsItem.isSelected(item)
    assert not scene.signalsBlocked()
    QGraphicsScene.clear(scene)


def test_qt_clear_allows_python_item_change_override_when_noop() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class TrackingItemChangeItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.selection_changes = 0

        def itemChange(self, change, value):
            if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
                self.selection_changes += 1
            return QGraphicsRectItem.itemChange(self, change, value)

    item = TrackingItemChangeItem()
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(item)

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )

    assert item.selection_changes == 0
    assert not QGraphicsItem.isSelected(item)
    assert not scene.signalsBlocked()
    QGraphicsScene.clear(scene)


def test_qt_set_allows_python_item_change_override_when_noop() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class TrackingItemChangeItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.selection_changes = 0

        def itemChange(self, change, value):
            if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
                self.selection_changes += 1
            return QGraphicsRectItem.itemChange(self, change, value)

    item = TrackingItemChangeItem()
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(item)
    QGraphicsItem.setSelected(item, True)
    item.selection_changes = 0

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [item],
        True,
        block_signals=True,
    )

    assert item.selection_changes == 0
    assert QGraphicsItem.isSelected(item)
    assert not scene.signalsBlocked()
    QGraphicsScene.clear(scene)


def test_qt_canvas_scene_override_cannot_delete_peer_before_capture() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class DeletingSceneOverrideView(QGraphicsView):
        def __init__(self) -> None:
            self.armed = False
            self.peer: QGraphicsItem | None = None
            self.override_calls = 0
            super().__init__(scene)

        def scene(self) -> QGraphicsScene | None:
            self.override_calls += 1
            current = QGraphicsView.scene(self)
            if self.armed and current is not None and self.peer is not None:
                self.armed = False
                QGraphicsScene.removeItem(current, self.peer)
                sip.delete(self.peer)
            return current

    canvas = DeletingSceneOverrideView()
    target = scene.addRect(0.0, 0.0, 10.0, 10.0)
    peer = scene.addRect(20.0, 0.0, 10.0, 10.0)
    canvas.peer = peer
    target.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    expected_items = tuple(QGraphicsScene.items(scene))
    calls_before = canvas.override_calls
    canvas.armed = True

    set_scene_items_selected_for(canvas, [target], True)

    assert canvas.override_calls == calls_before
    assert canvas.armed is True
    assert tuple(QGraphicsScene.items(scene)) == expected_items
    assert not sip.isdeleted(peer)
    assert QGraphicsItem.isSelected(target)
    assert not QGraphicsItem.isSelected(peer)
    canvas.armed = False
    QGraphicsScene.clear(scene)
    canvas.close()
    app.processEvents()


def test_selection_capture_rejects_and_restores_non_qt_membership_reorder() -> None:
    class ReorderingItem(_Item):
        armed = True

        def isSelected(self) -> bool:
            if self.armed:
                self.armed = False
                scene.items.reverse()
            return super().isSelected()

    target = ReorderingItem()
    peer = _Item()
    scene = _Scene()
    scene.items = [target, peer]

    with pytest.raises(RuntimeError, match="selection capture changed authoritative"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
        )

    assert scene.items == [target, peer]
    assert target.armed is True
    assert target._selected is False


def test_fake_clear_selection_failure_restores_exact_selection_frontier() -> None:
    primary = RuntimeError("fake clear failed after partial mutation")
    first = _Item()
    second = _Item()
    peer = _Item()
    first._selected = True
    second._selected = True

    class FailingScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [first, second, peer]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            first._selected = False
            peer._selected = True
            raise primary

    scene = FailingScene()

    with pytest.raises(RuntimeError) as raised:
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert raised.value is primary
    assert first.isSelected() is True
    assert second.isSelected() is True
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_unblocked_clear_uses_exact_rollback_without_signal_ports() -> None:
    primary = RuntimeError("unblocked sparse clear failed after partial mutation")
    selected = _Item()
    peer = _Item()
    selected._selected = True

    class SceneWithoutSignalPorts:
        def __init__(self) -> None:
            self.items = [selected, peer]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            selected._selected = False
            peer._selected = True
            raise primary

    scene = SceneWithoutSignalPorts()

    with pytest.raises(RuntimeError) as raised:
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=False,
        )

    assert raised.value is primary
    assert selected.isSelected() is True
    assert peer.isSelected() is False
    assert scene.items == [selected, peer]


def test_clear_selection_retry_closes_on_true_after_false_peer_callback() -> None:
    primary = RuntimeError("clear failed before reciprocal recovery")
    selected = _Item()
    selected._selected = True

    class DeselectingPeer(_Item):
        def __init__(self, target: _Item) -> None:
            super().__init__()
            self.target = target

        def setSelected(self, value: bool) -> None:
            super().setSelected(value)
            if not value:
                self.target._selected = False

    peer = DeselectingPeer(selected)

    class FailingScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [selected, peer]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            selected._selected = False
            raise primary

    scene = FailingScene()

    with pytest.raises(RuntimeError) as raised:
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert raised.value is primary
    assert selected.isSelected() is True
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_clear_selection_retry_reverses_items_within_the_same_state() -> None:
    primary = RuntimeError("clear failed before same-state recovery")
    first = _Item()
    first._selected = True

    class DeselectingSelectedPeer(_Item):
        def setSelected(self, value: bool) -> None:
            super().setSelected(value)
            if value:
                first._selected = False

    second = DeselectingSelectedPeer()
    second._selected = True

    class FailingScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [first, second]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            first._selected = False
            second._selected = False
            raise primary

    scene = FailingScene()

    with pytest.raises(RuntimeError) as raised:
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert raised.value is primary
    assert first.isSelected() is True
    assert second.isSelected() is True
    assert scene.signalsBlocked() is False


def test_clear_success_does_not_reenter_untrusted_selected_items_reader() -> None:
    peer = _Item()

    class MutatingVerificationScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [peer]
            self.selected_item_reads = 0

        def selectedItems(self):
            self.selected_item_reads += 1
            if self.selected_item_reads > 1:
                peer._selected = True
            return []

        def clearSelection(self) -> None:
            peer._selected = False

    scene = MutatingVerificationScene()

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )

    assert scene.selected_item_reads == 1
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_clear_capture_rejects_and_restores_signal_getter_poisoning() -> None:
    class SignalPoisoningScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = []
            self.armed = True

        def selectedItems(self):
            if self.armed:
                self.armed = False
                self.blocked = True
            return []

    scene = SignalPoisoningScene()

    with pytest.raises(RuntimeError, match="selection capture changed authoritative"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert scene.blocked is False
    assert scene.armed is True
    assert scene.clear_selection_calls == 0


def test_clear_capture_detects_nonstandard_signal_state_poisoning() -> None:
    class SignalPoisoningScene:
        def __init__(self) -> None:
            self.items = []
            self.signal_flag = False
            self.clear_calls = 0

        def selectedItems(self):
            self.signal_flag = True
            return []

        def clearSelection(self) -> None:
            self.clear_calls += 1

        def blockSignals(self, blocked: bool) -> bool:
            previous = self.signal_flag
            self.signal_flag = blocked
            return previous

        def signalsBlocked(self) -> bool:
            return self.signal_flag

    scene = SignalPoisoningScene()

    with pytest.raises(RuntimeError, match="selection capture changed authoritative"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert scene.signal_flag is False
    assert scene.clear_calls == 0


def test_clear_capture_restores_external_non_qt_signal_state() -> None:
    external_state = SimpleNamespace(blocked=False)

    class ExternalSignalScene:
        def __init__(self) -> None:
            self.items = []
            self.clear_calls = 0

        def selectedItems(self):
            external_state.blocked = True
            return []

        def clearSelection(self) -> None:
            self.clear_calls += 1

        def blockSignals(self, blocked: bool) -> bool:
            previous = external_state.blocked
            external_state.blocked = blocked
            return previous

        def signalsBlocked(self) -> bool:
            return external_state.blocked

    scene = ExternalSignalScene()

    with pytest.raises(RuntimeError, match="selection capture changed authoritative"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert external_state.blocked is False
    assert scene.clear_calls == 0


@pytest.mark.parametrize("operation", ["set", "clear"])
def test_signal_getter_poisoning_is_rejected_before_selection_mutation(
    operation: str,
) -> None:
    item = _Item()
    item._selected = operation == "clear"

    class SignalGetterPoisoningScene(_Scene):
        def __init__(self) -> None:
            super().__init__([item] if item.isSelected() else [])
            self.items = [item]
            self.armed = True

        def selectedItems(self):
            return [candidate for candidate in self.items if candidate.isSelected()]

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            item._selected = False
            self._selected_items.clear()

        def signalsBlocked(self) -> bool:
            if self.armed:
                self.armed = False
                self.blocked = True
            return self.blocked

    scene = SignalGetterPoisoningScene()
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(
        RuntimeError,
        match="signal-state capture changed raw authority",
    ):
        if operation == "set":
            set_scene_items_selected_for(
                canvas,
                [item],
                True,
                block_signals=True,
            )
        else:
            clear_scene_selection_for(canvas, block_signals=True)

    assert item.isSelected() is (operation == "clear")
    assert scene.blocked is False
    assert scene.armed is True
    assert scene.clear_selection_calls == 0


def test_unknown_fake_selection_storage_uses_compatibility_clear() -> None:
    class Item:
        def __init__(self) -> None:
            self.flag = True

        def isSelected(self) -> bool:
            return self.flag

        def setSelected(self, selected: bool) -> None:
            self.flag = selected

    item = Item()

    class Scene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [item]

        def selectedItems(self):
            return [item] if item.isSelected() else []

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            item.flag = False

    scene = Scene()

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )
    assert item.isSelected() is False
    assert scene.clear_selection_calls == 1


def test_compatibility_clear_rejects_a_public_only_noop() -> None:
    class Item:
        def __init__(self) -> None:
            self.flag = True

        def isSelected(self) -> bool:
            return self.flag

        def setSelected(self, selected: bool) -> None:
            self.flag = selected

    item = Item()

    class Scene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [item]

        def selectedItems(self):
            return [item] if item.isSelected() else []

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1

    scene = Scene()

    with pytest.raises(RuntimeError, match="compatible.*left an item selected"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert item.isSelected() is True
    assert scene.clear_selection_calls == 1
    assert scene.signalsBlocked() is False


def test_compatibility_clear_rejects_and_restores_membership_reordering() -> None:
    class Item:
        def __init__(self, selected: bool) -> None:
            self.flag = selected

        def isSelected(self) -> bool:
            return self.flag

        def setSelected(self, selected: bool) -> None:
            self.flag = selected

    target = Item(True)
    peer = Item(False)

    class ReorderingScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [target, peer]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            target.flag = False
            self.items.reverse()

    scene = ReorderingScene()

    with pytest.raises(RuntimeError, match="membership/order"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert scene.items == [target, peer]
    assert target.isSelected() is True
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_normal_partial_clear_is_rejected_and_restores_full_frontier() -> None:
    first = _Item()
    second = _Item()
    peer = _Item()
    first._selected = True
    second._selected = True

    class PartiallyClearingScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [first, second, peer]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            first._selected = False
            peer._selected = True

    scene = PartiallyClearingScene()

    with pytest.raises(RuntimeError, match="selection clear left"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert scene.clear_selection_calls == 1
    assert first.isSelected() is True
    assert second.isSelected() is True
    assert peer.isSelected() is False
    assert scene.signalsBlocked() is False


def test_qt_clear_selection_bypasses_membership_mutating_override() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    primary = RuntimeError("Qt clear failed after partial mutation")

    class FailingScene(QGraphicsScene):
        first: QGraphicsItem
        peer: QGraphicsItem
        clear_override_calls = 0

        def clearSelection(self) -> None:
            self.clear_override_calls += 1
            QGraphicsItem.setSelected(self.first, False)
            QGraphicsItem.setSelected(self.peer, True)
            raise primary

    scene = FailingScene()
    first = scene.addRect(0.0, 0.0, 10.0, 10.0)
    second = scene.addRect(20.0, 0.0, 10.0, 10.0)
    peer = scene.addRect(40.0, 0.0, 10.0, 10.0)
    for item in (first, second, peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    first.setSelected(True)
    second.setSelected(True)
    scene.first = first
    scene.peer = peer

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )

    assert scene.clear_override_calls == 0
    assert first.isSelected() is False
    assert second.isSelected() is False
    assert peer.isSelected() is False
    assert all(item.scene() is scene for item in (first, second, peer))
    assert scene.signalsBlocked() is False


def test_qt_base_clear_ignores_overridden_item_selection_ports() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    primary = RuntimeError("Qt clear failed after base deselection")

    class LyingItem(QGraphicsRectItem):
        def isSelected(self) -> bool:
            return False

        def setSelected(self, selected: bool) -> None:
            if not selected:
                QGraphicsItem.setSelected(self, False)

    class FailingScene(QGraphicsScene):
        clear_override_calls = 0

        def clearSelection(self) -> None:
            self.clear_override_calls += 1
            QGraphicsScene.clearSelection(self)
            raise primary

    scene = FailingScene()
    item = LyingItem(0.0, 0.0, 10.0, 10.0)
    scene.addItem(item)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    QGraphicsItem.setSelected(item, True)

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )

    assert scene.clear_override_calls == 0
    assert QGraphicsItem.isSelected(item) is False
    assert item.scene() is scene
    assert scene.signalsBlocked() is False


def test_fake_full_scene_capture_ignores_unrelated_scene_containers() -> None:
    actual = _Item()
    unrelated = _Item()
    unrelated._selected = True

    class SceneWithAuditItems(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [actual]
            self.audit = [unrelated]

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            actual._selected = False

    scene = SceneWithAuditItems()

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )
    assert actual.isSelected() is False
    assert unrelated.isSelected() is True


def test_fake_full_scene_capture_does_not_call_incompatible_items_port() -> None:
    target = _Item()
    target._selected = True

    class SceneWithKeyedItems(_Scene):
        def __init__(self) -> None:
            super().__init__([target])
            self.items_calls = 0

        def items(self, _key):
            self.items_calls += 1
            return [target]

        def clearSelection(self) -> None:
            target._selected = False
            self._selected_items.clear()

    scene = SceneWithKeyedItems()

    assert clear_scene_selection_for(
        SimpleNamespace(scene=lambda: scene),
        block_signals=True,
    )
    assert scene.items_calls == 0
    assert target.isSelected() is False


def test_set_scene_items_selected_for_handles_missing_scene() -> None:
    item = _Item()

    set_scene_items_selected_for(SimpleNamespace(), [item], False)

    assert item.selected_calls == [False]


def test_set_scene_items_selected_rejects_a_noop_setter() -> None:
    class NoOpItem(_Item):
        def setSelected(self, selected: bool) -> None:
            self.selected_calls.append(selected)

    item = NoOpItem()
    scene = _Scene()
    scene.items = [item]

    with pytest.raises(
        RuntimeError,
        match="selection setter did not apply",
    ):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
            block_signals=True,
        )

    assert item.isSelected() is False
    assert scene.signalsBlocked() is False


def test_set_selection_rejects_raw_state_that_disagrees_with_public_getter() -> None:
    class PubliclyUnselectedItem(_Item):
        def isSelected(self) -> bool:
            return False

    item = PubliclyUnselectedItem()
    scene = _Scene()
    scene.items = [item]

    with pytest.raises(
        RuntimeError,
        match="public getter disagrees with raw authority",
    ):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
            block_signals=True,
        )

    assert item._selected is False
    assert item.isSelected() is False
    assert scene.selectedItems() == []
    assert scene.signalsBlocked() is False


def test_clear_rejects_raw_state_that_disagrees_with_public_getter() -> None:
    class PubliclySelectedItem(_Item):
        def isSelected(self) -> bool:
            return True

    item = PubliclySelectedItem()
    item._selected = True

    class Scene(_Scene):
        def __init__(self) -> None:
            super().__init__([item])
            self.items = [item]

        def selectedItems(self):
            return [item] if item.isSelected() else []

        def clearSelection(self) -> None:
            item._selected = False
            self._selected_items.clear()

    scene = Scene()

    with pytest.raises(
        RuntimeError,
        match="public getter disagrees with raw authority",
    ):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert item._selected is True
    assert item.isSelected() is True
    assert scene.selectedItems() == [item]
    assert scene.signalsBlocked() is False


def test_clear_rejects_and_restores_a_stale_raw_selection_container() -> None:
    item = _Item()
    item._selected = True

    class Scene(_Scene):
        def __init__(self) -> None:
            super().__init__([item])
            self.items = [item]

        def clearSelection(self) -> None:
            item._selected = False

    scene = Scene()
    selected_items = scene._selected_items

    with pytest.raises(
        RuntimeError,
        match="raw selection container populated",
    ):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert item.isSelected() is True
    assert scene._selected_items is selected_items
    assert scene.selectedItems() == [item]
    assert scene.signalsBlocked() is False


def test_selection_authority_uses_the_field_matching_live_semantics() -> None:
    class CollidingSelectionFields:
        def __init__(self) -> None:
            self._selected = True
            self.selected = False
            self.calls: list[bool] = []

        def isSelected(self) -> bool:
            return self.selected

        def setSelected(self, selected: bool) -> None:
            self.calls.append(selected)

    item = CollidingSelectionFields()

    with pytest.raises(RuntimeError, match="selection setter did not apply"):
        set_scene_items_selected_for(SimpleNamespace(), [item], True)

    assert item.isSelected() is False
    assert item._selected is True
    assert item.selected is False
    assert item.calls == [True]


def test_set_rejects_a_non_qt_getter_that_poisons_final_raw_authority() -> None:
    class FinalReadPoisoningItem(_Item):
        def __init__(self) -> None:
            super().__init__()
            self.armed = False
            self.verification_reads = 0

        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                self.armed = True
                self.verification_reads = 0

        def isSelected(self) -> bool:
            captured = self._selected
            if self.armed:
                self.verification_reads += 1
                if self.verification_reads == 2:
                    self._selected = not captured
                    self.armed = False
            return captured

    item = FinalReadPoisoningItem()
    scene = _Scene()
    scene.items = [item]

    with pytest.raises(RuntimeError, match="callback-free postcondition"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
            block_signals=True,
        )

    assert item._selected is False
    assert scene.signalsBlocked() is False


def test_clear_rejects_a_non_qt_getter_that_reselects_on_final_read() -> None:
    class FinalReadPoisoningItem(_Item):
        def __init__(self) -> None:
            super().__init__()
            self._selected = True
            self.armed = False
            self.verification_reads = 0

        def isSelected(self) -> bool:
            captured = self._selected
            if self.armed:
                self.verification_reads += 1
                if self.verification_reads == 2:
                    self._selected = True
                    self.armed = False
            return captured

    item = FinalReadPoisoningItem()

    class Scene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.items = [item]

        def selectedItems(self):
            return [candidate for candidate in self.items if candidate._selected]

        def clearSelection(self) -> None:
            item._selected = False
            item.armed = True
            item.verification_reads = 0

    scene = Scene()

    with pytest.raises(RuntimeError, match="callback-free item selected"):
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=True,
        )

    assert item._selected is True
    assert scene.signalsBlocked() is False


def test_set_bypasses_qt_getter_and_setter_overrides() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class FinalReadPoisoningItem(QGraphicsRectItem):
        def __init__(self) -> None:
            super().__init__(0.0, 0.0, 10.0, 10.0)
            self.armed = False
            self.verification_reads = 0

        def setSelected(self, selected: bool) -> None:
            QGraphicsItem.setSelected(self, selected)
            if selected:
                self.armed = True
                self.verification_reads = 0

        def isSelected(self) -> bool:
            captured = bool(QGraphicsItem.isSelected(self))
            if self.armed:
                self.verification_reads += 1
                if self.verification_reads == 2:
                    QGraphicsItem.setSelected(self, not captured)
                    self.armed = False
            return captured

    scene = QGraphicsScene()
    item = FinalReadPoisoningItem()
    scene.addItem(item)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    set_scene_items_selected_for(
        SimpleNamespace(scene=lambda: scene),
        [item],
        True,
        block_signals=True,
    )

    assert QGraphicsItem.isSelected(item) is True
    assert item.armed is False
    assert item.verification_reads == 0
    assert scene.signalsBlocked() is False


def test_external_non_qt_signal_storage_fails_closed_before_mutation() -> None:
    external_state = SimpleNamespace(blocked=False)
    item = _Item()

    class ExternalSignalScene:
        def __init__(self) -> None:
            self.items = [item]
            self.restore_armed = False
            self.post_restore_reads = 0

        def selectedItems(self):
            return [item] if item._selected else []

        def clearSelection(self) -> None:
            item._selected = False

        def blockSignals(self, blocked: bool) -> bool:
            previous = external_state.blocked
            external_state.blocked = blocked
            if not blocked:
                self.restore_armed = True
                self.post_restore_reads = 0
            return previous

        def signalsBlocked(self) -> bool:
            captured = external_state.blocked
            if self.restore_armed:
                self.post_restore_reads += 1
                if self.post_restore_reads == 3:
                    external_state.blocked = not captured
            return captured

    scene = ExternalSignalScene()

    with pytest.raises(RuntimeError, match="selection capture changed authoritative"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
            block_signals=True,
        )

    assert item._selected is False
    assert external_state.blocked is False
    assert scene.post_restore_reads == 0


@pytest.mark.parametrize("layout", ["dict-keys", "nested-values"])
def test_blocked_failure_restores_peers_in_recursive_dict_membership(
    layout: str,
) -> None:
    primary = RuntimeError("target failed after selecting nested peer")
    peer = _Item()

    class FailingItem(_Item):
        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                peer._selected = True
                raise primary

    target = FailingItem()
    scene = _Scene()
    if layout == "dict-keys":
        scene.items = {target: "target metadata", peer: "peer metadata"}
    else:
        nested: list[object] = [target, {"peer": [peer]}]
        nested.append(nested)
        scene.items = {"group": nested}

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
            block_signals=True,
        )

    assert raised.value is primary
    assert target._selected is False
    assert peer._selected is False
    assert scene.signalsBlocked() is False


def test_blocked_selection_rejects_and_restores_nested_membership_removal() -> None:
    peer = _Item()

    class RemovingItem(_Item):
        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                scene.items["group"].remove(peer)

    target = RemovingItem()
    scene = _Scene()
    scene.items = {"group": [target, peer]}
    expected_members = list(scene.items["group"])

    with pytest.raises(RuntimeError, match="changed authoritative membership"):
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
            block_signals=True,
        )

    assert scene.items["group"] == expected_members
    assert target._selected is False
    assert peer._selected is False
    assert scene.signalsBlocked() is False


def test_blocked_selection_failure_restores_nested_membership_removal() -> None:
    primary = RuntimeError("target failed after removing a nested peer")
    peer = _Item()

    class FailingRemovingItem(_Item):
        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                scene.items["group"].remove(peer)
                raise primary

    target = FailingRemovingItem()
    scene = _Scene()
    scene.items = {"group": [target, peer]}
    expected_members = list(scene.items["group"])

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [target],
            True,
            block_signals=True,
        )

    assert raised.value is primary
    assert scene.items["group"] == expected_members
    assert target._selected is False
    assert peer._selected is False
    assert scene.signalsBlocked() is False


def test_selection_helpers_preserve_an_already_blocked_scene() -> None:
    scene = _Scene()
    scene.blocked = True
    canvas = SimpleNamespace(scene=lambda: scene)

    assert clear_scene_selection_for(canvas, block_signals=True)

    assert scene.signalsBlocked() is True
    assert scene.block_signal_calls == [True, True]


def test_selection_signal_block_entry_repairs_one_interruption() -> None:
    class InterruptingScene(_Scene):
        calls = 0

        def blockSignals(self, blocked: bool) -> bool:
            self.calls += 1
            previous = super().blockSignals(blocked)
            if self.calls == 1:
                raise SystemExit("selection signal blocking terminated")
            return previous

    scene = InterruptingScene()
    canvas = SimpleNamespace(scene=lambda: scene)

    with mock.patch.object(scene, "clearSelection") as clear_selection:
        assert clear_scene_selection_for(canvas, block_signals=True)

    assert scene.signalsBlocked() is False
    assert scene.block_signal_calls == [True, True, False]
    clear_selection.assert_called_once_with()


def test_live_scene_getter_failure_aborts_selection_mutation() -> None:
    scene = _Scene()

    class Canvas:
        calls = 0

        def scene(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("selection scene capture failed")
            return scene

    canvas = Canvas()
    item = _Item()

    with pytest.raises(RuntimeError, match="selection scene capture failed"):
        set_scene_items_selected_for(canvas, [item], True)

    assert item.selected_calls == []
    assert scene.block_signal_calls == []


def test_selection_item_interruption_restores_signal_state_and_primary() -> None:
    primary = KeyboardInterrupt("item selection interrupted")

    class InterruptingItem(_Item):
        def setSelected(self, selected: bool) -> None:
            self.selected_calls.append(selected)
            raise primary

    scene = _Scene()
    item = InterruptingItem()

    try:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
        )
    except KeyboardInterrupt as error:
        assert error is primary
    else:
        raise AssertionError("KeyboardInterrupt was not propagated")

    assert scene.signalsBlocked() is False
    assert scene.block_signal_calls == [True, False]


@pytest.mark.parametrize(
    ("failure_mode", "error"),
    [
        ("before", KeyboardInterrupt("selection failed before mutation")),
        ("after", SystemExit("selection failed after mutation")),
    ],
)
def test_actual_qt_multi_selection_bypasses_failing_override_without_refresh(
    failure_mode: str,
    error: BaseException,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class FailingItem(QGraphicsRectItem):
        failures = 1

        def setSelected(self, selected: bool) -> None:
            if selected and self.failures and failure_mode == "before":
                self.failures -= 1
                raise error
            super().setSelected(selected)
            if selected and self.failures and failure_mode == "after":
                self.failures -= 1
                raise error

    scene = QGraphicsScene()
    first = scene.addRect(0.0, 0.0, 10.0, 10.0)
    second = FailingItem(20.0, 0.0, 10.0, 10.0)
    scene.addItem(second)
    for item in (first, second):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    refresh = mock.Mock()
    canvas = SimpleNamespace(
        scene=lambda: scene,
        services=SimpleNamespace(
            selection_controller=SimpleNamespace(
                update_selection_outline=refresh,
            )
        ),
    )

    set_scene_items_selected_for(canvas, [first, second], True)

    assert QGraphicsItem.isSelected(first)
    assert QGraphicsItem.isSelected(second)
    assert second.failures == 1
    assert not scene.signalsBlocked()
    # Base Qt selection never enters the Python failure override or derived UI.
    refresh.assert_not_called()


def test_selection_restore_retries_item_setter_and_preserves_blocked_state() -> None:
    primary = KeyboardInterrupt("selection mutation interrupted")

    class RetryItem(_Item):
        def __init__(self) -> None:
            super().__init__()
            self.restore_failures = 1

        def setSelected(self, selected: bool) -> None:
            self.selected_calls.append(selected)
            if selected:
                self._selected = True
                raise primary
            if self.restore_failures:
                self.restore_failures -= 1
                raise SystemExit("selection restore failed before mutation")
            self._selected = False

    scene = _Scene()
    scene.blocked = True
    item = RetryItem()

    with pytest.raises(KeyboardInterrupt) as raised:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
        )

    assert raised.value is primary
    assert item.isSelected() is False
    assert item.selected_calls == [True, False, False]
    assert scene.signalsBlocked() is True


def test_selection_ports_are_bound_once_across_mutation_and_rollback() -> None:
    primary = SystemExit("bound selection setter terminated")

    class DescriptorItem:
        def __init__(self) -> None:
            self._selected = False
            self.setter_reads = 0
            self.getter_reads = 0
            self.failures = 1

        @property
        def setSelected(self):
            self.setter_reads += 1

            def set_selected(selected: bool) -> None:
                self._selected = selected
                if selected and self.failures:
                    self.failures -= 1
                    raise primary

            return set_selected

        @property
        def isSelected(self):
            self.getter_reads += 1
            return lambda: self._selected

    scene = _Scene()
    item = DescriptorItem()

    with pytest.raises(SystemExit) as raised:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
        )

    assert raised.value is primary
    assert item._selected is False
    assert item.setter_reads == 1
    assert item.getter_reads == 1
    assert not scene.signalsBlocked()


def test_selection_capture_failure_restores_preflight_target_state() -> None:
    primary = SystemExit("second selection capture terminated")

    class Item(_Item):
        pass

    first = Item()
    first_state = first.__dict__.copy()

    class FailingItem(Item):
        def isSelected(self) -> bool:
            first._selected = True
            first.selected_calls.append("poisoned")
            raise primary

    second = FailingItem()

    with pytest.raises(SystemExit) as caught:
        set_scene_items_selected_for(
            SimpleNamespace(),
            [first, second],
            True,
        )

    assert caught.value is primary
    assert first.__dict__ == first_state
    assert first.isSelected() is False


def test_unblocked_partial_selection_restores_frontier_and_refreshes_once() -> None:
    primary = RuntimeError("second selection failed after mutation")

    class LiveScene(_Scene):
        def __init__(self, items) -> None:
            super().__init__(items)
            self.items = list(items)

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            for item in self.items:
                item._selected = False

    class FailingItem(_Item):
        failures = 1

        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected and self.failures:
                self.failures -= 1
                raise primary

    previously_selected = _Item()
    previously_selected._selected = True
    first = _Item()
    second = FailingItem()
    scene = LiveScene([previously_selected, first, second])
    status_callback = mock.Mock()
    selection_info = SimpleNamespace(
        callback=status_callback,
        signature=(frozenset({7}), frozenset({9})),
        pending_signature=(frozenset({8}), frozenset()),
        cache=("C2H6", "30.07"),
        rdkit_warmup_pending=True,
        last_interaction_time=17.5,
    )
    selected_note = object()
    other_note = object()
    selected_notes = [selected_note]
    scene_items_state = SimpleNamespace(
        selected_notes=selected_notes,
        note_items=[selected_note, other_note],
    )

    def mutate_derived_state() -> None:
        selection_info.signature = None
        selection_info.pending_signature = None
        selection_info.cache = ("partial", "partial")
        selection_info.rdkit_warmup_pending = False
        selection_info.last_interaction_time = 99.0
        scene_items_state.selected_notes = [other_note]

    refresh = mock.Mock(side_effect=mutate_derived_state)
    update_note_selection_box = mock.Mock()
    canvas = SimpleNamespace(
        scene=lambda: scene,
        selection_info_state=selection_info,
        scene_items_state=scene_items_state,
        services=SimpleNamespace(
            selection_controller=SimpleNamespace(
                update_selection_outline=refresh,
                update_note_selection_box=update_note_selection_box,
            )
        ),
    )

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(
            canvas,
            [first, second],
            True,
            block_signals=False,
        )

    assert raised.value is primary
    assert previously_selected.isSelected()
    assert not first.isSelected()
    assert not second.isSelected()
    assert scene.selectedItems() == [previously_selected]
    assert not scene.signalsBlocked()
    refresh.assert_called_once_with()
    assert selection_info.signature == (frozenset({7}), frozenset({9}))
    assert selection_info.pending_signature == (frozenset({8}), frozenset())
    assert selection_info.cache == ("C2H6", "30.07")
    assert selection_info.rdkit_warmup_pending is True
    assert selection_info.last_interaction_time == 17.5
    status_callback.assert_called_once_with("C2H6", "30.07")
    assert scene_items_state.selected_notes is selected_notes
    assert selected_notes == [selected_note]
    assert update_note_selection_box.call_args_list == [
        mock.call(selected_note),
        mock.call(other_note),
    ]


def test_unblocked_clear_failure_restores_public_only_item_state() -> None:
    primary = RuntimeError("clear failed before updating the scene registry")

    class Item:
        def __init__(self) -> None:
            self.flag = True

        def isSelected(self) -> bool:
            return self.flag

        def setSelected(self, selected: bool) -> None:
            self.flag = selected

    item = Item()

    class Scene:
        def __init__(self) -> None:
            self.items = [item]
            self.selected_registry = [item]

        def selectedItems(self):
            return list(self.selected_registry)

        def clearSelection(self) -> None:
            item.flag = False
            raise primary

    scene = Scene()

    with pytest.raises(RuntimeError) as raised:
        clear_scene_selection_for(
            SimpleNamespace(scene=lambda: scene),
            block_signals=False,
        )

    assert raised.value is primary
    assert item.flag is True
    assert scene.selectedItems() == [item]


def test_unblocked_set_failure_restores_public_only_item_state() -> None:
    primary = RuntimeError("setter failed before updating the scene registry")

    class Item:
        def __init__(self) -> None:
            self.flag = False

        def isSelected(self) -> bool:
            return self.flag

        def setSelected(self, selected: bool) -> None:
            self.flag = selected
            if selected:
                raise primary

    item = Item()

    class Scene:
        def __init__(self) -> None:
            self.items = [item]
            self.selected_registry = []

        def selectedItems(self):
            return list(self.selected_registry)

        def clearSelection(self) -> None:
            self.selected_registry.clear()

    scene = Scene()

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(
            SimpleNamespace(scene=lambda: scene),
            [item],
            True,
            block_signals=False,
        )

    assert raised.value is primary
    assert item.flag is False
    assert scene.selectedItems() == []


def test_selection_restore_writes_captured_false_after_true_callback() -> None:
    primary = RuntimeError("second target failed after selection")

    class LiveScene(_Scene):
        def __init__(self, items) -> None:
            super().__init__(items)
            self.items = list(items)

        def selectedItems(self):
            return [item for item in self.items if item.isSelected()]

        def clearSelection(self) -> None:
            self.clear_selection_calls += 1
            for item in self.items:
                item._selected = False

    target = _Item()

    class PreviouslySelected(_Item):
        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected:
                target._selected = True

    class FailingTarget(_Item):
        failures = 1

        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected and self.failures:
                self.failures -= 1
                raise primary

    previous = PreviouslySelected()
    previous._selected = True
    failing = FailingTarget()
    scene = LiveScene([previous, target, failing])
    canvas = SimpleNamespace(
        scene=lambda: scene,
        services=SimpleNamespace(selection_controller=None),
    )

    with pytest.raises(RuntimeError) as caught:
        set_scene_items_selected_for(
            canvas,
            [target, failing],
            True,
            block_signals=False,
        )

    assert caught.value is primary
    assert previous.isSelected()
    assert not target.isSelected()
    assert not failing.isSelected()
    assert scene.selectedItems() == [previous]


def test_fail_before_selection_still_restores_derived_logical_state() -> None:
    primary = RuntimeError("selection failed after poisoning derived state")
    selection_info = SimpleNamespace(
        callback=None,
        signature="captured",
        pending_signature=None,
        cache=("C", "12.01"),
        rdkit_warmup_pending=False,
        last_interaction_time=4.0,
    )
    selected_note = object()
    selected_notes = [selected_note]
    scene_items_state = SimpleNamespace(
        selected_notes=selected_notes,
        note_items=[selected_note],
    )

    class PoisoningItem(_Item):
        def setSelected(self, selected: bool) -> None:
            assert selected
            selection_info.signature = "poisoned"
            scene_items_state.selected_notes = []
            raise primary

    item = PoisoningItem()

    class LiveScene(_Scene):
        def selectedItems(self):
            return [item] if item.isSelected() else []

    scene = LiveScene()
    canvas = SimpleNamespace(
        scene=lambda: scene,
        selection_info_state=selection_info,
        scene_items_state=scene_items_state,
        services=SimpleNamespace(selection_controller=None),
    )

    with pytest.raises(RuntimeError) as raised:
        set_scene_items_selected_for(
            canvas,
            [item],
            True,
            block_signals=False,
        )

    assert raised.value is primary
    assert item.isSelected() is False
    assert selection_info.signature == "captured"
    assert scene_items_state.selected_notes is selected_notes
    assert selected_notes == [selected_note]


def test_strict_selection_scene_property_attribute_error_precedes_mutation() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = scene.addRect(0.0, 0.0, 10.0, 10.0)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    item.setSelected(True)

    class FlakyCanvas:
        calls = 0

        @property
        def scene(self):
            self.calls += 1
            if self.calls == 1:
                raise AttributeError("selection scene property failed internally")
            return lambda: scene

    canvas = FlakyCanvas()
    with pytest.raises(
        AttributeError,
        match="selection scene property failed internally",
    ):
        clear_scene_selection_for(canvas, block_signals=True)

    assert item.isSelected()
    assert clear_scene_selection_for(canvas, block_signals=True)
    assert not item.isSelected()


def test_actual_qt_override_bypass_needs_no_status_recovery_publication() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    previously_selected = scene.addRect(0.0, 0.0, 10.0, 10.0)
    first = scene.addRect(20.0, 0.0, 10.0, 10.0)

    primary = SystemExit("selection setter terminated after mutation")

    class FailingRect(QGraphicsRectItem):
        failures = 1

        def setSelected(self, selected: bool) -> None:
            super().setSelected(selected)
            if selected and self.failures:
                self.failures -= 1
                raise primary

    second = FailingRect(40.0, 0.0, 10.0, 10.0)
    scene.addItem(second)
    for item in (previously_selected, first, second):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    previously_selected.setSelected(True)

    selected_note = object()
    selected_notes = [selected_note]
    scene_items_state = SimpleNamespace(
        selected_notes=selected_notes,
        note_items=[],
    )
    published: list[tuple[str, str]] = []
    selection_info = SimpleNamespace(
        callback=None,
        signature=(frozenset({7}), frozenset()),
        pending_signature=None,
        cache=("captured", "status"),
        rdkit_warmup_pending=True,
        last_interaction_time=12.5,
    )

    def corrupt_after_publication(formula: str, mass: str) -> None:
        published.append((formula, mass))
        first.setSelected(True)
        selection_info.cache = ("corrupt", "corrupt")
        selection_info.callback = None
        selected_notes.clear()

    selection_info.callback = corrupt_after_publication
    canvas = SimpleNamespace(
        scene=lambda: scene,
        selection_info_state=selection_info,
        scene_items_state=scene_items_state,
        services=SimpleNamespace(
            selection_controller=SimpleNamespace(
                update_selection_outline=None,
                update_note_selection_box=None,
            )
        ),
    )

    set_scene_items_selected_for(
        canvas,
        [first, second],
        True,
        block_signals=False,
    )

    assert second.failures == 1
    assert published == []
    assert {id(item) for item in scene.selectedItems()} == {
        id(previously_selected),
        id(first),
        id(second),
    }
    assert selection_info.cache == ("captured", "status")
    assert selection_info.callback is corrupt_after_publication
    assert scene_items_state.selected_notes is selected_notes
    assert selected_notes == [selected_note]
    assert not scene.signalsBlocked()
