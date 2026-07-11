import os
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)
from ui.history_commands import (
    _capture_scene_rect_snapshot,
    _release_scene_rect_snapshot,
)
from ui.input_view_access import CanvasSceneRectStateSnapshot, set_scene_rect_for
from ui.scene_item_attach_snapshot import (
    SceneItemAttachPorts,
    SceneItemAttachSnapshot,
)
from ui.scene_rect_snapshot import (
    SceneRectSnapshot,
    SceneRectStateSnapshot,
    ViewSceneRectStateSnapshot,
    _add_secondary_note,
    scene_rect_is_automatic,
    set_explicit_scene_rect,
    set_explicit_view_scene_rect,
    set_inherited_view_scene_rect,
    view_scene_rect_is_explicit,
)
from ui.scene_signal_blocking import _add_signal_recovery_note


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, rect) -> None:
        for callback in self.callbacks:
            callback(rect)

    def disconnect(self, callback) -> None:
        self.callbacks.remove(callback)


class _FailOnceDescriptor:
    def __init__(self, name: str, value_factory) -> None:
        self.name = name
        self.value_factory = value_factory
        self.calls = 0

    def __get__(self, instance, owner):
        if instance is None:
            return self
        self.calls += 1
        if self.calls == 1:
            raise AttributeError(f"live {self.name} descriptor failed internally")
        return self.value_factory(instance)


class _FailingScene:
    def __init__(self) -> None:
        self.rect = QRectF(-0.5, -0.5, 11.0, 11.0)
        self.inherited_rect = QRectF(self.rect)
        self.sceneRectChanged = _Signal()
        self.failures: list[tuple[bool, BaseException]] = []

    def sceneRect(self) -> QRectF:
        return QRectF(self.rect)

    def setSceneRect(self, rect: QRectF) -> None:
        tracker = getattr(self, "_chemvas_scene_rect_tracker", None)

        def apply() -> None:
            if rect.isNull():
                fallback = tracker.baseline_rect if tracker is not None else self.rect
                self.rect = QRectF(getattr(self, "inherited_rect", fallback))
            else:
                self.rect = QRectF(rect)
                if tracker is None:
                    self.inherited_rect = QRectF(rect)

        if self.failures:
            mutate, error = self.failures.pop(0)
            if mutate:
                apply()
                self.sceneRectChanged.emit(QRectF(rect))
            raise error
        # Match QGraphicsScene's inherited-mode behavior: a null setter value
        # clears the explicit override while sceneRect() still reports the
        # items-derived live rectangle.
        apply()
        self.sceneRectChanged.emit(QRectF(rect))


@pytest.mark.parametrize(
    "report",
    [
        lambda primary, secondary: _add_secondary_note(primary, secondary),
        lambda primary, secondary: _add_signal_recovery_note(
            primary,
            secondary,
            phase="testing diagnostic lookup",
        ),
    ],
)
@pytest.mark.parametrize("primary_type", [KeyboardInterrupt, SystemExit])
def test_broken_add_note_attribute_lookup_preserves_primary_identity(
    report,
    primary_type: type[BaseException],
) -> None:
    class BrokenLookupPrimary(primary_type):
        def __getattribute__(self, name: str):
            if name == "add_note":
                raise RuntimeError("add_note attribute lookup failed")
            return super().__getattribute__(name)

    primary = BrokenLookupPrimary("primary control flow")
    with pytest.raises(primary_type) as caught:
        try:
            raise primary
        except BaseException as original_error:
            report(original_error, RuntimeError("secondary rollback failure"))
            raise

    assert caught.value is primary


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (False, KeyboardInterrupt("guard interrupted")),
        (True, SystemExit("guard terminated")),
    ],
)
def test_capture_guard_failure_restores_tracker_and_preserves_primary(
    mutate, error
) -> None:
    scene = _FailingScene()
    scene.failures.append((mutate, error))

    with pytest.raises(type(error), match=str(error)):
        SceneRectSnapshot.capture(scene)

    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.depth == 0
    assert tracker.internal_change is False
    assert tracker.known_rect == QRectF(-0.5, -0.5, 11.0, 11.0)


def test_signal_connect_exit_does_not_publish_a_stale_tracker() -> None:
    class FailingConnectSignal(_Signal):
        fail_once = True

        def connect(self, callback) -> None:
            self.callbacks.append(callback)
            if self.fail_once:
                self.fail_once = False
                raise SystemExit("scene rect signal connect terminated")

    scene = _FailingScene()
    scene.sceneRectChanged = FailingConnectSignal()

    with pytest.raises(SystemExit, match="scene rect signal connect terminated"):
        SceneRectSnapshot.capture(scene)

    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    assert scene.sceneRectChanged.callbacks == []
    updated = QRectF(100.0, 50.0, 20.0, 30.0)
    scene.setSceneRect(updated)
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    assert snapshot.baseline_rect == updated
    snapshot.restore()
    assert snapshot.tracker.depth == 0
    assert snapshot.tracker.known_rect == updated


@pytest.mark.parametrize("source", ["scene_rect_changed", "connect"])
def test_scene_rect_signal_static_live_descriptor_failure_aborts_and_retries(
    source: str,
) -> None:
    signal = _Signal()
    if source == "scene_rect_changed":
        descriptor = _FailOnceDescriptor(
            "scene rect changed",
            lambda _scene: signal,
        )

        class BrokenSignalScene(_FailingScene):
            sceneRectChanged = descriptor

            def __init__(self) -> None:
                self.rect = QRectF(-0.5, -0.5, 11.0, 11.0)
                self.failures = []

    else:
        descriptor = _FailOnceDescriptor(
            "signal connect",
            lambda target: lambda callback: _Signal.connect(target, callback),
        )

        class BrokenConnectSignal(_Signal):
            connect = descriptor

        class BrokenSignalScene(_FailingScene):
            def __init__(self) -> None:
                super().__init__()
                self.sceneRectChanged = BrokenConnectSignal()

    scene = BrokenSignalScene()
    with pytest.raises(AttributeError):
        SceneRectSnapshot.capture(scene)

    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    snapshot.restore()
    assert snapshot.tracker.depth == 0


@pytest.mark.parametrize("failure_mode", ["fail_once", "no_op"])
def test_state_snapshot_disconnects_later_tracker_before_removing_absent_attr(
    failure_mode: str,
) -> None:
    class DisconnectSignal(_Signal):
        def __init__(self) -> None:
            super().__init__()
            self.failure_mode: str | None = failure_mode
            self.disconnect_calls = 0

        def disconnect(self, callback) -> None:
            self.disconnect_calls += 1
            if self.failure_mode == "fail_once":
                self.failure_mode = None
                raise KeyboardInterrupt("disconnect failed once")
            if self.failure_mode == "no_op":
                return
            super().disconnect(callback)

    scene = _FailingScene()
    signal = DisconnectSignal()
    scene.sceneRectChanged = signal
    state = SceneRectStateSnapshot.capture(scene)
    guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert guard is not None
    tracker = guard.tracker
    callback = tracker.callback
    assert callback is not None and signal.callbacks == [callback]

    if failure_mode == "fail_once":
        state.restore()
        assert state.active is False
        assert signal.disconnect_calls == 2
        assert signal.callbacks == []
        assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    else:
        with pytest.raises(RuntimeError, match="disconnect was a no-op"):
            state.restore()
        assert state.active is True
        assert signal.disconnect_calls == 2
        assert signal.callbacks == [callback]
        assert scene._chemvas_scene_rect_tracker is tracker

        signal.failure_mode = None
        state.restore()
        assert state.active is False
        assert signal.callbacks == []
        assert not hasattr(scene, "_chemvas_scene_rect_tracker")

    guard.release()


def test_state_snapshot_probes_opaque_disconnect_before_discarding_tracker() -> None:
    class OpaqueDisconnectSignal:
        def __init__(self) -> None:
            self._receivers = []
            self.disconnect_calls = 0
            self.no_op = True

        def connect(self, callback) -> None:
            self._receivers.append(callback)

        def emit(self, rect) -> None:
            for callback in tuple(self._receivers):
                callback(rect)

        def disconnect(self, callback) -> None:
            self.disconnect_calls += 1
            if self.no_op:
                return
            self._receivers.remove(callback)

    scene = _FailingScene()
    signal = OpaqueDisconnectSignal()
    scene.sceneRectChanged = signal
    state = SceneRectStateSnapshot.capture(scene)
    guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert guard is not None
    tracker = guard.tracker
    callback = tracker.callback
    assert callback is not None and signal._receivers == [callback]

    with pytest.raises(RuntimeError, match="disconnect was a no-op"):
        state.restore()

    assert state.active is True
    assert signal.disconnect_calls == 2
    assert signal._receivers == [callback]
    assert scene._chemvas_scene_rect_tracker is tracker

    signal.no_op = False
    state.restore()
    assert state.active is False
    assert signal._receivers == []
    assert not hasattr(scene, "_chemvas_scene_rect_tracker")

    discarded_known_rect = QRectF(tracker.known_rect)
    scene.setSceneRect(QRectF(90.0, 80.0, 70.0, 60.0))
    assert tracker.known_rect == discarded_known_rect


