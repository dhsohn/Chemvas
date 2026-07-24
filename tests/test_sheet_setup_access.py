import os
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.ui.sheet_setup_access import (
    _SheetSetupStateSnapshot,
    scene_pos_in_sheet_for,
    set_sheet_setup_for,
    sheet_orientation_for,
    sheet_rect_for,
    sheet_setup_for,
    sheet_size_for,
)
from chemvas.ui.sheet_setup_state import SheetSetupState, sheet_setup_state_for
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
    view_scene_rect_is_explicit,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

_APP = QApplication.instance() or QApplication([])
_APP.setQuitOnLastWindowClosed(False)


class _Viewport:
    def __init__(self) -> None:
        self.update = mock.Mock()


def _qt_sheet_canvas() -> tuple[QGraphicsView, QGraphicsScene]:
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = QGraphicsView(scene)
    set_sheet_setup_for(canvas, "A4", "landscape")
    return canvas, scene


def _tracker_signature(scene: QGraphicsScene):
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    if tracker is None:
        return None
    return (
        tracker,
        QRectF(tracker.known_rect),
        QRectF(tracker.baseline_rect),
        QRectF(tracker.pending_rect),
        tracker.pending_expansions,
        tuple((key, QRectF(rect)) for key, rect in tracker.pending_expansions.items()),
        tracker.pending_journal,
        tuple(
            (
                key,
                existed,
                QRectF(previous) if previous is not None else None,
            )
            for key, existed, previous in tracker.pending_journal
        ),
        tracker.depth,
        tracker.internal_change,
    )


def _sheet_configuration(canvas: QGraphicsView, scene: QGraphicsScene):
    state = sheet_setup_state_for(canvas)
    return (
        state,
        state.size_name,
        state.orientation,
        state.rect,
        QRectF(state.rect),
        canvas.sheet_size,
        canvas.sheet_orientation,
        QRectF(canvas.sceneRect()),
        view_scene_rect_is_explicit(canvas),
        QRectF(scene.sceneRect()),
        scene_rect_is_automatic(scene),
        _tracker_signature(scene),
    )


def _assert_sheet_configuration(
    canvas: QGraphicsView,
    scene: QGraphicsScene,
    expected,
) -> None:
    actual = _sheet_configuration(canvas, scene)
    assert actual[0] is expected[0]
    assert actual[1:3] == expected[1:3]
    assert actual[3] is expected[3]
    assert actual[4:11] == expected[4:11]
    actual_tracker = actual[11]
    expected_tracker = expected[11]
    if expected_tracker is None:
        assert actual_tracker is None
        return
    assert actual_tracker is not None
    assert actual_tracker[0] is expected_tracker[0]
    assert actual_tracker[1:4] == expected_tracker[1:4]
    assert actual_tracker[4] is expected_tracker[4]
    assert actual_tracker[5] == expected_tracker[5]
    assert actual_tracker[6] is expected_tracker[6]
    assert actual_tracker[7:] == expected_tracker[7:]


def test_sheet_setup_accessors_return_current_sheet_values() -> None:
    canvas = SimpleNamespace(sheet_size="A4", sheet_orientation="landscape")

    assert sheet_setup_for(canvas) == ("A4", "landscape")
    assert sheet_size_for(canvas) == "A4"
    assert sheet_orientation_for(canvas) == "landscape"


def test_set_sheet_setup_updates_scene_rect_and_viewport() -> None:
    viewport = _Viewport()
    canvas = SimpleNamespace(
        sheet_size="A4",
        sheet_orientation="landscape",
        setSceneRect=mock.Mock(),
        viewport=lambda: viewport,
    )

    set_sheet_setup_for(canvas, "A4", "portrait")

    assert sheet_setup_for(canvas) == ("A4", "portrait")
    assert sheet_rect_for(canvas) == QRectF(-297.5, -421.0, 595.0, 842.0)
    canvas.setSceneRect.assert_called_once_with(QRectF(-377.5, -501.0, 755.0, 1002.0))
    viewport.update.assert_called_once_with()


