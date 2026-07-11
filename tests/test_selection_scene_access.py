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


def test_set_scene_items_selected_for_handles_missing_scene() -> None:
    item = _Item()

    set_scene_items_selected_for(SimpleNamespace(), [item], False)

    assert item.selected_calls == [False]


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
def test_actual_qt_multi_selection_failure_restores_every_item_without_refresh(
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

    with pytest.raises(type(error)) as raised:
        set_scene_items_selected_for(canvas, [first, second], True)

    assert raised.value is error
    assert not first.isSelected()
    assert not second.isSelected()
    assert not scene.signalsBlocked()
    # The scene signal was blocked throughout, so the pre-operation derived
    # UI is already authoritative and must not be redundantly re-entered.
    refresh.assert_not_called()

    set_scene_items_selected_for(canvas, [first, second], True)
    assert first.isSelected()
    assert second.isSelected()


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


def test_actual_qt_status_publication_mutation_is_silently_reasserted_once() -> None:
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

    with pytest.raises(SystemExit) as raised:
        set_scene_items_selected_for(
            canvas,
            [first, second],
            True,
            block_signals=False,
        )

    assert raised.value is primary
    assert published == [("captured", "status")]
    assert scene.selectedItems() == [previously_selected]
    assert selection_info.cache == ("captured", "status")
    assert selection_info.callback is corrupt_after_publication
    assert scene_items_state.selected_notes is selected_notes
    assert selected_notes == [selected_note]
    assert not scene.signalsBlocked()