def test_state_snapshot_replaces_and_disconnects_a_later_tracker_exactly() -> None:
    scene = _FailingScene()
    original_guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert original_guard is not None
    original = original_guard.tracker
    original_callback = original.callback
    assert original_callback is not None
    state = SceneRectStateSnapshot.capture(scene)

    delattr(scene, "_chemvas_scene_rect_tracker")
    replacement_guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert replacement_guard is not None
    replacement = replacement_guard.tracker
    replacement_callback = replacement.callback
    assert replacement_callback is not None
    assert scene.sceneRectChanged.callbacks == [
        original_callback,
        replacement_callback,
    ]

    state.restore()

    assert scene._chemvas_scene_rect_tracker is original
    assert original.connected is True
    assert replacement.connected is False
    assert scene.sceneRectChanged.callbacks == [original_callback]
    original_guard.release()
    replacement_guard.release()


def test_state_snapshot_rearms_mutated_handles_on_the_same_tracker() -> None:
    scene = _FailingScene()
    guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert guard is not None
    tracker = guard.tracker
    original_callback = tracker.callback
    original_disconnect = tracker.disconnect_port
    assert original_callback is not None and original_disconnect is not None
    state = SceneRectStateSnapshot.capture(scene)

    original_disconnect(original_callback)

    def replacement_callback(_rect) -> None:
        return

    scene.sceneRectChanged.connect(replacement_callback)
    tracker.callback = replacement_callback
    tracker.connection_probe = lambda: any(
        callback is replacement_callback
        for callback in scene.sceneRectChanged.callbacks
    )
    tracker.connected = True

    state.restore()

    assert tracker.callback is original_callback
    assert tracker.connected is True
    assert scene.sceneRectChanged.callbacks == [original_callback]
    guard.release()


@pytest.mark.parametrize("mutate_before_raise", [False, True])
def test_state_snapshot_uses_bound_ports_and_repairs_one_setter_failure(
    mutate_before_raise: bool,
) -> None:
    class Owner:
        def __init__(self) -> None:
            self.rect = QRectF(-5.0, -6.0, 20.0, 30.0)
            self.inherited = QRectF(self.rect)
            self.port_reads = {"get": 0, "set": 0}
            self.fail_port_lookup = False
            self.fail_once = False
            self.setter_calls = 0

        @property
        def sceneRect(self):
            self.port_reads["get"] += 1
            if self.fail_port_lookup:
                raise SystemExit("sceneRect port was re-read")
            return self._get_rect

        @property
        def setSceneRect(self):
            self.port_reads["set"] += 1
            if self.fail_port_lookup:
                raise SystemExit("setSceneRect port was re-read")
            return self._set_rect

        def _get_rect(self) -> QRectF:
            return QRectF(self.rect)

        def _set_rect(self, rect: QRectF) -> None:
            self.setter_calls += 1
            if self.fail_once:
                self.fail_once = False
                if mutate_before_raise:
                    self.rect = (
                        QRectF(self.inherited) if rect.isNull() else QRectF(rect)
                    )
                raise KeyboardInterrupt("state setter failed once")
            self.rect = QRectF(self.inherited) if rect.isNull() else QRectF(rect)

    owner = Owner()
    expected = QRectF(owner.rect)
    state = SceneRectStateSnapshot.capture(owner)
    owner.rect = QRectF(100.0, 200.0, 10.0, 10.0)
    owner.fail_once = True
    owner.fail_port_lookup = True

    state.restore()

    assert state.active is False
    assert owner.rect == expected
    assert owner.port_reads == {"get": 1, "set": 1}
    assert owner.setter_calls == 3


@pytest.mark.parametrize(
    "snapshot_type",
    [SceneRectStateSnapshot, ViewSceneRectStateSnapshot],
)
def test_rect_state_persistent_no_op_stays_active_until_exact_retry(
    snapshot_type,
) -> None:
    class Owner:
        def __init__(self) -> None:
            self.rect = QRectF(-5.0, -6.0, 20.0, 30.0)
            self.inherited = QRectF(self.rect)
            self.no_op = False
            self.setter_calls = 0

        def sceneRect(self) -> QRectF:
            return QRectF(self.rect)

        def setSceneRect(self, rect: QRectF) -> None:
            self.setter_calls += 1
            if self.no_op:
                return
            self.rect = QRectF(self.inherited) if rect.isNull() else QRectF(rect)

    owner = Owner()
    expected = QRectF(owner.rect)
    state = snapshot_type.capture(owner)
    owner.rect = QRectF(100.0, 200.0, 10.0, 10.0)
    owner.no_op = True

    with pytest.raises(RuntimeError, match="verification probe"):
        state.restore()

    assert state.active is True
    assert owner.setter_calls == 2
    owner.no_op = False
    state.restore()
    assert state.active is False
    assert owner.rect == expected


def test_actual_qt_null_scene_state_restore_preserves_future_growth() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    assert scene.sceneRect().isNull()
    state = SceneRectStateSnapshot.capture(scene)
    set_explicit_scene_rect(scene, QRectF(-10.0, -20.0, 30.0, 40.0))

    state.restore()

    assert state.active is False
    assert scene.sceneRect().isNull()
    assert scene_rect_is_automatic(scene)
    assert not hasattr(scene, "_chemvas_scene_rect_automatic")
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


def test_actual_qt_view_state_restores_inherited_and_explicit_modes() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    view = QGraphicsView(scene)
    inherited = QRectF(view.sceneRect())
    inherited_state = ViewSceneRectStateSnapshot.capture(view)
    set_explicit_view_scene_rect(
        view,
        QRectF(-100.0, -100.0, 200.0, 200.0),
    )

    inherited_state.restore()

    assert inherited_state.active is False
    assert view.sceneRect() == inherited
    assert not view_scene_rect_is_explicit(view)
    assert not hasattr(view, "_chemvas_view_scene_rect_explicit")
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert view.sceneRect().right() > 10_000.0
    scene.removeItem(future)

    fixed = QRectF(-50.0, -60.0, 120.0, 140.0)
    set_explicit_view_scene_rect(view, fixed)
    explicit_state = ViewSceneRectStateSnapshot.capture(view)
    set_explicit_view_scene_rect(view, QRectF(1.0, 2.0, 3.0, 4.0))
    explicit_state.restore()
    assert view.sceneRect() == fixed
    assert view_scene_rect_is_explicit(view)


@pytest.mark.parametrize(
    "helper",
    ["scene_explicit", "view_explicit", "view_inherited"],
)
@pytest.mark.parametrize("failure_mode", ["no_op", "fail_after", "system_exit"])
def test_actual_qt_rect_mode_helpers_restore_exact_state_after_setter_failure(
    helper: str,
    failure_mode: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class FailingScene(QGraphicsScene):
        armed = False

        def setSceneRect(self, *args) -> None:
            if not self.armed:
                QGraphicsScene.setSceneRect(self, *args)
                return
            if failure_mode == "no_op":
                return
            if failure_mode == "fail_after":
                QGraphicsScene.setSceneRect(self, *args)
                raise RuntimeError("scene rect setter failed after mutation")
            raise SystemExit("scene rect setter terminated")

    class FailingView(QGraphicsView):
        armed = False

        def setSceneRect(self, *args) -> None:
            if not self.armed:
                QGraphicsView.setSceneRect(self, *args)
                return
            if failure_mode == "no_op":
                return
            if failure_mode == "fail_after":
                QGraphicsView.setSceneRect(self, *args)
                raise RuntimeError("view rect setter failed after mutation")
            raise SystemExit("view rect setter terminated")

    scene = FailingScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    view = FailingView(scene)
    if helper == "view_inherited":
        old_rect = QRectF(-50.0, -60.0, 120.0, 140.0)
        QGraphicsView.setSceneRect(view, old_rect)
        view._chemvas_view_scene_rect_explicit = True
        old_marker = True
        view.armed = True
    elif helper == "view_explicit":
        old_rect = QRectF(view.sceneRect())
        old_marker = False
        view.armed = True
    else:
        old_rect = QRectF(scene.sceneRect())
        old_marker = True
        scene.armed = True

    def operation() -> None:
        if helper == "view_inherited":
            set_inherited_view_scene_rect(view)
        elif helper == "view_explicit":
            set_explicit_view_scene_rect(
                view,
                QRectF(100.0, 100.0, 20.0, 20.0),
            )
        else:
            set_explicit_scene_rect(
                scene,
                QRectF(100.0, 100.0, 20.0, 20.0),
            )

    expected_error = SystemExit if failure_mode == "system_exit" else RuntimeError
    with pytest.raises(expected_error):
        operation()

    target = scene if helper == "scene_explicit" else view
    assert target.sceneRect() == old_rect
    if helper == "scene_explicit":
        assert scene_rect_is_automatic(scene) is old_marker
    else:
        assert view_scene_rect_is_explicit(view) is old_marker


@pytest.mark.parametrize("action", ["release", "restore", "commit"])
def test_nested_guard_finalizers_consume_one_depth_without_setter(action: str) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    setter_calls = 0

    def counted_setter(rect: QRectF) -> None:
        nonlocal setter_calls
        setter_calls += 1
        scene.setSceneRect(rect)

    outer = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=counted_setter,
    )
    inner = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=counted_setter,
    )
    assert outer is not None and inner is not None
    setter_calls = 0

    if action == "release":
        inner.release(QRectF(20.0, 0.0, 2.0, 2.0))
    elif action == "restore":
        inner.restore()
    else:
        inner.commit_replacement(QRectF(20.0, 0.0, 2.0, 2.0))

    assert setter_calls == 0
    assert outer.tracker.depth == 1
    assert inner.active is False
    outer.restore()