def test_scene_pos_in_sheet_uses_configured_sheet_rect_and_allows_uninitialized_rect() -> (
    None
):
    canvas = SimpleNamespace(sheet_size="A4", sheet_orientation="landscape")

    assert scene_pos_in_sheet_for(canvas, QPointF(999.0, 999.0))

    configured = SimpleNamespace(
        sheet_size="A4",
        sheet_orientation="landscape",
        setSceneRect=mock.Mock(),
        viewport=lambda: _Viewport(),
    )
    set_sheet_setup_for(configured, "A4", "landscape")

    assert scene_pos_in_sheet_for(configured, QPointF(0.0, 0.0))
    assert not scene_pos_in_sheet_for(configured, QPointF(999.0, 999.0))


@pytest.mark.parametrize(
    "error",
    [
        KeyboardInterrupt("sheet viewport update interrupted"),
        SystemExit("sheet viewport update terminated"),
    ],
)
def test_sheet_setup_finalization_failure_restores_explicit_state_and_tracker(
    error: BaseException,
) -> None:
    canvas, scene = _qt_sheet_canvas()
    tracker_snapshot = SceneRectSnapshot.capture(scene)
    assert tracker_snapshot is not None
    tracker_snapshot.release()
    tracker = tracker_snapshot.tracker
    expansion_key = id(object())
    pending_expansions = tracker.pending_expansions
    pending_journal = tracker.pending_journal
    pending_expansions[expansion_key] = QRectF(1.0, 2.0, 3.0, 4.0)
    pending_journal.append((expansion_key, False, None))
    tracker.pending_rect = QRectF(-20.0, -30.0, 40.0, 60.0)
    before = _sheet_configuration(canvas, scene)
    failing_viewport = SimpleNamespace(update=mock.Mock(side_effect=error))

    with mock.patch.object(canvas, "viewport", return_value=failing_viewport):
        with pytest.raises(type(error), match=str(error)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is error
    _assert_sheet_configuration(canvas, scene, before)
    assert tracker.pending_expansions is pending_expansions
    assert tracker.pending_journal is pending_journal
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect() == before[9]
    assert canvas.sceneRect() == before[7]
    scene.removeItem(far)
    canvas.close()


def test_sheet_setup_rollback_closes_on_rect_after_state_setter_recontaminates_it() -> (
    None
):
    canvas, scene = _qt_sheet_canvas()
    original_state = sheet_setup_state_for(canvas)
    before_scene_rect = QRectF(scene.sceneRect())
    before_view_rect = QRectF(canvas.sceneRect())
    poisoned_rect = QRectF(9000.0, 9001.0, 90.0, 91.0)

    class RectPoisoningSheetState:
        def __init__(self) -> None:
            self.size_name = original_state.size_name
            self._orientation = original_state.orientation
            self.rect = original_state.rect
            self.poison_restore = False

        @property
        def orientation(self):
            return self._orientation

        @orientation.setter
        def orientation(self, value) -> None:
            self._orientation = value
            if self.poison_restore and value == "landscape":
                scene.setSceneRect(poisoned_rect)

    state = RectPoisoningSheetState()
    canvas.sheet_setup_state = state
    state.poison_restore = True
    primary = RuntimeError("sheet viewport update failed")
    failing_viewport = SimpleNamespace(update=mock.Mock(side_effect=primary))

    with mock.patch.object(canvas, "viewport", return_value=failing_viewport):
        with pytest.raises(RuntimeError, match=str(primary)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is primary
    assert state.size_name == "A4"
    assert state.orientation == "landscape"
    assert state.rect is original_state.rect
    assert scene.sceneRect() == before_scene_rect
    assert canvas.sceneRect() == before_view_rect
    assert scene.sceneRect() != poisoned_rect
    canvas.close()


@pytest.mark.parametrize("owner", ["scene", "view"])
@pytest.mark.parametrize("mutate_before_raise", [False, True])
@pytest.mark.parametrize(
    "error_type",
    [KeyboardInterrupt, SystemExit],
)
def test_sheet_setup_owner_setter_failure_restores_exact_explicit_configuration(
    owner: str,
    mutate_before_raise: bool,
    error_type: type[BaseException],
) -> None:
    canvas, scene = _qt_sheet_canvas()
    before = _sheet_configuration(canvas, scene)
    target = scene if owner == "scene" else canvas
    original_set_scene_rect = target.setSceneRect
    error = error_type(f"{owner} rect setter failed")
    failed = False

    def fail_once(rect) -> None:
        nonlocal failed
        if not failed:
            failed = True
            if mutate_before_raise:
                original_set_scene_rect(rect)
            raise error
        original_set_scene_rect(rect)

    with mock.patch.object(target, "setSceneRect", side_effect=fail_once):
        with pytest.raises(error_type, match=str(error)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is error
    _assert_sheet_configuration(canvas, scene, before)
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect() == before[9]
    assert canvas.sceneRect() == before[7]
    scene.removeItem(far)
    canvas.close()


@pytest.mark.parametrize("failure_call", [1, 2])
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_sheet_setup_live_scene_getter_failure_after_state_mutation_rolls_back(
    failure_call: int,
    error_type: type[BaseException],
) -> None:
    canvas, scene = _qt_sheet_canvas()
    before = _sheet_configuration(canvas, scene)
    original_scene = canvas.scene
    calls = 0
    error = error_type("live scene getter failed")

    def fail_second_scene_read():
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise error
        return original_scene()

    with mock.patch.object(canvas, "scene", side_effect=fail_second_scene_read):
        with pytest.raises(error_type, match=str(error)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is error
    _assert_sheet_configuration(canvas, scene, before)
    canvas.close()


@pytest.mark.parametrize("owner", ["scene", "view"])
@pytest.mark.parametrize("failure_call", [1, 2])
def test_sheet_setup_live_rect_getter_failure_preserves_prestate(
    owner: str,
    failure_call: int,
) -> None:
    canvas, scene = _qt_sheet_canvas()
    before = _sheet_configuration(canvas, scene)
    target = scene if owner == "scene" else canvas
    original_scene_rect = target.sceneRect
    calls = 0
    error = SystemExit(f"{owner} rect getter terminated")

    def fail_selected_read():
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise error
        return original_scene_rect()

    with mock.patch.object(target, "sceneRect", side_effect=fail_selected_read):
        with pytest.raises(SystemExit, match=str(error)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is error
    _assert_sheet_configuration(canvas, scene, before)
    canvas.close()


@pytest.mark.parametrize("failure_field", ["orientation", "rect"])
@pytest.mark.parametrize("mutate_before_raise", [False, True])
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_sheet_setup_state_failure_restores_size_orientation_and_rect_identity(
    failure_field: str,
    mutate_before_raise: bool,
    error_type: type[BaseException],
) -> None:
    canvas, scene = _qt_sheet_canvas()
    original_state = sheet_setup_state_for(canvas)

    class FailingSheetState:
        def __init__(self) -> None:
            self.size_name = original_state.size_name
            self._orientation = original_state.orientation
            self._rect = original_state.rect
            self.failure_armed = True
            self.error = error_type(f"sheet {failure_field} setter failed")

        @property
        def orientation(self):
            return self._orientation

        @orientation.setter
        def orientation(self, value) -> None:
            if self.failure_armed and failure_field == "orientation":
                self.failure_armed = False
                if mutate_before_raise:
                    self._orientation = value
                raise self.error
            self._orientation = value

        @property
        def rect(self):
            return self._rect

        @rect.setter
        def rect(self, value) -> None:
            if self.failure_armed and failure_field == "rect":
                self.failure_armed = False
                if mutate_before_raise:
                    self._rect = value
                raise self.error
            self._rect = value

    state = FailingSheetState()
    canvas.sheet_setup_state = state
    before = _sheet_configuration(canvas, scene)

    with pytest.raises(error_type, match=str(state.error)) as raised:
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is state.error
    _assert_sheet_configuration(canvas, scene, before)
    canvas.close()


def test_sheet_state_snapshot_rejects_persistent_no_op_setters_and_stays_active() -> (
    None
):
    original_rect = QRectF(-10.0, -20.0, 30.0, 40.0)

    class NoOpRestoreState:
        def __init__(self) -> None:
            self._size_name = "Letter"
            self._orientation = "landscape"
            self._rect = original_rect
            self.no_op_restore = False

        @property
        def size_name(self):
            return self._size_name

        @size_name.setter
        def size_name(self, value) -> None:
            if self.no_op_restore and value == "Letter":
                return
            self._size_name = value

        @property
        def orientation(self):
            return self._orientation

        @orientation.setter
        def orientation(self, value) -> None:
            if self.no_op_restore and value == "landscape":
                return
            self._orientation = value

        @property
        def rect(self):
            return self._rect

        @rect.setter
        def rect(self, value) -> None:
            if self.no_op_restore and value is original_rect:
                return
            self._rect = value

    state = NoOpRestoreState()
    canvas = SimpleNamespace(
        sheet_setup_state=state,
        sheet_size="Letter",
        sheet_orientation="landscape",
    )
    snapshot = _SheetSetupStateSnapshot.capture(canvas)
    replacement_rect = QRectF(-100.0, -200.0, 300.0, 400.0)
    state.size_name = "A4"
    state.orientation = "portrait"
    state.rect = replacement_rect
    canvas.sheet_size = "A4"
    canvas.sheet_orientation = "portrait"
    state.no_op_restore = True

    with pytest.raises(BaseExceptionGroup, match="two verified passes"):
        snapshot.restore()

    assert snapshot.active is True
    assert state.size_name == "A4"
    assert state.orientation == "portrait"
    assert state.rect is replacement_rect

    state.no_op_restore = False
    snapshot.restore()

    assert snapshot.active is False
    assert state.size_name == "Letter"
    assert state.orientation == "landscape"
    assert state.rect is original_rect
    assert state.rect == QRectF(-10.0, -20.0, 30.0, 40.0)
    assert canvas.sheet_size == "Letter"
    assert canvas.sheet_orientation == "landscape"


def test_failed_first_sheet_setup_restores_absent_state_and_inherited_qt_modes() -> (
    None
):
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = QGraphicsView(scene)
    assert not hasattr(canvas, "sheet_setup_state")
    assert not hasattr(canvas, "sheet_size")
    assert not hasattr(canvas, "sheet_orientation")
    assert not hasattr(scene, "_chemvas_scene_rect_automatic")
    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    assert not hasattr(canvas, "_chemvas_view_scene_rect_explicit")
    error = KeyboardInterrupt("first sheet setup interrupted")
    failing_viewport = SimpleNamespace(update=mock.Mock(side_effect=error))

    with mock.patch.object(canvas, "viewport", return_value=failing_viewport):
        with pytest.raises(KeyboardInterrupt, match=str(error)) as raised:
            set_sheet_setup_for(canvas, "A4", "portrait")

    assert raised.value is error
    assert not hasattr(canvas, "sheet_setup_state")
    assert not hasattr(canvas, "sheet_size")
    assert not hasattr(canvas, "sheet_orientation")
    assert not hasattr(scene, "_chemvas_scene_rect_automatic")
    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    assert not hasattr(canvas, "_chemvas_view_scene_rect_explicit")
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    assert canvas.sceneRect().right() > 10_000.0
    scene.removeItem(far)
    canvas.close()


def test_failed_sheet_setup_restores_active_nested_rect_guard_and_journal() -> None:
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = QGraphicsView(scene)
    outer = SceneRectSnapshot.capture(scene)
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and inner is not None
    expansion_key = object()
    inner.release(
        QRectF(10_000.0, 0.0, 10.0, 10.0),
        expansion_key=expansion_key,
    )
    tracker = outer.tracker
    before_tracker = _tracker_signature(scene)
    guarded_rect = QRectF(scene.sceneRect())
    error = KeyboardInterrupt("nested sheet setup interrupted")
    failing_viewport = SimpleNamespace(update=mock.Mock(side_effect=error))

    with mock.patch.object(canvas, "viewport", return_value=failing_viewport):
        with pytest.raises(KeyboardInterrupt, match=str(error)):
            set_sheet_setup_for(canvas, "A4", "portrait")

    after_tracker = _tracker_signature(scene)
    assert after_tracker is not None and before_tracker is not None
    assert after_tracker[0] is before_tracker[0]
    assert after_tracker[1:4] == before_tracker[1:4]
    assert after_tracker[4] is before_tracker[4]
    assert after_tracker[5] == before_tracker[5]
    assert after_tracker[6] is before_tracker[6]
    assert after_tracker[7:] == before_tracker[7:]
    assert tracker.depth == 1
    assert scene_rect_is_automatic(scene)
    assert scene.sceneRect() == guarded_rect
    assert view_scene_rect_is_explicit(canvas) is False
    guarded_far = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect() == guarded_rect
    scene.removeItem(guarded_far)

    outer.restore()
    future = scene.addRect(30_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 30_000.0
    assert canvas.sceneRect().right() > 30_000.0
    scene.removeItem(future)
    canvas.close()


def test_second_sheet_snapshot_capture_failure_unwinds_first_rect_snapshot() -> None:
    primary = SystemExit("sheet compatibility capture poisoned the rect")

    class PoisoningSheetView(QGraphicsView):
        armed = False

        @property
        def sheet_size(self):
            if self.armed:
                self.scene().setSceneRect(QRectF(5000.0, 6000.0, 70.0, 80.0))
                raise primary
            return "Letter"

    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = PoisoningSheetView(scene)
    before = QRectF(scene.sceneRect())
    canvas.armed = True

    with pytest.raises(SystemExit) as caught:
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert caught.value is primary
    assert scene.sceneRect() == before
    canvas.close()


def test_sheet_state_capture_failure_restores_mutated_raw_rect_contents() -> None:
    primary = KeyboardInterrupt("sheet orientation capture terminated")

    class PoisoningSheetState:
        def __init__(self) -> None:
            self._size_name = "Letter"
            self._orientation = "landscape"
            self.rect = QRectF(1.0, 2.0, 3.0, 4.0)
            self.armed = False

        @property
        def size_name(self):
            if self.armed:
                self.rect.setRect(90.0, 91.0, 92.0, 93.0)
                self._orientation = "portrait"
            return self._size_name

        @size_name.setter
        def size_name(self, value) -> None:
            self._size_name = value

        @property
        def orientation(self):
            if self.armed:
                raise primary
            return self._orientation

        @orientation.setter
        def orientation(self, value) -> None:
            self._orientation = value

    scene = QGraphicsScene()
    canvas = QGraphicsView(scene)
    state = PoisoningSheetState()
    canvas.sheet_setup_state = state
    before_rect = QRectF(state.rect)
    state.armed = True

    with pytest.raises(KeyboardInterrupt) as caught:
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert caught.value is primary
    assert state.rect == before_rect
    assert state._orientation == "landscape"
    canvas.close()


def test_sheet_state_root_capture_failure_restores_raw_backing_state() -> None:
    primary = SystemExit("sheet root capture terminated after poisoning backing state")

    class PoisoningRootView(QGraphicsView):
        def __init__(self, scene: QGraphicsScene) -> None:
            super().__init__(scene)
            self._state = SimpleNamespace(
                size_name="Letter",
                orientation="landscape",
                rect=QRectF(1.0, 2.0, 3.0, 4.0),
            )
            self.armed = False

        @property
        def sheet_setup_state(self):
            if self.armed:
                self._state.orientation = "portrait"
                self._state.rect.setRect(90.0, 91.0, 92.0, 93.0)
                raise primary
            return self._state

        @sheet_setup_state.setter
        def sheet_setup_state(self, value) -> None:
            self._state = value

    scene = QGraphicsScene()
    canvas = PoisoningRootView(scene)
    canvas.sheet_size = "Letter"
    canvas.sheet_orientation = "landscape"
    original_state = canvas._state
    original_rect = QRectF(original_state.rect)
    canvas.armed = True

    with pytest.raises(SystemExit) as caught:
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert caught.value is primary
    assert canvas._state is original_state
    assert original_state.orientation == "landscape"
    assert original_state.rect == original_rect
    canvas.close()


def test_sheet_success_callback_poison_is_rejected_and_restores_prestate() -> None:
    canvas, scene = _qt_sheet_canvas()
    before = _sheet_configuration(canvas, scene)
    state = sheet_setup_state_for(canvas)

    def poison_after_update() -> None:
        state.orientation = "landscape"
        state.rect.setRect(90.0, 91.0, 92.0, 93.0)

    viewport = SimpleNamespace(update=poison_after_update)
    with mock.patch.object(canvas, "viewport", return_value=viewport):
        with pytest.raises(
            RuntimeError,
            match="changed during successful finalization",
        ):
            set_sheet_setup_for(canvas, "A4", "portrait")

    _assert_sheet_configuration(canvas, scene, before)
    canvas.close()


def test_sheet_success_final_compatibility_getter_cannot_poison_scene_rect() -> None:
    poisoned_rect = QRectF(9000.0, 9001.0, 90.0, 91.0)

    class FinalGetterPoisoningView(QGraphicsView):
        def __init__(self, scene: QGraphicsScene) -> None:
            super().__init__(scene)
            self._sheet_orientation = "landscape"
            self.orientation_reads = 0
            self.poison_on_read = 0

        @property
        def sheet_orientation(self) -> str:
            self.orientation_reads += 1
            if self.poison_on_read == self.orientation_reads:
                self.scene().setSceneRect(poisoned_rect)
            return self._sheet_orientation

        @sheet_orientation.setter
        def sheet_orientation(self, value: str) -> None:
            self._sheet_orientation = value

    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = FinalGetterPoisoningView(scene)
    canvas.sheet_size = "A4"
    set_sheet_setup_for(canvas, "A4", "landscape")
    before = _sheet_configuration(canvas, scene)
    canvas.orientation_reads = 0
    # One read captures the compatibility baseline; the next is the last live
    # compatibility read during successful-result verification.
    canvas.poison_on_read = 2

    with pytest.raises(
        RuntimeError,
        match="scene rect changed during successful finalization",
    ):
        set_sheet_setup_for(canvas, "A4", "portrait")

    _assert_sheet_configuration(canvas, scene, before)
    assert scene.sceneRect() != poisoned_rect
    canvas.close()


def test_sheet_success_final_scene_getter_cannot_delete_canonical_state_root() -> None:
    class RootDeletingView(QGraphicsView):
        def __init__(self, scene: QGraphicsScene) -> None:
            super().__init__(scene)
            self.runtime_state = SimpleNamespace(sheet_setup_state=SheetSetupState())
            self.scene_reads = 0
            self.delete_on_read = 0

        def scene(self):
            self.scene_reads += 1
            if self.scene_reads == self.delete_on_read:
                del self.runtime_state.sheet_setup_state
            return QGraphicsView.scene(self)

    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = RootDeletingView(scene)
    set_sheet_setup_for(canvas, "A4", "landscape")
    before = _sheet_configuration(canvas, scene)
    canvas.scene_reads = 0
    # Initial transaction capture, forward rect capture, then the final
    # successful-result capture. Delete the canonical root in that last getter.
    canvas.delete_on_read = 3

    with pytest.raises(
        RuntimeError,
        match="state root disappeared during finalization",
    ):
        set_sheet_setup_for(canvas, "A4", "portrait")

    assert canvas.runtime_state.sheet_setup_state is before[0]
    _assert_sheet_configuration(canvas, scene, before)
    canvas.close()
