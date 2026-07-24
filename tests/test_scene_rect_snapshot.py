import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.ui.history_commands import (
    _capture_scene_rect_snapshot,
    _release_scene_rect_snapshot,
)
from chemvas.ui.transactions.scene_item_attach import (
    SceneItemAttachPorts,
    SceneItemAttachSnapshot,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    SceneRectStateSnapshot,
    ViewSceneRectStateSnapshot,
    scene_rect_is_automatic,
    set_explicit_scene_rect,
    set_explicit_view_scene_rect,
    view_scene_rect_is_explicit,
)
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)


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


def test_attach_snapshot_keeps_truly_sparse_fake_fallback() -> None:
    class SparseItem:
        def data(self, role: int):
            return "unknown" if role == 0 else None

    snapshot = SceneItemAttachSnapshot.capture(SimpleNamespace(), SparseItem())

    assert snapshot.scene is None
    assert snapshot.collection is None
    assert snapshot.scene_rect_snapshot is None
    snapshot.release()


def test_scene_rect_guard_keeps_truly_sparse_scene_fallback() -> None:
    assert SceneRectSnapshot.capture(SimpleNamespace()) is None