def test_top_level_release_persistent_no_op_stays_active_for_retry() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    no_op = False
    setter_calls = 0

    def controlled_setter(rect: QRectF) -> None:
        nonlocal setter_calls
        setter_calls += 1
        if not no_op:
            scene.setSceneRect(rect)

    snapshot = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=controlled_setter,
    )
    assert snapshot is not None
    setter_calls = 0
    no_op = True

    with pytest.raises(RuntimeError, match="verification probe"):
        snapshot.release(QRectF(20.0, 0.0, 2.0, 2.0))

    assert snapshot.active is True
    assert snapshot.tracker.depth == 1
    assert setter_calls == 2
    no_op = False
    snapshot.release(QRectF(20.0, 0.0, 2.0, 2.0))
    assert snapshot.active is False
    assert snapshot.tracker.depth == 0


def test_set_scene_rect_forward_mutation_uses_captured_ports() -> None:
    shared = {"block_lookup": False}

    class RectOwner:
        def __init__(self, *, blocks_after_setter_capture: bool = False) -> None:
            self.rect = QRectF(0.0, 0.0, 10.0, 10.0)
            self.port_reads = {"get": 0, "set": 0}
            self.blocks_after_setter_capture = blocks_after_setter_capture

        @property
        def sceneRect(self):
            self.port_reads["get"] += 1
            if shared["block_lookup"]:
                raise SystemExit("sceneRect port was re-read")
            return self._get_rect

        @property
        def setSceneRect(self):
            self.port_reads["set"] += 1
            if shared["block_lookup"]:
                raise SystemExit("setSceneRect port was re-read")
            port = self._set_rect
            if self.blocks_after_setter_capture:
                shared["block_lookup"] = True
            return port

        def _get_rect(self) -> QRectF:
            return QRectF(self.rect)

        def _set_rect(self, rect: QRectF) -> None:
            self.rect = QRectF(rect)

    scene = RectOwner()

    class Canvas(RectOwner):
        def __init__(self) -> None:
            super().__init__(blocks_after_setter_capture=True)

        @staticmethod
        def scene():
            return scene

    canvas = Canvas()
    target = QRectF(-20.0, -30.0, 40.0, 50.0)

    set_scene_rect_for(canvas, target)

    assert scene.rect == target
    assert canvas.rect == target
    assert scene.port_reads == {"get": 1, "set": 1}
    assert canvas.port_reads == {"get": 1, "set": 1}


@pytest.mark.parametrize("mutate", [False, True])
def test_release_retries_one_failure_and_clears_nested_depth(mutate) -> None:
    scene = _FailingScene()
    outer = SceneRectSnapshot.capture(scene)
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and inner is not None
    inner.release(QRectF(20.0, 0.0, 2.0, 2.0))
    assert outer.tracker.depth == 1
    scene.failures.append((mutate, SystemExit("release terminated")))

    # A first setter failure is repaired inside the bounded two-attempt
    # finalizer; callers only see an error when both attempts fail.
    outer.release(QRectF(40.0, 0.0, 2.0, 2.0))

    assert outer.active is False
    assert outer.tracker.depth == 0
    assert outer.tracker.internal_change is False


@pytest.mark.parametrize("guard_growth", [False, True])
@pytest.mark.parametrize(
    ("failure_call", "mutate_before_raise"),
    [
        (1, False),
        (1, True),
        (2, False),
        (2, True),
    ],
)
def test_automatic_restore_repairs_one_failure_with_actual_qt_scene(
    guard_growth: bool,
    failure_call: int,
    mutate_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = QRectF(scene.sceneRect())
    original_set_scene_rect = scene.setSceneRect
    calls = 0
    armed = False

    def fail_one_restore_step(rect: QRectF) -> None:
        nonlocal calls
        if armed:
            calls += 1
            if calls == failure_call:
                if mutate_before_raise:
                    original_set_scene_rect(rect)
                raise SystemExit("automatic rect restore terminated")
        original_set_scene_rect(rect)

    snapshot = SceneRectSnapshot.capture(
        scene,
        guard_growth=guard_growth,
        set_scene_rect_setter=fail_one_restore_step,
    )
    assert snapshot is not None
    tracker = snapshot.tracker
    armed = True
    snapshot.restore()

    assert snapshot.active is False
    assert calls == (3 if failure_call == 1 else 4)
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert tracker.known_rect == baseline
    assert scene_rect_is_automatic(scene)
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize("mutate_before_raise", [False, True])
def test_explicit_restore_repairs_one_failure_internally(
    mutate_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    fixed = QRectF(-50.0, -50.0, 100.0, 100.0)
    target = QRectF(-10.0, -20.0, 30.0, 40.0)
    set_explicit_scene_rect(scene, fixed)
    original_set_scene_rect = scene.setSceneRect
    calls = 0
    failed = False
    armed = False

    def fail_once(rect: QRectF) -> None:
        nonlocal calls, failed
        if armed:
            calls += 1
            if not failed:
                failed = True
                if mutate_before_raise:
                    original_set_scene_rect(rect)
                raise KeyboardInterrupt("explicit rect restore interrupted")
        original_set_scene_rect(rect)

    snapshot = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=fail_once,
    )
    assert snapshot is not None
    set_explicit_scene_rect(scene, target)
    armed = True
    snapshot.restore()

    assert snapshot.active is False
    assert calls == 3
    assert snapshot.tracker.known_rect == fixed
    assert scene.sceneRect() == fixed
    assert scene_rect_is_automatic(scene) is False
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect() == fixed
    scene.removeItem(future)


def test_persistent_outer_restore_failure_preserves_pending_journal_for_retry() -> None:
    scene = _FailingScene()
    failures: list[BaseException] = []

    def fail_persistently(rect: QRectF) -> None:
        if failures:
            raise failures.pop(0)
        scene.setSceneRect(rect)

    outer = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=fail_persistently,
    )
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and inner is not None
    expansion_key = object()
    inner.release(
        QRectF(10_000.0, 0.0, 10.0, 10.0),
        expansion_key=expansion_key,
    )
    tracker = outer.tracker
    pending_rect = QRectF(tracker.pending_rect)
    pending_expansions = {
        key: QRectF(rect) for key, rect in tracker.pending_expansions.items()
    }
    pending_journal = [
        (
            key,
            existed,
            QRectF(previous) if previous is not None else None,
        )
        for key, existed, previous in tracker.pending_journal
    ]
    failures.extend(
        [
            SystemExit("nested rect restore terminated"),
            SystemExit("nested rect restore terminated again"),
        ]
    )

    with pytest.raises(SystemExit, match="nested rect restore terminated"):
        outer.restore()

    assert outer.active is True
    assert tracker.depth == 1
    assert tracker.pending_rect == pending_rect
    assert tracker.pending_expansions == pending_expansions
    assert tracker.pending_journal == pending_journal
    assert tracker.internal_change is False

    outer.restore()

    assert outer.active is False
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert tracker.known_rect == outer.baseline_rect


def test_auto_scene_guard_has_linear_normal_path_and_keeps_future_growth() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class CountingItem(QGraphicsRectItem):
        calls = 0

        def boundingRect(self):
            type(self).calls += 1
            return super().boundingRect()

    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    for index in range(30):
        item = CountingItem(QRectF(float(index * 20), 0.0, 10.0, 10.0))
        snapshot = SceneRectSnapshot.capture(
            scene,
            incremental_tracking=True,
        )
        assert snapshot is not None
        scene.addItem(item)
        snapshot.release(item.sceneBoundingRect())

    assert CountingItem.calls <= 60
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)
    view.close()


def test_existing_tracker_syncs_lazy_raw_external_growth_before_outer_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    initial = SceneRectSnapshot.capture(scene)
    assert initial is not None
    initial.release(scene.itemsBoundingRect())

    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    # Do not call scene.sceneRect(): Qt has not yet emitted its lazy growth.
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None

    assert snapshot.baseline_rect.contains(far.sceneBoundingRect())
    assert scene.sceneRect().contains(far.sceneBoundingRect())
    snapshot.restore()
    assert snapshot.active is False
    assert snapshot.tracker.depth == 0


def test_incremental_abort_absorbs_lazy_growth_omitted_by_prior_hint() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    near = scene.addRect(0.0, 0.0, 10.0, 10.0)
    initial = SceneRectSnapshot.capture(scene, incremental_tracking=True)
    assert initial is not None
    initial.release(
        near.sceneBoundingRect(),
        expansion_key=near,
        expansion_owner_scene_getter=near.scene,
    )

    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    successful = SceneRectSnapshot.capture(scene, incremental_tracking=True)
    assert successful is not None
    middle = scene.addRect(100.0, 0.0, 10.0, 10.0)
    successful.release(
        middle.sceneBoundingRect(),
        expansion_key=middle,
        expansion_owner_scene_getter=middle.scene,
    )
    assert not successful.tracker.known_rect.contains(far.sceneBoundingRect())

    aborted = SceneRectSnapshot.capture(scene, incremental_tracking=True)
    assert aborted is not None
    aborted.restore()

    assert aborted.active is False
    assert aborted.tracker.depth == 0
    assert aborted.tracker.known_rect.contains(far.sceneBoundingRect())
    assert scene.sceneRect() == aborted.tracker.known_rect


def test_actual_qt_internal_rect_probes_are_not_published_to_observers() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    view = QGraphicsView(scene)
    observed: list[QRectF] = []
    scene.sceneRectChanged.connect(lambda rect: observed.append(QRectF(rect)))

    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    item = scene.addRect(100.0, 0.0, 10.0, 10.0)
    # No expansion hint: the preflight must derive the current item bounds
    # without first publishing Qt's grow-only automatic scene cache.
    snapshot.release()

    assert observed == []
    assert snapshot.active is False
    assert snapshot.tracker.depth == 0
    assert snapshot.tracker.known_rect.contains(item.sceneBoundingRect())
    view.close()


@pytest.mark.parametrize("disconnect_fails_after", [False, True])
def test_actual_qt_proxy_signal_does_not_publish_internal_rect_probes(
    disconnect_fails_after: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class SignalProxy:
        def __init__(self, signal) -> None:
            self.signal = signal
            self.fail_after_disconnect = False
            self.connect_calls = 0
            self.disconnect_calls = 0

        def connect(self, callback) -> None:
            self.connect_calls += 1
            self.signal.connect(callback)

        def disconnect(self, callback) -> None:
            self.disconnect_calls += 1
            self.signal.disconnect(callback)
            if self.fail_after_disconnect:
                self.fail_after_disconnect = False
                raise RuntimeError("proxy disconnect failed after mutation")

    class ProxyScene(QGraphicsScene):
        def __init__(self) -> None:
            super().__init__()
            actual = QGraphicsScene.sceneRectChanged.__get__(self, type(self))
            self.proxy = SignalProxy(actual)

        @property
        def sceneRectChanged(self):
            return self.proxy

    scene = ProxyScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    actual_signal = QGraphicsScene.sceneRectChanged.__get__(scene, type(scene))
    observed: list[QRectF] = []
    actual_signal.connect(lambda rect: observed.append(QRectF(rect)))

    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    scene.proxy.fail_after_disconnect = disconnect_fails_after
    item = scene.addRect(100.0, 0.0, 10.0, 10.0)
    snapshot.release(item.sceneBoundingRect())

    assert observed == []
    assert snapshot.active is False
    assert snapshot.tracker.depth == 0
    assert snapshot.recovery_errors == []
    assert scene.proxy.connect_calls == 0
    assert scene.proxy.disconnect_calls == 0


def test_actual_qt_tracker_never_allows_proxy_to_disconnect_another_receiver() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class MisroutingSignalProxy:
        def __init__(self, signal) -> None:
            self.signal = signal
            self.external_callback = None
            self.connect_calls = 0
            self.disconnect_calls = 0

        def connect(self, callback) -> None:
            self.connect_calls += 1
            self.signal.connect(callback)

        def disconnect(self, _callback) -> None:
            self.disconnect_calls += 1
            assert self.external_callback is not None
            self.signal.disconnect(self.external_callback)

    class ProxyScene(QGraphicsScene):
        def __init__(self) -> None:
            super().__init__()
            actual = QGraphicsScene.sceneRectChanged.__get__(self, type(self))
            self.proxy = MisroutingSignalProxy(actual)

        @property
        def sceneRectChanged(self):
            return self.proxy

    scene = ProxyScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    actual_signal = QGraphicsScene.sceneRectChanged.__get__(scene, type(scene))
    observed: list[QRectF] = []

    def remember_external(rect: QRectF) -> None:
        observed.append(QRectF(rect))

    scene.proxy.external_callback = remember_external
    actual_signal.connect(remember_external)
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    item = scene.addRect(100.0, 0.0, 10.0, 10.0)

    snapshot.release(item.sceneBoundingRect())

    assert snapshot.active is False
    assert scene.proxy.connect_calls == 0
    assert scene.proxy.disconnect_calls == 0
    external_rect = QRectF(20.0, 30.0, 40.0, 50.0)
    QGraphicsScene.setSceneRect(scene, external_rect)
    assert observed == [external_rect]


def test_explicit_outer_capture_syncs_raw_rect_changed_while_signals_blocked() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    initial = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert initial is not None
    initial.release()
    old_rect = QRectF(0.0, 0.0, 10.0, 10.0)
    live_rect = QRectF(20.0, 30.0, 40.0, 50.0)
    later_rect = QRectF(100.0, 200.0, 30.0, 40.0)
    set_explicit_scene_rect(scene, old_rect)
    tracker = scene._chemvas_scene_rect_tracker

    previous = scene.blockSignals(True)
    try:
        QGraphicsScene.setSceneRect(scene, live_rect)
    finally:
        scene.blockSignals(previous)
    assert tracker.known_rect == old_rect
    assert scene.sceneRect() == live_rect

    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    assert snapshot.baseline_rect == live_rect
    QGraphicsScene.setSceneRect(scene, later_rect)
    snapshot.restore()

    assert snapshot.active is False
    assert scene.sceneRect() == live_rect
    assert tracker.known_rect == live_rect
    assert scene_rect_is_automatic(scene) is False


def test_actual_qt_view_refresh_blocks_view_and_both_scrollbar_signals() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    view = QGraphicsView(scene)
    view.resize(80, 80)
    view.show()
    app.processEvents()
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    horizontal = view.horizontalScrollBar()
    vertical = view.verticalScrollBar()
    rogue_rect = QRectF(777.0, 888.0, 9.0, 9.0)
    callbacks: list[str] = []

    def poison_scene_from_horizontal(*_args) -> None:
        callbacks.append("horizontal")
        QGraphicsScene.setSceneRect(scene, rogue_rect)

    def poison_scene_from_vertical(*_args) -> None:
        callbacks.append("vertical")
        QGraphicsScene.setSceneRect(scene, rogue_rect)

    horizontal.rangeChanged.connect(poison_scene_from_horizontal)
    vertical.rangeChanged.connect(poison_scene_from_vertical)
    item = scene.addRect(10_000.0, 20_000.0, 10.0, 10.0)

    snapshot.release(item.sceneBoundingRect())

    assert callbacks == []
    assert not view.signalsBlocked()
    assert not horizontal.signalsBlocked()
    assert not vertical.signalsBlocked()
    assert snapshot.active is False
    assert snapshot.tracker.depth == 0
    assert scene.sceneRect() == snapshot.tracker.known_rect
    assert scene.sceneRect().contains(item.sceneBoundingRect())
    assert scene.sceneRect() != rogue_rect
    view.close()


@pytest.mark.parametrize("failure_mode", ["raise", "rogue_rect"])
def test_view_refresh_failure_keeps_guard_active_for_exact_rollback(
    failure_mode: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = QRectF(scene.sceneRect())
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    item = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    rogue_rect = QRectF(777.0, 888.0, 9.0, 9.0)
    updater_calls = 0

    def fail_refresh(_rect: QRectF) -> None:
        nonlocal updater_calls
        updater_calls += 1
        if failure_mode == "raise":
            raise RuntimeError("view updater failed")
        QGraphicsScene.setSceneRect(scene, rogue_rect)

    snapshot.view_scene_rect_updaters = (fail_refresh,)
    expected_message = (
        "view updater failed"
        if failure_mode == "raise"
        else "view scene-rect refresh changed the guarded scene rect"
    )

    with pytest.raises(RuntimeError, match=expected_message):
        snapshot.release(item.sceneBoundingRect())

    assert updater_calls == 2
    assert snapshot.active is True
    assert snapshot.tracker.depth == 1
    assert scene._chemvas_scene_rect_tracker is snapshot.tracker
    scene.removeItem(item)
    snapshot.restore()

    assert snapshot.active is False
    assert snapshot.tracker.depth == 0
    assert scene_rect_is_automatic(scene)
    assert scene.sceneRect() == baseline
    assert snapshot.tracker.known_rect == baseline


@pytest.mark.parametrize(
    ("poison", "expected_message"),
    [
        ("tracker_root", "replaced tracker ownership"),
        ("depth", "changed the guard depth"),
        ("active", "changed the active savepoint"),
    ],
)
def test_view_refresh_cas_failure_unwinds_the_active_guard_authority(
    poison: str,
    expected_message: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = QRectF(scene.sceneRect())
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    tracker = snapshot.tracker
    item = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    replacement_root = object()
    updater_calls = 0

    def poison_guard(_rect: QRectF) -> None:
        nonlocal updater_calls
        updater_calls += 1
        if poison == "tracker_root":
            scene._chemvas_scene_rect_tracker = replacement_root
        elif poison == "depth":
            tracker.depth = 2
        else:
            snapshot.active = False

    snapshot.view_scene_rect_updaters = (poison_guard,)

    with pytest.raises(RuntimeError, match=expected_message):
        snapshot.release(item.sceneBoundingRect())

    assert updater_calls == 2
    assert snapshot.active is True
    assert snapshot.tracker is tracker
    assert scene._chemvas_scene_rect_tracker is tracker
    assert tracker.depth == 1
    assert scene_rect_is_automatic(scene)

    scene.removeItem(item)
    snapshot.restore()

    assert snapshot.active is False
    assert scene._chemvas_scene_rect_tracker is tracker
    assert tracker.depth == 0
    assert scene_rect_is_automatic(scene)
    assert scene.sceneRect() == baseline
    assert tracker.known_rect == baseline


def test_nested_same_item_release_commits_only_final_geometry() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(100.0, 0.0, 10.0, 10.0)
    outer = SceneRectSnapshot.capture(scene)
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and inner is not None
    item = scene.addRect(0.0, 0.0, 10.0, 10.0)
    inner.release(item.sceneBoundingRect(), expansion_key=item)
    item.setPos(10_000.0, 0.0)
    outer.release(item.sceneBoundingRect(), expansion_key=item)

    assert outer.tracker.known_rect.left() == pytest.approx(99.5)
    assert outer.tracker.known_rect.right() > 10_000.0
    assert scene.sceneRect() == outer.tracker.known_rect


def test_unique_nested_releases_do_not_rescan_pending_expansions() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    snapshots = [SceneRectSnapshot.capture(scene) for _ in range(2001)]
    assert all(snapshot is not None for snapshot in snapshots)
    outer = snapshots[0]
    assert outer is not None

    class CountingDict(dict):
        values_calls = 0

        def values(self):
            self.values_calls += 1
            return super().values()

    pending = CountingDict()
    outer.tracker.pending_expansions = pending
    keys = [object() for _ in range(1000)]
    for index, (snapshot, key) in enumerate(zip(snapshots[1:1001], keys, strict=True)):
        assert snapshot is not None
        snapshot.release(
            QRectF(float(index * 20), 0.0, 10.0, 10.0),
            expansion_key=key,
        )
    for index, (snapshot, key) in enumerate(zip(snapshots[1001:], keys, strict=True)):
        assert snapshot is not None
        snapshot.release(
            QRectF(float(index * 20 + 5), 5.0, 10.0, 10.0),
            expansion_key=key,
        )
    outer.release()

    assert pending.values_calls == 1
    assert outer.tracker.depth == 0


def test_nested_parent_restore_rewinds_successful_child_expansion() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = scene.sceneRect()
    outer = SceneRectSnapshot.capture(scene)
    middle = SceneRectSnapshot.capture(scene)
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and middle is not None and inner is not None
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    far_rect = far.sceneBoundingRect()

    inner.release(far_rect, expansion_key=far)
    scene.removeItem(far)
    middle.restore()
    outer.release()

    tracker = outer.tracker
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert scene.sceneRect() == baseline
    assert tracker.known_rect == baseline
    follow_up = SceneRectSnapshot.capture(scene)
    assert follow_up is not None
    assert follow_up.baseline_rect == baseline
    follow_up.restore()


@pytest.mark.parametrize(
    ("depth", "actions", "keeps_far_item"),
    [
        (1, ("release",), True),
        (1, ("restore",), False),
        (2, ("release", "release"), True),
        (2, ("release", "restore"), False),
        (2, ("restore", "release"), False),
        (3, ("release", "release", "release"), True),
        (3, ("release", "restore", "release"), False),
        (3, ("restore", "release", "release"), False),
    ],
)
def test_nested_scene_rect_state_machine_invariants(
    depth: int,
    actions: tuple[str, ...],
    keeps_far_item: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = scene.sceneRect()
    snapshots = [SceneRectSnapshot.capture(scene) for _ in range(depth)]
    assert all(snapshot is not None for snapshot in snapshots)
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    far_rect = far.sceneBoundingRect()
    far_removed = False

    for index, (snapshot, action) in enumerate(
        zip(reversed(snapshots), actions, strict=True)
    ):
        assert snapshot is not None
        if action == "restore":
            if not far_removed:
                scene.removeItem(far)
                far_removed = True
            snapshot.restore()
        else:
            snapshot.release(
                far_rect if index == 0 and not far_removed else None,
                expansion_key=far,
            )

    tracker = snapshots[0].tracker
    assert all(snapshot is not None and not snapshot.active for snapshot in snapshots)
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert scene_rect_is_automatic(scene)
    if keeps_far_item:
        assert far.scene() is scene
        assert scene.sceneRect().right() > 10_000.0
    else:
        assert far.scene() is None
        assert scene.sceneRect() == baseline
    assert tracker.known_rect == scene.sceneRect()
    follow_up = SceneRectSnapshot.capture(scene)
    assert follow_up is not None
    assert follow_up.baseline_rect == scene.sceneRect()
    follow_up.restore()


def test_explicit_scene_contract_is_preserved_without_auto_release() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    fixed = QRectF(-50.0, -50.0, 100.0, 100.0)
    set_explicit_scene_rect(scene, fixed)
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    snapshot.release(far.sceneBoundingRect())

    assert scene.sceneRect() == fixed
    assert scene._chemvas_scene_rect_automatic is False


def test_item_getter_system_exit_precedes_scene_rect_guard_creation() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = SimpleNamespace(scene=lambda: scene)

    class BrokenItem:
        def data(self, role: int):
            return "shape" if role == 0 else None

        def flags(self):
            raise SystemExit("flags terminated")

        def setFlags(self, _flags) -> None:
            return

    with pytest.raises(SystemExit, match="flags terminated"):
        SceneItemAttachSnapshot.capture(canvas, BrokenItem())

    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize("error_type", [AttributeError, RuntimeError])
def test_live_scene_getter_failure_aborts_attach_snapshot_before_guard(
    error_type: type[Exception],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
    item.setData(0, "shape")

    class Canvas:
        calls = 0

        def scene(self):
            self.calls += 1
            if self.calls == 1:
                raise error_type("live scene capture failed")
            return scene

    canvas = Canvas()
    with pytest.raises(error_type, match="live scene capture failed"):
        SceneItemAttachSnapshot.capture(canvas, item)

    assert item.scene() is None
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize(
    "source",
    [
        "collection",
        "mark_registry",
        "canvas_scene",
        "item_flags",
        "item_text_flags",
        "scene_focus",
        "scene_focus_setter",
    ],
)
def test_attach_snapshot_static_live_descriptor_failure_aborts_before_guard_and_retries(
    source: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene: QGraphicsScene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    collection: list[object] = []
    mark_mapping: dict[int, list[object]] = {}
    kind = "mark" if source == "mark_registry" else "note"
    item: QGraphicsTextItem = QGraphicsTextItem("item")
    item.setData(0, kind)
    if kind == "mark":
        item.setData(1, {"atom_id": 7})
    scene_items_state: object = SimpleNamespace(
        mark_items=collection,
        note_items=collection,
    )
    mark_registry: object = SimpleNamespace(by_atom=mark_mapping)
    canvas: object = SimpleNamespace(
        scene=lambda: scene,
        scene_items_state=scene_items_state,
        mark_registry=mark_registry,
    )

    if source == "collection":
        descriptor = _FailOnceDescriptor("collection", lambda _owner: collection)

        class BrokenSceneItemsState:
            note_items = descriptor

        canvas.scene_items_state = BrokenSceneItemsState()
    elif source == "mark_registry":
        descriptor = _FailOnceDescriptor(
            "mark registry",
            lambda _owner: mark_mapping,
        )

        class BrokenMarkRegistry:
            by_atom = descriptor

        canvas.mark_registry = BrokenMarkRegistry()
    elif source == "canvas_scene":
        descriptor = _FailOnceDescriptor(
            "canvas scene",
            lambda _owner: lambda: scene,
        )

        class BrokenCanvas:
            scene = descriptor

        broken_canvas = BrokenCanvas()
        broken_canvas.scene_items_state = scene_items_state
        broken_canvas.mark_registry = mark_registry
        canvas = broken_canvas
    elif source == "item_flags":
        descriptor = _FailOnceDescriptor(
            "item flags",
            lambda target: lambda: QGraphicsTextItem.flags(target),
        )

        class BrokenFlagsItem(QGraphicsTextItem):
            flags = descriptor

        item = BrokenFlagsItem("item")
        item.setData(0, kind)
    elif source == "item_text_flags":
        descriptor = _FailOnceDescriptor(
            "item text flags",
            lambda target: lambda: QGraphicsTextItem.textInteractionFlags(target),
        )

        class BrokenTextFlagsItem(QGraphicsTextItem):
            textInteractionFlags = descriptor

        item = BrokenTextFlagsItem("item")
        item.setData(0, kind)
    elif source in {"scene_focus", "scene_focus_setter"}:
        focus_port = "focusItem" if source == "scene_focus" else "setFocusItem"

        def focus_port_for(target):
            if focus_port == "focusItem":
                return lambda: QGraphicsScene.focusItem(target)
            return lambda item: QGraphicsScene.setFocusItem(target, item)

        descriptor = _FailOnceDescriptor(
            source.replace("_", " "),
            focus_port_for,
        )
        scene_type = type(
            "BrokenFocusScene",
            (QGraphicsScene,),
            {focus_port: descriptor},
        )
        scene = scene_type()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas.scene = lambda: scene

    if source in {"item_flags", "item_text_flags", "scene_focus"}:
        snapshot = SceneItemAttachSnapshot.capture(canvas, item)
        assert descriptor.calls == 0
        snapshot.release()
        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        assert tracker is None or tracker.depth == 0
        return

    with pytest.raises(AttributeError):
        SceneItemAttachSnapshot.capture(canvas, item)

    assert item.scene() is None
    assert collection == []
    assert mark_mapping == {}
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0

    snapshot = SceneItemAttachSnapshot.capture(canvas, item)
    snapshot.release()
    assert (
        snapshot.scene_rect_snapshot is None or not snapshot.scene_rect_snapshot.active
    )
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0


def test_attach_snapshot_keeps_truly_sparse_fake_fallback() -> None:
    class SparseItem:
        def data(self, role: int):
            return "unknown" if role == 0 else None

    snapshot = SceneItemAttachSnapshot.capture(SimpleNamespace(), SparseItem())

    assert snapshot.scene is None
    assert snapshot.collection is None
    assert snapshot.scene_rect_snapshot is None
    snapshot.release()


def test_attach_focus_restore_uses_captured_ports_and_retries_once() -> None:
    class Item:
        def data(self, role: int):
            return "unknown" if role == 0 else None

        def scene(self):
            return None

    class FocusScene:
        def __init__(self) -> None:
            self._focus_item = object()
            self.focus_getter_reads = 0
            self.focus_setter_reads = 0
            self.focus_getter_calls = 0
            self.focus_setter_calls = 0
            self.fail_port_lookup = False
            self.fail_next_set = False

        @property
        def focusItem(self):
            self.focus_getter_reads += 1
            if self.fail_port_lookup:
                raise SystemExit("focus getter port was re-read")
            return self._get_focus_item

        def _get_focus_item(self):
            self.focus_getter_calls += 1
            return self._focus_item

        @property
        def setFocusItem(self):
            self.focus_setter_reads += 1
            if self.fail_port_lookup:
                raise SystemExit("focus setter port was re-read")
            return self._set_focus_item

        def _set_focus_item(self, item) -> None:
            self.focus_setter_calls += 1
            if self.fail_next_set:
                self.fail_next_set = False
                raise KeyboardInterrupt("attach focus setter failed once")
            self._focus_item = item

    scene = FocusScene()
    original_focus = scene._focus_item
    canvas = SimpleNamespace(scene=lambda: scene)
    snapshot = SceneItemAttachSnapshot.capture(canvas, Item())
    scene._focus_item = object()
    scene.fail_port_lookup = True
    scene.fail_next_set = True
    primary = RuntimeError("attach failed")

    snapshot.restore(primary, phase="an injected attach failure")

    assert scene._focus_item is original_focus
    assert scene.focus_getter_reads == 1
    assert scene.focus_setter_reads == 1
    assert scene.focus_getter_calls == 3
    assert scene.focus_setter_calls == 2
    assert any(
        "attach focus setter failed once" in note
        for note in getattr(primary, "__notes__", [])
    )


@pytest.mark.parametrize("failure_mode", ["raise", "no_op"])
def test_attach_focus_restore_persistent_failure_is_recorded_as_critical(
    failure_mode: str,
) -> None:
    class Item:
        def data(self, role: int):
            return "unknown" if role == 0 else None

        def scene(self):
            return None

    class FocusScene:
        def __init__(self) -> None:
            self.focus_item = object()
            self.failure_mode: str | None = None

        def focusItem(self):
            return self.focus_item

        def setFocusItem(self, item) -> None:
            if self.failure_mode == "raise":
                raise SystemExit("persistent attach focus setter failure")
            if self.failure_mode != "no_op":
                self.focus_item = item

    scene = FocusScene()
    snapshot = SceneItemAttachSnapshot.capture(
        SimpleNamespace(scene=lambda: scene),
        Item(),
    )
    replacement_focus = object()
    scene.focus_item = replacement_focus
    scene.failure_mode = failure_mode
    primary = RuntimeError("attach failed")

    snapshot.restore(primary, phase="an injected attach failure")

    assert scene.focus_item is replacement_focus
    notes = getattr(primary, "__notes__", [])
    expected = (
        "persistent attach focus setter failure"
        if failure_mode == "raise"
        else "did not restore focus identity"
    )
    assert sum(expected in note for note in notes) == 4


@pytest.mark.parametrize("state_name", ["flags", "text"])
@pytest.mark.parametrize("failure_mode", ["fail_once", "no_op"])
def test_attach_item_state_restore_uses_bound_ports_and_verifies(
    state_name: str,
    failure_mode: str,
) -> None:
    class Scene:
        @staticmethod
        def addItem(_item) -> None:
            return None

        @staticmethod
        def removeItem(_item) -> None:
            return None

    class Item:
        def __init__(self) -> None:
            self._flags = "original-flags"
            self._text_flags = "original-text"
            self.port_reads = {
                "flags": 0,
                "setFlags": 0,
                "textInteractionFlags": 0,
                "setTextInteractionFlags": 0,
                "sceneBoundingRect": 0,
            }
            self.setter_calls = {"flags": 0, "text": 0}
            self.fail_port_lookup = False
            self.failure_target: str | None = None
            self.failure_mode: str | None = None

        def data(self, role: int):
            return "unknown" if role == 0 else None

        def scene(self):
            return None

        def _port(self, name: str, value):
            self.port_reads[name] += 1
            if self.fail_port_lookup:
                raise SystemExit(f"{name} port was re-read")
            return value

        @property
        def flags(self):
            return self._port("flags", lambda: self._flags)

        @property
        def setFlags(self):
            return self._port("setFlags", self._set_flags)

        def _set_flags(self, value) -> None:
            self._set_state("flags", value)

        @property
        def textInteractionFlags(self):
            return self._port(
                "textInteractionFlags",
                lambda: self._text_flags,
            )

        @property
        def setTextInteractionFlags(self):
            return self._port(
                "setTextInteractionFlags",
                self._set_text_flags,
            )

        def _set_text_flags(self, value) -> None:
            self._set_state("text", value)

        def _set_state(self, target: str, value) -> None:
            self.setter_calls[target] += 1
            if self.failure_target == target:
                if self.failure_mode == "fail_once":
                    self.failure_mode = None
                    raise KeyboardInterrupt(f"{target} setter failed once")
                if self.failure_mode == "no_op":
                    return
            if target == "flags":
                self._flags = value
            else:
                self._text_flags = value

        @property
        def sceneBoundingRect(self):
            return self._port("sceneBoundingRect", lambda: "bounds")

    item = Item()
    snapshot = SceneItemAttachSnapshot.capture(
        SimpleNamespace(scene=lambda: Scene()),
        item,
    )
    item._flags = "mutated-flags"
    item._text_flags = "mutated-text"
    item.failure_target = state_name
    item.failure_mode = failure_mode
    item.fail_port_lookup = True
    primary = RuntimeError("attach failed")

    snapshot.restore(primary, phase="an injected attach failure")

    assert all(reads == 1 for reads in item.port_reads.values())
    target_value = item._flags if state_name == "flags" else item._text_flags
    if failure_mode == "fail_once":
        assert target_value == f"original-{state_name}"
        assert item.setter_calls[state_name] == 2
    else:
        assert target_value == f"mutated-{state_name}"
        assert item.setter_calls[state_name] == 4
        phase = (
            "restoring item flags"
            if state_name == "flags"
            else "restoring text interaction flags"
        )
        assert sum(phase in note for note in getattr(primary, "__notes__", [])) == 4


def test_attach_release_uses_captured_scene_bounding_rect_port() -> None:
    class Item:
        scene_bounds_port_reads = 0
        scene_bounds_calls = 0
        fail_port_lookup = False

        def data(self, role: int):
            return "unknown" if role == 0 else None

        @property
        def sceneBoundingRect(self):
            self.scene_bounds_port_reads += 1
            if self.fail_port_lookup:
                raise SystemExit("sceneBoundingRect port was re-read")
            return self._scene_bounding_rect

        def _scene_bounding_rect(self):
            self.scene_bounds_calls += 1
            return "captured-bounds"

    class ReleaseSnapshot:
        automatic = True

        def __init__(self) -> None:
            self.released = None

        def release(
            self,
            expanded_rect,
            *,
            expansion_key,
            expansion_owner_scene_getter=None,
        ) -> None:
            self.released = (expanded_rect, expansion_key)

    item = Item()
    snapshot = SceneItemAttachSnapshot.capture(SimpleNamespace(), item)
    rect_snapshot = ReleaseSnapshot()
    snapshot.scene_rect_snapshot = rect_snapshot
    item.fail_port_lookup = True

    snapshot.release()

    assert item.scene_bounds_port_reads == 1
    assert item.scene_bounds_calls == 1
    assert rect_snapshot.released == ("captured-bounds", item)


def test_release_uses_bound_expansion_owner_membership_getter() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)

    class SwitchingSceneItem(QGraphicsRectItem):
        scene_port_reads = 0

        @property
        def scene(self):
            self.scene_port_reads += 1
            if self.scene_port_reads == 1:
                return lambda: QGraphicsRectItem.scene(self)
            return lambda: None

    far = SwitchingSceneItem(20_000.0, 0.0, 10.0, 10.0)
    bound_scene_getter = far.scene
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    QGraphicsScene.addItem(scene, far)
    expanded_rect = far.sceneBoundingRect()

    snapshot.release(
        expanded_rect,
        expansion_key=far,
        expansion_owner_scene_getter=bound_scene_getter,
    )

    assert far.scene_port_reads == 1
    assert snapshot.tracker.known_rect.contains(expanded_rect)
    follow_up = SceneRectSnapshot.capture(scene)
    assert follow_up is not None
    assert follow_up.baseline_rect.contains(expanded_rect)
    follow_up.restore()
    QGraphicsScene.removeItem(scene, far)


@pytest.mark.parametrize(
    "broken_lookup",
    [
        "collection",
        "setFlags",
        "setTextInteractionFlags",
        "setFocusItem",
    ],
)
def test_attach_restore_lookup_failure_does_not_abort_later_exact_steps(
    broken_lookup: str,
) -> None:
    actions: list[tuple[str, object]] = []
    lookup_error = SystemExit(f"persistent {broken_lookup} lookup failure")

    class Owner:
        def __init__(self, items: list[object]) -> None:
            self.note_items = items

        def __getattribute__(self, name: str):
            if name == "note_items" and broken_lookup == "collection":
                raise lookup_error
            return object.__getattribute__(self, name)

    class Item:
        def __getattribute__(self, name: str):
            if name == broken_lookup:
                raise lookup_error
            return object.__getattribute__(self, name)

        @staticmethod
        def setFlags(value) -> None:
            actions.append(("flags", value))

        @staticmethod
        def setTextInteractionFlags(value) -> None:
            actions.append(("text", value))

    class Scene:
        def __getattribute__(self, name: str):
            if name == broken_lookup:
                raise lookup_error
            return object.__getattribute__(self, name)

        @staticmethod
        def setFocusItem(value) -> None:
            actions.append(("focus", value))

    item = Item()
    original_collection = [item]
    replacement_collection = [item]
    owner = Owner(replacement_collection)
    focus_item = object()
    focus_state = {"item": None}

    def set_captured_focus(value) -> None:
        actions.append(("focus", value))
        focus_state["item"] = value

    snapshot = SceneItemAttachSnapshot(
        canvas=SimpleNamespace(scene=lambda: None),
        item=item,
        collection_owner=owner,
        collection_name="note_items",
        collection=original_collection,
        collection_contents=(),
        mark_registry=None,
        mark_mapping=None,
        mark_entries=(),
        mark_atom_id=None,
        mark_entry_existed=False,
        mark_list=None,
        item_flags="original-flags",
        text_interaction_flags="original-text-flags",
        scene=Scene(),
        scene_rect_snapshot=None,
        focus_item=focus_item,
        focus_item_getter=lambda: focus_state["item"],
        focus_item_setter=set_captured_focus,
        scene_runtime_snapshot=None,
        full_graph_snapshot=False,
    )
    primary_error = RuntimeError("attach failed")

    snapshot.restore(primary_error, phase="an injected attach failure")

    assert original_collection == []
    if broken_lookup == "collection":
        assert replacement_collection == [item]
    else:
        assert replacement_collection == []
    expected_actions = {
        "collection": [
            ("flags", "original-flags"),
            ("text", "original-text-flags"),
            ("focus", focus_item),
            ("flags", "original-flags"),
            ("text", "original-text-flags"),
            ("focus", focus_item),
        ],
        "setFlags": [
            ("text", "original-text-flags"),
            ("focus", focus_item),
        ],
        "setTextInteractionFlags": [
            ("flags", "original-flags"),
            ("focus", focus_item),
        ],
        "setFocusItem": [
            ("flags", "original-flags"),
            ("text", "original-text-flags"),
            ("focus", focus_item),
        ],
    }
    assert actions == expected_actions[broken_lookup]
    lookup_was_used = any(
        str(lookup_error) in note for note in getattr(primary_error, "__notes__", [])
    )
    assert lookup_was_used is (broken_lookup != "setFocusItem")


@pytest.mark.parametrize(
    "source",
    [
        "canvas_scene",
        "scene_scene_rect",
        "scene_set_scene_rect",
        "view_scene_rect",
        "view_set_scene_rect",
    ],
)
def test_canvas_rect_capture_static_live_descriptor_failure_aborts_before_mutation_and_retries(
    source: str,
) -> None:
    rect = QRectF(0.0, 0.0, 10.0, 10.0)

    class RectOwner:
        scene_rect_calls = 0
        set_scene_rect_calls = 0

        def sceneRect(self) -> QRectF:
            self.scene_rect_calls += 1
            return QRectF(rect)

        def setSceneRect(self, _rect: QRectF) -> None:
            self.set_scene_rect_calls += 1

    scene: object = RectOwner()

    class Canvas(RectOwner):
        def scene(self):
            return scene

    canvas: object = Canvas()
    if source == "canvas_scene":
        descriptor = _FailOnceDescriptor(
            "canvas scene",
            lambda _owner: lambda: scene,
        )

        class BrokenCanvas(Canvas):
            scene = descriptor

        canvas = BrokenCanvas()
    elif source.startswith("scene_"):
        name = {
            "scene_scene_rect": "sceneRect",
            "scene_set_scene_rect": "setSceneRect",
        }[source]
        inherited = getattr(RectOwner, name)
        descriptor = _FailOnceDescriptor(
            source,
            lambda owner: inherited.__get__(owner, type(owner)),
        )
        scene_type = type("BrokenScene", (RectOwner,), {name: descriptor})
        scene = scene_type()
    else:
        name = {
            "view_scene_rect": "sceneRect",
            "view_set_scene_rect": "setSceneRect",
        }[source]
        inherited = getattr(RectOwner, name)
        descriptor = _FailOnceDescriptor(
            source,
            lambda owner: inherited.__get__(owner, type(owner)),
        )
        canvas_type = type("BrokenCanvas", (Canvas,), {name: descriptor})
        canvas = canvas_type()

    with pytest.raises(AttributeError, match=f"live {descriptor.name} descriptor"):
        CanvasSceneRectStateSnapshot.capture(canvas)

    assert scene.set_scene_rect_calls == 0
    assert canvas.set_scene_rect_calls == 0
    snapshot = CanvasSceneRectStateSnapshot.capture(canvas)
    snapshot.release()
    assert not snapshot.active


@pytest.mark.parametrize("name", ["sceneRect", "setSceneRect"])
def test_scene_rect_guard_static_live_method_descriptor_failure_aborts_and_retries(
    name: str,
) -> None:
    inherited = getattr(_FailingScene, name)
    descriptor = _FailOnceDescriptor(
        name,
        lambda owner: inherited.__get__(owner, type(owner)),
    )
    scene_type = type("BrokenLookupScene", (_FailingScene,), {name: descriptor})
    scene = scene_type()

    with pytest.raises(AttributeError, match=f"live {name} descriptor"):
        SceneRectSnapshot.capture(scene)

    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    snapshot = SceneRectSnapshot.capture(scene)
    assert snapshot is not None
    snapshot.restore()
    assert snapshot.tracker.depth == 0


def test_scene_rect_guard_keeps_truly_sparse_scene_fallback() -> None:
    assert SceneRectSnapshot.capture(SimpleNamespace()) is None


@pytest.mark.parametrize("failure_call", [1, 2])
@pytest.mark.parametrize("mutate_before_raise", [False, True])
def test_attach_scene_rect_restore_uses_capture_bound_setter(
    failure_call: int,
    mutate_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = QRectF(scene.sceneRect())
    canvas = SimpleNamespace(scene=lambda: scene)
    item = QGraphicsRectItem(10_000.0, 0.0, 10.0, 10.0)
    item.setData(0, "shape")
    snapshot = SceneItemAttachSnapshot.capture(canvas, item)
    assert snapshot.scene_rect_snapshot is not None
    scene.addItem(item)
    original_set_scene_rect = scene.setSceneRect
    calls = 0

    def fail_one_restore_step(rect: QRectF) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            if mutate_before_raise:
                original_set_scene_rect(rect)
            raise KeyboardInterrupt("attach scene rect restore interrupted")
        original_set_scene_rect(rect)

    primary = RuntimeError("attach failed")
    with mock.patch.object(
        scene,
        "setSceneRect",
        side_effect=fail_one_restore_step,
    ):
        snapshot.restore(primary, phase="an injected attach failure")

    # Replacing the public descriptor after capture must not redirect recovery
    # away from the exact bound port retained by the snapshot.
    assert calls == 0
    assert item.scene() is None
    assert snapshot.scene_rect_snapshot.active is False
    assert snapshot.scene_rect_snapshot.tracker.depth == 0
    assert scene.sceneRect() == baseline
    assert not any(
        "scene-rect restore" in note for note in getattr(primary, "__notes__", [])
    )
    future = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().right() > 20_000.0
    scene.removeItem(future)


def test_capture_failure_retries_complete_automatic_mode_cleanup() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    original_set_scene_rect = scene.setSceneRect
    calls = 0

    def fail_guard_and_one_cleanup_step(rect: QRectF) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_set_scene_rect(rect)
            raise SystemExit("guard capture terminated after mutation")
        if calls == 3:
            raise KeyboardInterrupt("first null cleanup failed")
        original_set_scene_rect(rect)

    with pytest.raises(SystemExit, match="guard capture terminated"):
        SceneRectSnapshot.capture(
            scene,
            set_scene_rect_setter=fail_guard_and_one_cleanup_step,
        )

    assert calls == 5
    assert scene_rect_is_automatic(scene)
    assert scene._chemvas_scene_rect_tracker.depth == 0
    assert scene._chemvas_scene_rect_tracker.automatic_recovery_required is False
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().contains(future.sceneBoundingRect())
    scene.removeItem(future)


def test_persistent_capture_cleanup_leaves_repair_ownership_for_next_capture() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    original_set_scene_rect = scene.setSceneRect
    calls = 0
    cleanup_blocked = True

    def fail_capture_cleanup(rect: QRectF) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_set_scene_rect(rect)
            raise SystemExit("guard capture terminated")
        if cleanup_blocked and calls in {3, 5}:
            raise KeyboardInterrupt("persistent null cleanup failure")
        original_set_scene_rect(rect)

    with pytest.raises(SystemExit, match="guard capture terminated"):
        SceneRectSnapshot.capture(
            scene,
            set_scene_rect_setter=fail_capture_cleanup,
        )
    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.automatic_recovery_required is True

    cleanup_blocked = False
    retry = SceneRectSnapshot.capture(
        scene,
        set_scene_rect_setter=fail_capture_cleanup,
    )
    assert retry is not None
    assert tracker.automatic_recovery_required is False
    retry.restore()
    future = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect().contains(future.sceneBoundingRect())
    scene.removeItem(future)


def test_actual_qt_state_restore_rearms_callback_disconnected_by_peer() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert guard is not None
    tracker = guard.tracker
    callback = tracker.callback
    assert callback is not None
    state = SceneRectStateSnapshot.capture(scene)
    scene.sceneRectChanged.disconnect(callback)
    state.restore()

    assert state.active is False
    assert state.recovery_errors == []
    previous = QRectF(tracker.known_rect)
    scene.setSceneRect(QRectF(500.0, 500.0, 10.0, 10.0))
    assert tracker.known_rect != previous
    guard.release()


def test_actual_qt_state_restore_preserves_peer_with_mutated_disconnect_port() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    guard = SceneRectSnapshot.capture(scene, guard_growth=False)
    assert guard is not None
    tracker = guard.tracker
    actual_signal = QGraphicsScene.sceneRectChanged.__get__(scene, type(scene))
    observed: list[QRectF] = []

    def remember_external(rect: QRectF) -> None:
        observed.append(QRectF(rect))

    actual_signal.connect(remember_external)
    state = SceneRectStateSnapshot.capture(scene)

    def disconnect_the_peer_instead(_callback) -> None:
        actual_signal.disconnect(remember_external)

    tracker.disconnect_port = disconnect_the_peer_instead
    state.restore()

    target = QRectF(500.0, 600.0, 70.0, 80.0)
    QGraphicsScene.setSceneRect(scene, target)
    assert observed == [target]
    assert tracker.known_rect == target
    guard.release()


def test_opaque_connect_failure_before_mutation_is_repaired_on_next_release() -> None:
    class OpaqueSignal:
        def __init__(self) -> None:
            self.receivers = []
            self.fail_first_connect = True

        def connect(self, callback) -> None:
            if self.fail_first_connect:
                self.fail_first_connect = False
                raise SystemExit("opaque connect failed before mutation")
            self.receivers.append(callback)

        def disconnect(self, callback) -> None:
            if callback not in self.receivers:
                raise TypeError("callback is not connected")
            self.receivers.remove(callback)

        def emit(self, rect: QRectF) -> None:
            for callback in tuple(self.receivers):
                callback(rect)

    class OpaqueScene:
        def __init__(self) -> None:
            self.rect = QRectF(0.0, 0.0, 10.0, 10.0)
            self.inherited = QRectF(self.rect)
            self.sceneRectChanged = OpaqueSignal()

        def sceneRect(self) -> QRectF:
            return QRectF(self.rect)

        def setSceneRect(self, rect: QRectF) -> None:
            self.rect = QRectF(self.inherited if rect.isNull() else rect)
            self.sceneRectChanged.emit(QRectF(self.rect))

    scene = OpaqueScene()
    with pytest.raises(SystemExit, match="opaque connect failed"):
        SceneRectSnapshot.capture(scene)
    # The reversible disconnect probe proves the fail-before connect left no
    # receiver, so there is no uncertain tracker ownership to retain.
    assert not hasattr(scene, "_chemvas_scene_rect_tracker")
    assert scene.sceneRectChanged.receivers == []

    retry = SceneRectSnapshot.capture(scene)
    assert retry is not None
    tracker = retry.tracker
    retry.release(QRectF(20.0, 0.0, 2.0, 2.0))
    assert retry.active is False
    assert tracker.connected is True
    assert tracker.connection_uncertain is False
    assert len(scene.sceneRectChanged.receivers) == 1


def test_detached_nested_expansion_removes_the_prior_key_hint() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    baseline = QRectF(scene.sceneRect())
    item = QGraphicsRectItem(QRectF(10_000.0, 0.0, 10.0, 10.0))
    outer = SceneRectSnapshot.capture(scene)
    inner = SceneRectSnapshot.capture(scene)
    assert outer is not None and inner is not None
    scene.addItem(item)
    hint = QRectF(item.sceneBoundingRect())
    inner.release(hint, expansion_key=item)
    scene.removeItem(item)

    outer.release(hint, expansion_key=item)

    assert outer.tracker.known_rect == baseline
    follow_up = SceneRectSnapshot.capture(scene)
    assert follow_up is not None
    follow_up.restore()
    assert follow_up.active is False


def test_empty_nested_rewinds_do_not_rescan_existing_expansions() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    outer = SceneRectSnapshot.capture(scene)
    assert outer is not None

    class CountingDict(dict):
        values_calls = 0

        def values(self):
            type(self).values_calls += 1
            return super().values()

    pending = CountingDict()
    outer.tracker.pending_expansions = pending
    keys = [object() for _index in range(200)]
    for index, key in enumerate(keys):
        child = SceneRectSnapshot.capture(scene)
        assert child is not None
        child.release(
            QRectF(float(index * 20), 0.0, 10.0, 10.0),
            expansion_key=key,
        )
    CountingDict.values_calls = 0

    for _index in range(200):
        child = SceneRectSnapshot.capture(scene)
        assert child is not None
        child.restore()

    assert CountingDict.values_calls == 0
    outer.restore()


def test_history_release_uses_capture_bound_full_scene_bounds_port() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class Scene(QGraphicsScene):
        pass

    scene = Scene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    snapshot = _capture_scene_rect_snapshot(scene)
    assert snapshot is not None
    far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
    Scene.itemsBoundingRect = lambda _scene: QRectF(0.0, 0.0, 1.0, 1.0)

    _release_scene_rect_snapshot(snapshot)

    assert snapshot.tracker.known_rect.contains(far.sceneBoundingRect())
    follow_up = SceneRectSnapshot.capture(scene)
    assert follow_up is not None
    follow_up.restore()


def test_custom_attach_callback_uses_full_bounds_fallback_only_at_top_level() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class CallbackScene(QGraphicsScene):
        def __init__(self) -> None:
            super().__init__()
            self.extra_item = None
            self.add_extra = False
            self.bounds_calls = 0

        def addItem(self, item) -> None:
            QGraphicsScene.addItem(self, item)
            if self.add_extra and self.extra_item is None:
                self.extra_item = QGraphicsRectItem(QRectF(10_000.0, 0.0, 10.0, 10.0))
                QGraphicsScene.addItem(self, self.extra_item)

        def itemsBoundingRect(self) -> QRectF:
            self.bounds_calls += 1
            return QGraphicsScene.itemsBoundingRect(self)

    scene = CallbackScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = SimpleNamespace(scene=lambda: scene)
    item = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    item.setData(0, "shape")
    ports = SceneItemAttachPorts.capture(scene, item)
    assert ports.requires_authoritative_scene_bounds is True
    snapshot = SceneItemAttachSnapshot.capture(
        canvas,
        item,
        attach_ports=ports,
    )
    scene.add_extra = True
    ports.add_item(item)

    snapshot.release()

    assert scene.bounds_calls == 1
    assert scene.extra_item is not None
    assert snapshot.scene_rect_snapshot is not None
    assert snapshot.scene_rect_snapshot.tracker.known_rect.contains(
        scene.extra_item.sceneBoundingRect()
    )


def test_builtin_attach_sequence_keeps_single_item_hint_linear_path() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class CountingScene(QGraphicsScene):
        bounds_calls = 0

        def itemsBoundingRect(self) -> QRectF:
            type(self).bounds_calls += 1
            return QGraphicsScene.itemsBoundingRect(self)

    scene = CountingScene()
    scene.addRect(0.0, 0.0, 10.0, 10.0)
    canvas = SimpleNamespace(scene=lambda: scene)
    for index in range(30):
        item = QGraphicsRectItem(QRectF(float(index * 20 + 20), 0.0, 10.0, 10.0))
        item.setData(0, "shape")
        ports = SceneItemAttachPorts.capture(scene, item)
        assert ports.requires_authoritative_scene_bounds is False
        snapshot = SceneItemAttachSnapshot.capture(
            canvas,
            item,
            attach_ports=ports,
        )
        ports.add_item(item)
        snapshot.release()

    assert CountingScene.bounds_calls == 0


def test_builtin_attach_inside_existing_rect_stays_linear_with_an_actual_view() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class CountingItem(QGraphicsRectItem):
        calls = 0

        def boundingRect(self) -> QRectF:
            type(self).calls += 1
            return super().boundingRect()

    def attach_count(count: int) -> int:
        scene = QGraphicsScene()
        baseline_item = CountingItem(QRectF(0.0, 0.0, 100_000.0, 100_000.0))
        baseline_item.setData(0, "shape")
        scene.addItem(baseline_item)
        scene.sceneRect()
        view = QGraphicsView(scene)
        canvas = SimpleNamespace(scene=lambda: scene)
        CountingItem.calls = 0
        for index in range(count):
            item = CountingItem(QRectF(float(index * 2 + 10), 10.0, 1.0, 1.0))
            item.setData(0, "shape")
            ports = SceneItemAttachPorts.capture(scene, item)
            assert ports.requires_authoritative_scene_bounds is False
            snapshot = SceneItemAttachSnapshot.capture(
                canvas,
                item,
                attach_ports=ports,
            )
            ports.add_item(item)
            snapshot.release()
        calls = CountingItem.calls
        future = scene.addRect(200_000.0, 0.0, 10.0, 10.0)
        assert scene_rect_is_automatic(scene)
        assert scene.sceneRect().contains(future.sceneBoundingRect())
        view.close()
        return calls

    calls_20, calls_40, calls_80 = (attach_count(count) for count in (20, 40, 80))

    assert calls_40 <= calls_20 * 2 + 20
    assert calls_80 <= calls_40 * 2 + 20
    assert calls_80 <= 8 * 80


def test_attach_port_capture_failure_restores_preflight_item_state() -> None:
    primary = SystemExit("late attach flags capture terminated")

    class Item:
        def __init__(self) -> None:
            self.state = ["clean"]

        def scene(self):
            return None

        def data(self, role: int):
            if role == 0:
                self.state[:] = ["poisoned"]
                return "shape"
            return None

        @property
        def flags(self):
            raise primary

        def setFlags(self, _flags) -> None:
            return None

    item = Item()
    state = item.state

    with pytest.raises(SystemExit) as caught:
        SceneItemAttachPorts.capture(None, item)

    assert caught.value is primary
    assert item.state is state
    assert item.state == ["clean"]
