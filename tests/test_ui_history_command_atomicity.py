from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QLineF, QObject, QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)
from ui.canvas_delete_transaction import (
    CanvasDeleteTransactionSnapshot,
    canvas_delete_transaction,
)
from ui.canvas_group_state import CanvasSceneGroup, group_state_for
from ui.canvas_history_service import CanvasHistoryService
from ui.canvas_history_state import CanvasHistoryState
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    move_atoms_for_history,
)
from ui.history_commands import (
    AddSceneItemsCommand,
    ChangeAtomLabelCommand,
    DeleteSceneItemsCommand,
    GroupSceneItemsCommand,
    MoveItemsCommand,
    UngroupSceneItemsCommand,
    UpdateSceneItemCommand,
    _restore_scene_runtime_snapshot,
    _scene_runtime_snapshot,
    _topology_depths,
)
from ui.scene_rect_snapshot import SceneRectSnapshot, set_explicit_scene_rect


class _Scene:
    def __init__(self) -> None:
        self._items: list[_SceneItem] = []
        self._signals_blocked = False

    def attach(self, item: _SceneItem) -> None:
        if item not in self._items:
            self._items.append(item)
        item._scene = self

    def detach(self, item: _SceneItem) -> None:
        if item in self._items:
            self._items.remove(item)
        item._scene = None

    def items(self) -> list[_SceneItem]:
        return list(self._items)

    def addItem(self, item: _SceneItem) -> None:
        self.attach(item)

    def removeItem(self, item: _SceneItem) -> None:
        self.detach(item)

    def blockSignals(self, blocked: bool) -> bool:
        previous = self._signals_blocked
        self._signals_blocked = blocked
        return previous

    def signalsBlocked(self) -> bool:
        return self._signals_blocked

    def selectedItems(self) -> list[_SceneItem]:
        return [item for item in self._items if item.isSelected()]


class _SceneItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self._scene: _Scene | None = None
        self.x = 0.0
        self.y = 0.0
        self._selected = False
        self._visible = True

    def scene(self) -> _Scene | None:
        return self._scene

    def parentItem(self):
        return None

    def zValue(self) -> float:
        return 0.0

    def stackBefore(self, sibling: _SceneItem) -> None:
        if self._scene is None or sibling._scene is not self._scene:
            return
        items = self._scene._items
        items.remove(self)
        items.insert(items.index(sibling) + 1, self)

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isVisible(self) -> bool:
        return self._visible

    def setVisible(self, visible: bool) -> None:
        self._visible = bool(visible)


class _RawStateSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.metadata_x = 0.0

    def pos(self) -> float:
        return self.x

    def setPos(self, position: float) -> None:
        self.x = float(position)

    def data(self, index: int):
        if index == 1:
            return {"metadata_x": self.metadata_x}
        return None

    def setData(self, index: int, value) -> None:
        if index == 1:
            self.metadata_x = float(value["metadata_x"])


class _ModelBackedSceneItem(_SceneItem):
    def __init__(self, name: str, kind: str, item_id: int) -> None:
        super().__init__(name)
        self.kind = kind
        self.item_id = item_id

    def pos(self) -> float:
        return self.x

    def setPos(self, position: float) -> None:
        self.x = float(position)

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None

    def setData(self, index: int, value) -> None:
        if index == 1:
            self.item_id = int(value)


class _VisualRectSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.rect_value = "before-rect"
        self.pen_value = "before-pen"
        self.brush_value = "before-brush"

    def data(self, index: int):
        return "note_select" if index == 0 else None

    def rect(self):
        return self.rect_value

    def setRect(self, value) -> None:
        self.rect_value = value

    def pen(self):
        return self.pen_value

    def setPen(self, value) -> None:
        self.pen_value = value

    def brush(self):
        return self.brush_value

    def setBrush(self, value) -> None:
        self.brush_value = value


class _StyledSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.pen_value = "highlight"
        self.original_pen = "normal"

    def pen(self):
        return self.pen_value

    def setPen(self, value) -> None:
        self.pen_value = value

    def data(self, index: int):
        return self.original_pen if index == 6 else None

    def setData(self, index: int, value) -> None:
        if index == 6:
            self.original_pen = value


class _Canvas:
    def __init__(self) -> None:
        self._scene = _Scene()

    def scene(self) -> _Scene:
        return self._scene


def _install_scene_runtime_state(canvas: _Canvas) -> None:
    canvas.scene_items_state = SimpleNamespace(
        selected_notes=[],
        ring_items=[],
        note_items=[],
        mark_items=[],
        arrow_items=[],
        ts_bracket_items=[],
        shape_items=[],
        orbital_items=[],
    )
    canvas.mark_registry = SimpleNamespace(by_atom={})
    canvas.handle_state = SimpleNamespace(active_handles=[], target=None)
    canvas.selection_style_state = SimpleNamespace(selected_items=[])
    canvas.selection_outline_state = SimpleNamespace(outlines=[])
    canvas.selection_info_state = SimpleNamespace(
        signature=(frozenset({1}), frozenset()),
        pending_signature=None,
        cache=("before", "selection"),
        rdkit_warmup_pending=False,
        last_interaction_time=1.0,
    )


def _restore_scene_item(canvas: _Canvas, item: _SceneItem) -> None:
    canvas.scene().attach(item)


def _remove_scene_item(canvas: _Canvas, item: _SceneItem) -> None:
    canvas.scene().detach(item)


def _persistent_outline_failure(canvas: _Canvas):
    old_outline = _SceneItem("old-outline")
    canvas.scene().attach(old_outline)
    outlines = [old_outline]
    canvas.selection_outline_state.outlines = outlines
    partial_outlines: list[_SceneItem] = []

    def refresh_then_fail(_canvas) -> None:
        for outline in list(canvas.selection_outline_state.outlines):
            canvas.scene().detach(outline)
        partial = _SceneItem(f"partial-{len(partial_outlines)}")
        partial_outlines.append(partial)
        canvas.scene().attach(partial)
        canvas.selection_outline_state.outlines = [partial]
        raise RuntimeError("persistent outline rebuild failure")

    return old_outline, outlines, partial_outlines, refresh_then_fail


def _assert_original_outline_restored(
    canvas: _Canvas,
    old_outline: _SceneItem,
    outlines: list[_SceneItem],
    partial_outlines: list[_SceneItem],
) -> None:
    assert canvas.selection_outline_state.outlines is outlines
    assert outlines == [old_outline]
    assert old_outline.scene() is canvas.scene()
    assert all(partial.scene() is None for partial in partial_outlines)


@pytest.mark.parametrize("operation", ["add", "remove"])
@pytest.mark.parametrize("failure_mode", ["raise", "false"])
def test_exact_scene_restore_reports_direct_membership_failure(
    operation: str,
    failure_mode: str,
) -> None:
    canvas = _Canvas()
    item = _SceneItem("snapshot-item")
    if operation == "add":
        canvas.scene().attach(item)
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)
    if operation == "add":
        canvas.scene().detach(item)
        method_name = "addItem"
    else:
        canvas.scene().attach(item)
        method_name = "removeItem"

    def fail_membership_change(_item):
        if failure_mode == "raise":
            raise RuntimeError(f"injected scene {operation} failure")
        return False

    setattr(canvas.scene(), method_name, fail_membership_change)
    result = snapshot.restore_with_result()

    assert not result.authoritative
    assert not result.fallback_to_inverse
    assert result.errors
    assert item.scene() is (None if operation == "add" else canvas.scene())


def test_exact_scene_snapshot_restores_all_existing_item_primitives_and_data() -> None:
    canvas = _Canvas()
    raw_item = _RawStateSceneItem("raw")
    raw_item.x = 3.0
    raw_item.metadata_x = 13.0
    visual_item = _VisualRectSceneItem("visual")
    for item in (raw_item, visual_item):
        canvas.scene().attach(item)
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)

    raw_item.x = 99.0
    raw_item.metadata_x = 199.0
    visual_item.setRect("mutated-rect")
    visual_item.setPen("mutated-pen")
    visual_item.setBrush("mutated-brush")

    result = snapshot.restore_with_result()

    assert result.authoritative
    assert (raw_item.x, raw_item.metadata_x) == (3.0, 13.0)
    assert visual_item.rect_value == "before-rect"
    assert visual_item.pen_value == "before-pen"
    assert visual_item.brush_value == "before-brush"


def test_exact_scene_snapshot_restores_ring_data_container_and_polygon_identity() -> (
    None
):
    class _RingLikeItem(_SceneItem):
        def __init__(self, atom_ids: list[int]) -> None:
            super().__init__("ring")
            self._data = {0: "ring", 2: atom_ids}
            self._polygon = [(0.0, 0.0), (20.0, 0.0), (10.0, 10.0)]

        def data(self, role: int):
            return self._data.get(role)

        def setData(self, role: int, value) -> None:
            self._data[role] = value

        def polygon(self):
            return list(self._polygon)

        def setPolygon(self, polygon) -> None:
            self._polygon = list(polygon)

    canvas = _Canvas()
    atom_ids = [7, 8, 9]
    ring = _RingLikeItem(atom_ids)
    canvas.scene().attach(ring)
    canvas.scene_items_state = SimpleNamespace(ring_items=[ring])
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)

    atom_ids[:] = [99]
    ring.setData(2, [1, 2, 3])
    ring.setPolygon([(100.0, 100.0)] * 3)
    result = snapshot.restore_with_result()

    assert result.authoritative
    assert ring.data(2) is atom_ids
    assert atom_ids == [7, 8, 9]
    assert ring.polygon() == [(0.0, 0.0), (20.0, 0.0), (10.0, 10.0)]


def test_exact_scene_snapshot_restores_auto_scene_rect_and_future_expansion() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline = scene.sceneRect()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )

    transient = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert transient.sceneBoundingRect().right() > 10_000.0
    assert scene.sceneRect() == baseline
    result = snapshot.restore_with_result()

    assert result.authoritative
    assert transient.scene() is None
    assert scene.sceneRect() == baseline

    later = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert later.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


def test_exact_scene_rect_restore_runs_after_transient_renderer_geometry() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    primitive = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    baseline = QRectF(scene.sceneRect())

    class Renderer:
        def update_bond_geometry(self, _bond_id: int) -> None:
            primitive.setRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
            # Force Qt to cache the transient far geometry while automatic
            # scene-rect tracking is active in the buggy restore order. The
            # fixed order still has the explicit guard active at this point.
            scene.sceneRect()
            raise RuntimeError("transient renderer refresh failed")

    canvas = SimpleNamespace(
        scene=lambda: scene,
        model=SimpleNamespace(bonds=[object()]),
        bond_renderer=Renderer(),
    )
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )

    result = snapshot.restore_with_result()

    assert result.authoritative
    assert any(
        "transient renderer refresh failed" in str(error) for error in result.errors
    )
    assert primitive.rect() == QRectF(0.0, 0.0, 10.0, 10.0)
    assert scene.sceneRect() == baseline

    scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 20_000.0


@pytest.mark.parametrize("failure_call", [1, 2])
@pytest.mark.parametrize("mutate_before_raise", [False, True])
def test_delete_scene_rect_restore_consumes_one_exact_retry(
    failure_call: int,
    mutate_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class Scene(QGraphicsScene):
        def __init__(self) -> None:
            super().__init__()
            self.restore_armed = False
            self.restore_calls = 0

        def setSceneRect(self, rect: QRectF) -> None:
            if self.restore_armed:
                self.restore_calls += 1
                if self.restore_calls == failure_call:
                    if mutate_before_raise:
                        QGraphicsScene.setSceneRect(self, rect)
                    raise SystemExit("delete scene rect restore terminated")
            QGraphicsScene.setSceneRect(self, rect)

    scene = Scene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    baseline = QRectF(scene.sceneRect())
    canvas = SimpleNamespace(scene=lambda: scene)
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )
    transient = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    scene.restore_armed = True
    result = snapshot.restore_with_result()

    assert result.authoritative
    assert not result.fallback_to_inverse
    assert any("scene-rect restore failed" in str(error) for error in result.errors)
    assert scene.restore_calls == (3 if failure_call == 1 else 4)
    assert transient.scene() is None
    assert snapshot.scene_rect_snapshot is not None
    assert snapshot.scene_rect_snapshot.active is False
    assert snapshot.scene_rect_snapshot.tracker.depth == 0
    assert scene.sceneRect() == baseline
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


def test_exact_scene_snapshot_release_commits_guarded_auto_scene_growth() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline = scene.sceneRect()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )

    far_item = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect() == baseline
    snapshot.release()

    assert far_item.scene() is scene
    assert scene.sceneRect().right() > 10_000.0


@pytest.mark.parametrize(
    "failure_source",
    [
        "canvas_renderer",
        "renderer_update",
        "model_bonds",
        "bond_iterator",
        "focus_setter",
        "history_notify",
    ],
)
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_exact_restore_descriptor_exit_cannot_skip_rect_last_cleanup(
    failure_source: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    injected = error_type(f"{failure_source} restore lookup terminated")

    class BrokenIterator:
        def __iter__(self):
            raise injected

    class Model:
        next_atom_id = 1
        atom_annotations: dict[int, object] = {}

        def __init__(self) -> None:
            self.atoms: dict[int, object] = {}
            self._bonds = BrokenIterator() if failure_source == "bond_iterator" else []
            self.fail_restore = False

        @property
        def bonds(self):
            if self.fail_restore and failure_source == "model_bonds":
                raise injected
            return self._bonds

        @bonds.setter
        def bonds(self, value) -> None:
            self._bonds = value

    class Renderer:
        fail_restore = False

        @property
        def update_bond_geometry(self):
            if self.fail_restore and failure_source == "renderer_update":
                raise injected
            return lambda _bond_id: None

    class Scene(QGraphicsScene):
        fail_restore = False

        @property
        def setFocusItem(self):
            if self.fail_restore and failure_source == "focus_setter":
                raise injected
            return super().setFocusItem

    renderer = Renderer()
    scene = Scene()
    original = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    baseline = QRectF(scene.sceneRect())

    class Canvas:
        fail_restore = False

        def __init__(self) -> None:
            self.model = Model()

        def scene(self):
            return scene

        @property
        def bond_renderer(self):
            if self.fail_restore and failure_source == "canvas_renderer":
                raise injected
            return renderer

    class HistoryService:
        fail_restore = False

        @property
        def notify_change(self):
            if self.fail_restore and failure_source == "history_notify":
                raise injected
            return lambda: None

    canvas = Canvas()
    history_service = HistoryService()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history_service,
        guard_scene_rect=True,
    )
    transient = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    canvas.fail_restore = True
    canvas.model.fail_restore = True
    renderer.fail_restore = True
    scene.fail_restore = True
    history_service.fail_restore = True

    result = snapshot.restore_with_result()

    if failure_source in {"focus_setter", "history_notify"}:
        # Focus and notification ports are captured before mutation begins and
        # are not looked up again during rollback.
        assert all(error is not injected for error in result.errors)
    else:
        assert any(error is injected for error in result.errors)
    # A persistently unreadable captured model authority cannot be verified,
    # even though rect-last cleanup must still complete.
    assert result.authoritative is (failure_source != "model_bonds")
    assert original.scene() is scene
    assert transient.scene() is None
    assert snapshot.scene_rect_snapshot is not None
    assert snapshot.scene_rect_snapshot.active is False
    assert snapshot.scene_rect_snapshot.tracker.depth == 0
    assert scene.sceneRect() == baseline
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 20_000.0
    scene.removeItem(future)


def test_delete_notification_mutation_is_silently_repaired_without_renotifying() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    shape = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    atom = SimpleNamespace(x=1.0, y=2.0)
    model = SimpleNamespace(atoms={1: atom}, bonds=[])
    canvas = SimpleNamespace(scene=lambda: scene, model=model)

    class History:
        calls = 0

        def notify_change(self) -> None:
            self.calls += 1
            shape.setPos(100.0, 0.0)
            atom.x = 777.0

    history = History()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history,
        guard_scene_rect=True,
    )
    shape.setPos(20.0, 0.0)
    atom.x = 50.0

    result = snapshot.restore_with_result()

    assert result.authoritative is True
    assert history.calls == 1
    assert shape.pos().x() == pytest.approx(0.0)
    assert atom.x == pytest.approx(1.0)


def test_delete_notification_waits_for_exact_model_identity_and_publishes_once() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    original_model = SimpleNamespace(atoms={}, bonds=[])
    replacement_model = SimpleNamespace(atoms={}, bonds=[])

    class Canvas:
        def __init__(self) -> None:
            self._model = original_model
            self.ignore_model_setter = False

        @property
        def model(self):
            return self._model

        @model.setter
        def model(self, value) -> None:
            if self.ignore_model_setter:
                return
            self._model = value

        def scene(self):
            return scene

    canvas = Canvas()

    class History:
        observed_models: list[object]

        def __init__(self) -> None:
            self.observed_models = []

        def notify_change(self) -> None:
            self.observed_models.append(canvas.model)

    history = History()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history,
    )
    canvas._model = replacement_model
    canvas.ignore_model_setter = True

    first = snapshot.restore_with_result()

    assert first.authoritative is False
    assert canvas.model is replacement_model
    assert history.observed_models == []
    assert snapshot.history_notification_published is False

    canvas.ignore_model_setter = False
    second = snapshot.restore_with_result()
    third = snapshot.restore_with_result()

    assert second.authoritative is True
    assert third.authoritative is True
    assert canvas.model is original_model
    assert history.observed_models == [original_model]
    assert snapshot.history_notification_published is True


def test_delete_html_authority_accepts_exact_baseline_and_rejects_mutation() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    label = QGraphicsTextItem("N")
    scene.addItem(label)
    canvas = SimpleNamespace(
        scene=lambda: scene,
        model=SimpleNamespace(atoms={}, bonds=[]),
    )
    baseline_html = label.toHtml()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )

    assert snapshot._verify_exact_authorities(include_rect=False) == []

    label.setHtml("<b>malicious</b>")
    verification_errors = snapshot._verify_exact_authorities(include_rect=False)

    assert any(
        "primitive toHtml was re-mutated" in str(error) for error in verification_errors
    )
    result = snapshot.restore_with_result()
    assert result.authoritative
    assert label.toHtml() == baseline_html


@pytest.mark.parametrize("persistent", [False, True])
def test_delete_rect_callback_cross_mutation_gets_two_silent_full_passes(
    persistent: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    shape = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    atom = SimpleNamespace(x=1.0, y=2.0)
    model = SimpleNamespace(atoms={1: atom}, bonds=[])
    canvas = SimpleNamespace(scene=lambda: scene, model=model)
    observer_calls = 0

    class History:
        calls = 0

        def notify_change(self) -> None:
            self.calls += 1

            def mutate_after_rect(_rect: QRectF) -> None:
                nonlocal observer_calls
                observer_calls += 1
                shape.setPos(100.0, 0.0)
                atom.x = 777.0
                if not persistent:
                    scene.sceneRectChanged.disconnect(mutate_after_rect)

            scene.sceneRectChanged.connect(mutate_after_rect)

    history = History()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history,
        guard_scene_rect=True,
    )
    shape.setPos(20.0, 0.0)
    atom.x = 50.0

    result = snapshot.restore_with_result()

    assert history.calls == 1
    # Publication happens only after the rect is final. A callback installed
    # by that publication therefore cannot retroactively observe a rollback
    # rect transition, regardless of whether it would disconnect itself.
    assert result.authoritative is True
    assert result.errors == ()
    assert observer_calls == 0
    assert shape.pos().x() == pytest.approx(0.0)
    assert atom.x == pytest.approx(1.0)


@pytest.mark.parametrize("persistent", [False, True])
@pytest.mark.parametrize("mutate_rect_before_raise", [False, True])
def test_delete_notify_rect_clear_failure_keeps_or_recovers_coherent_guard(
    persistent: bool,
    mutate_rect_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class Scene(QGraphicsScene):
        armed = False
        failed_once = False
        restore_calls = 0
        shape: QGraphicsRectItem
        atom: SimpleNamespace

        def setSceneRect(self, rect: QRectF) -> None:
            if self.armed:
                self.restore_calls += 1
                should_fail = rect.isNull() and (persistent or not self.failed_once)
                if should_fail:
                    self.failed_once = True
                    if mutate_rect_before_raise:
                        QGraphicsScene.setSceneRect(self, rect)
                    self.shape.setPos(100.0, 0.0)
                    self.atom.x = 777.0
                    raise SystemExit("automatic rect clear terminated")
            QGraphicsScene.setSceneRect(self, rect)

    scene = Scene()
    shape = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    atom = SimpleNamespace(x=1.0, y=2.0)
    scene.shape = shape
    scene.atom = atom
    canvas = SimpleNamespace(
        scene=lambda: scene,
        model=SimpleNamespace(atoms={1: atom}, bonds=[]),
    )

    class History:
        calls = 0

        def notify_change(self) -> None:
            self.calls += 1
            scene.armed = True

    history = History()
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history,
        guard_scene_rect=True,
    )
    shape.setPos(20.0, 0.0)
    atom.x = 50.0

    result = snapshot.restore_with_result()

    assert history.calls == 1
    assert result.authoritative is True
    assert not any(
        "automatic rect clear terminated" in str(error) for error in result.errors
    )
    assert shape.pos().x() == pytest.approx(0.0)
    assert atom.x == pytest.approx(1.0)
    assert snapshot.scene_rect_snapshot is not None
    rect_snapshot = snapshot.scene_rect_snapshot
    # The observer is armed after rect finality, so rollback performs no later
    # setSceneRect call and cannot hit the injected failure at all.
    assert scene.restore_calls == 0
    assert not rect_snapshot.active
    assert rect_snapshot.tracker.depth == 0
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


@pytest.mark.parametrize(
    "failure_source",
    [
        "scene_items",
        "scene_block_signals",
        "item_parent",
        "item_scene",
        "item_stack",
        "item_set_selected",
        "selection_set_pen",
        "visibility_set_visible",
        "item_set_data",
        "primitive_set_line",
    ],
)
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_strict_runtime_restore_lookup_exit_is_critical_and_continues_rect_last(
    failure_source: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    injected = error_type(f"{failure_source} restore lookup terminated")

    class FailOnceMixin:
        fail_restore = False
        failed_restore = False

        def _restore_getter(self, name: str, getter):
            if self.fail_restore and not self.failed_restore and failure_source == name:
                self.failed_restore = True
                raise injected
            return getter

    class Scene(FailOnceMixin, QGraphicsScene):
        @property
        def items(self):
            return self._restore_getter("scene_items", super().items)

        @property
        def blockSignals(self):
            return self._restore_getter(
                "scene_block_signals",
                super().blockSignals,
            )

    class Item(FailOnceMixin, QGraphicsRectItem):
        @property
        def parentItem(self):
            return self._restore_getter("item_parent", super().parentItem)

        @property
        def scene(self):
            return self._restore_getter("item_scene", super().scene)

        @property
        def stackBefore(self):
            return self._restore_getter("item_stack", super().stackBefore)

        @property
        def setSelected(self):
            return self._restore_getter(
                "item_set_selected",
                super().setSelected,
            )

        @property
        def setPen(self):
            return self._restore_getter(
                "selection_set_pen",
                super().setPen,
            )

        @property
        def setVisible(self):
            return self._restore_getter(
                "visibility_set_visible",
                super().setVisible,
            )

        @property
        def setData(self):
            return self._restore_getter("item_set_data", super().setData)

    class Line(FailOnceMixin, QGraphicsLineItem):
        @property
        def setLine(self):
            return self._restore_getter(
                "primitive_set_line",
                super().setLine,
            )

    scene = Scene()
    item = Item(QRectF(0.0, 0.0, 10.0, 10.0))
    stable = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    line = Line(QLineF(0.0, 20.0, 10.0, 20.0))
    item.setData(0, "note_box")
    scene.addItem(item)
    scene.addItem(stable)
    scene.addItem(line)
    item.setSelected(True)
    baseline = QRectF(scene.sceneRect())
    canvas = SimpleNamespace(
        scene=lambda: scene,
        selection_style_state=SimpleNamespace(selected_items=[item]),
    )
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )

    stable.setRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    item.setSelected(False)
    item.setVisible(False)
    item.setData(0, "mutated")
    line.setLine(QLineF(20_000.0, 20.0, 20_010.0, 20.0))
    scene.fail_restore = True
    item.fail_restore = True
    line.fail_restore = True

    result = snapshot.restore_with_result()

    if failure_source in {
        "scene_items",
        "scene_block_signals",
        "item_parent",
        "item_scene",
        "item_set_selected",
        "item_stack",
    }:
        # Scene items, signal, and selection ports are captured before
        # mutation. Stacking is retried after its first transient lookup
        # failure and verified by the final full ordered-identity read.
        assert result.authoritative
        assert all(error is not injected for error in result.errors)
    else:
        assert not result.authoritative
        assert any(error is injected for error in result.errors)
    assert stable.rect() == QRectF(20.0, 0.0, 10.0, 10.0)
    assert line.line() == QLineF(0.0, 20.0, 10.0, 20.0)
    assert snapshot.scene_rect_snapshot is not None
    assert snapshot.scene_rect_snapshot.active is False
    assert snapshot.scene_rect_snapshot.tracker.depth == 0
    assert scene.sceneRect() == baseline


def test_atom_primitive_capture_exit_precedes_auto_scene_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)

    with (
        mock.patch(
            "ui.canvas_delete_transaction._atom_primitive_graphics_snapshots",
            side_effect=SystemExit("atom primitive capture terminated"),
        ),
        pytest.raises(SystemExit, match="atom primitive capture terminated"),
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_delete_object_live_property_attribute_error_aborts_exact_capture() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))

    class BrokenModel:
        bonds: list[object] = []
        next_atom_id = 1
        atom_annotations: dict[int, object] = {}

        @property
        def atoms(self):
            raise AttributeError("live atoms property failed internally")

    canvas = SimpleNamespace(scene=lambda: scene, model=BrokenModel())

    with pytest.raises(
        AttributeError,
        match="live atoms property failed internally",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0


@pytest.mark.parametrize(
    ("collection_name", "leaf_attribute"),
    [("atoms", "x"), ("bonds", "order")],
)
def test_exact_delete_snapshot_reuses_model_collections_for_nested_leaves(
    collection_name: str,
    leaf_attribute: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    leaf = SimpleNamespace(**{leaf_attribute: 1})

    class FlakyModel:
        next_atom_id = 2
        atom_annotations: dict[int, object] = {}

        def __init__(self) -> None:
            self._atoms = {1: leaf} if collection_name == "atoms" else {}
            self._bonds = [leaf] if collection_name == "bonds" else []
            self.reads = {"atoms": 0, "bonds": 0}

        def _read(self, name: str, value):
            self.reads[name] += 1
            if name == collection_name and self.reads[name] == 2:
                raise AttributeError(f"{name} failed on a duplicate read")
            return value

        @property
        def atoms(self):
            return self._read("atoms", self._atoms)

        @atoms.setter
        def atoms(self, value) -> None:
            self._atoms = value

        @property
        def bonds(self):
            return self._read("bonds", self._bonds)

        @bonds.setter
        def bonds(self, value) -> None:
            self._bonds = value

    model = FlakyModel()
    canvas = SimpleNamespace(scene=lambda: scene, model=model)
    primary = RuntimeError(f"{collection_name} mutation failed")

    with pytest.raises(RuntimeError) as caught:
        with canvas_delete_transaction(canvas):
            setattr(leaf, leaf_attribute, 99)
            raise primary

    assert caught.value is primary
    assert getattr(leaf, leaf_attribute) == 1
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is not None
    assert tracker.depth == 0
    future = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize("state_source", ["groups", "registered_ring_items"])
def test_exact_delete_snapshot_reuses_runtime_collections_for_nested_leaves(
    state_source: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)

    if state_source == "groups":
        leaf = SimpleNamespace(value="before")

        class FlakyGroupState:
            def __init__(self) -> None:
                self.groups = {7: leaf}
                self.reads = 0

            def __getattribute__(self, name: str):
                if name == "groups":
                    reads = object.__getattribute__(self, "reads") + 1
                    object.__setattr__(self, "reads", reads)
                    if reads == 2:
                        raise AttributeError("groups failed on a duplicate read")
                return object.__getattribute__(self, name)

        canvas.group_state = FlakyGroupState()
    else:
        leaf = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))

        class FlakySceneItemsState:
            def __init__(self) -> None:
                self.ring_items = [leaf]
                self.selected_notes: list[object] = []
                self.note_items: list[object] = []
                self.mark_items: list[object] = []
                self.arrow_items: list[object] = []
                self.ts_bracket_items: list[object] = []
                self.shape_items: list[object] = []
                self.orbital_items: list[object] = []
                self.reads = 0

            def __getattribute__(self, name: str):
                if name == "ring_items":
                    reads = object.__getattribute__(self, "reads") + 1
                    object.__setattr__(self, "reads", reads)
                    if reads == 3:
                        raise AttributeError("ring_items failed on a duplicate read")
                return object.__getattribute__(self, name)

        canvas.scene_items_state = FlakySceneItemsState()

    primary = RuntimeError(f"{state_source} mutation failed")
    with pytest.raises(RuntimeError) as caught:
        with canvas_delete_transaction(canvas):
            if state_source == "groups":
                leaf.value = "mutated"
            else:
                leaf.setRect(QRectF(100.0, 100.0, 20.0, 20.0))
            raise primary

    assert caught.value is primary
    if state_source == "groups":
        assert leaf.value == "before"
    else:
        assert leaf.rect() == QRectF(0.0, 0.0, 10.0, 10.0)
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is not None
    assert tracker.depth == 0


def test_delete_canvas_model_property_without_raw_authority_fails_closed_before_scene_guard() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))

    class BrokenCanvas:
        def scene(self):
            return scene

        @property
        def model(self):
            raise AttributeError("canvas model capture failed internally")

    with pytest.raises(
        RuntimeError,
        match="callback-free canvas model authority",
    ):
        CanvasDeleteTransactionSnapshot.capture(
            BrokenCanvas(),
            guard_scene_rect=True,
        )

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    future = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize(
    "state_source",
    [
        "primitive",
        "selection_info",
        "scene_items",
        "mark_registry",
        "atom_graphics",
        "runtime_root",
        "runtime_nested_root",
        "canvas_state_root",
    ],
)
def test_runtime_live_property_attribute_error_aborts_before_scene_guard(
    state_source: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)

    if state_source == "primitive":

        class BrokenPrimitive(QGraphicsRectItem):
            @property
            def _hit_padding(self):
                raise AttributeError("primitive direct attribute failed internally")

        primitive = BrokenPrimitive(QRectF(0.0, 0.0, 5.0, 5.0))
        scene.addItem(primitive)
        expected = "primitive direct attribute failed internally"
    elif state_source == "selection_info":

        class BrokenSelectionInfo:
            @property
            def signature(self):
                raise AttributeError("selection info attribute failed internally")

        canvas.selection_info_state = BrokenSelectionInfo()
        expected = "selection info attribute failed internally"
    elif state_source == "scene_items":

        class BrokenSceneItems:
            @property
            def note_items(self):
                raise AttributeError("scene item list failed internally")

        canvas.scene_items_state = BrokenSceneItems()
        expected = "scene item list failed internally"
    elif state_source == "mark_registry":

        class BrokenMarkRegistry:
            @property
            def by_atom(self):
                raise AttributeError("mark registry mapping failed internally")

        canvas.mark_registry = BrokenMarkRegistry()
        expected = "mark registry mapping failed internally"
    elif state_source == "atom_graphics":

        class BrokenAtomGraphics:
            @property
            def atom_items(self):
                raise AttributeError("atom graphics mapping failed internally")

        canvas.atom_graphics_state = BrokenAtomGraphics()
        expected = "atom graphics mapping failed internally"
    elif state_source == "runtime_root":

        class BrokenCanvas:
            def scene(self):
                return scene

            @property
            def runtime_state(self):
                raise AttributeError("canvas runtime root failed internally")

        canvas = BrokenCanvas()
        expected = "canvas runtime root failed internally"
    elif state_source == "runtime_nested_root":

        class BrokenRuntimeState:
            @property
            def graph_state(self):
                raise AttributeError("nested runtime root failed internally")

        canvas.runtime_state = BrokenRuntimeState()
        expected = "nested runtime root failed internally"
    else:

        class BrokenCanvas:
            def scene(self):
                return scene

            @property
            def graph_state(self):
                raise AttributeError("canvas state root failed internally")

        canvas = BrokenCanvas()
        expected = "canvas state root failed internally"

    with pytest.raises(AttributeError, match=expected):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    future = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


def test_renderer_style_exit_precedes_wrapped_auto_scene_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))

    class Renderer:
        @property
        def style(self):
            raise SystemExit("renderer style capture terminated")

    canvas = SimpleNamespace(scene=lambda: scene, renderer=Renderer())
    with pytest.raises(SystemExit, match="renderer style capture terminated"):
        capture_history_transaction_for_history(canvas)

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


@pytest.mark.parametrize("capture_root", ["renderer", "style"])
def test_renderer_property_attribute_error_precedes_wrapped_scene_guard(
    capture_root: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))

    class BrokenRenderer:
        @property
        def style(self):
            raise AttributeError("renderer style capture failed internally")

    class Canvas:
        def scene(self):
            return scene

        @property
        def renderer(self):
            if capture_root == "renderer":
                raise AttributeError("canvas renderer capture failed internally")
            return BrokenRenderer()

    expected = (
        "canvas renderer capture failed internally"
        if capture_root == "renderer"
        else "renderer style capture failed internally"
    )
    with pytest.raises(AttributeError, match=expected):
        capture_history_transaction_for_history(Canvas())

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    future = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(future)


@pytest.mark.parametrize(
    ("getter_name", "error_type"),
    [("data", KeyboardInterrupt), ("pos", SystemExit)],
)
def test_exact_item_getter_control_flow_aborts_before_mutation_and_guard(
    getter_name: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class InterruptingItem(QGraphicsRectItem):
        def data(self, role: int):
            if getter_name == "data":
                raise error_type("item data capture terminated")
            return super().data(role)

        def pos(self):
            if getter_name == "pos":
                raise error_type("item pos capture terminated")
            return super().pos()

    item = InterruptingItem(QRectF(0.0, 0.0, 10.0, 10.0))
    scene.addItem(item)
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(error_type, match=f"item {getter_name} capture terminated"):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    assert item.scene() is scene
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    scene.removeItem(item)
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_move_atoms_getter_exit_precedes_command_transaction_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)

    def restore_transaction(_canvas, snapshot, _error):
        snapshot.restore()
        return SimpleNamespace(errors=(), authoritative=True)

    with (
        mock.patch(
            "ui.history_canvas_access.atom_for_id",
            side_effect=SystemExit("atom state capture terminated"),
        ),
        mock.patch(
            "ui.history_canvas_access._capture_history_transaction_for_command",
            side_effect=lambda _canvas: SceneRectSnapshot.capture(scene),
        ) as capture,
        mock.patch(
            "ui.history_canvas_access._restore_history_transaction_for_command",
            side_effect=restore_transaction,
        ),
        pytest.raises(SystemExit, match="atom state capture terminated"),
    ):
        move_atoms_for_history(canvas, {7}, 1.0, 2.0)

    # The command-wide transaction is deliberately captured before live atom
    # preflight so a side-effecting getter is still rolled back absolutely.
    capture.assert_called_once_with(canvas)
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_move_item_snapshot_exit_restores_command_transaction_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    command = MoveItemsCommand([item], 1.0, 2.0)

    def restore_transaction(_canvas, snapshot, _error):
        snapshot.restore()
        return SimpleNamespace(errors=(), authoritative=True)

    with (
        mock.patch(
            "ui.history_commands._move_item_snapshot",
            side_effect=SystemExit("move item snapshot terminated"),
        ),
        mock.patch(
            "ui.history_commands.capture_history_transaction_for_command",
            side_effect=lambda _canvas: SceneRectSnapshot.capture(scene),
        ) as capture,
        mock.patch(
            "ui.history_commands.restore_history_transaction_for_command",
            side_effect=restore_transaction,
        ) as restore,
        pytest.raises(SystemExit, match="move item snapshot terminated"),
    ):
        command.redo(canvas)

    capture.assert_called_once_with(canvas)
    restore.assert_called_once()
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_strict_exact_capture_propagates_live_scene_items_failure() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    class FailOnceItemsScene(QGraphicsScene):
        fail_once = True

        def items(self, *args, **kwargs):
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("live scene items capture failed")
            return super().items(*args, **kwargs)

    scene = FailOnceItemsScene()
    original = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(RuntimeError, match="live scene items capture failed"):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    assert original.scene() is scene
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_strict_exact_capture_propagates_scene_property_attribute_error() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    original = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))

    class FlakyCanvas:
        calls = 0

        @property
        def scene(self):
            self.calls += 1
            if self.calls == 1:
                raise AttributeError("canvas scene property failed internally")
            return lambda: scene

    canvas = FlakyCanvas()
    with pytest.raises(
        AttributeError,
        match="canvas scene property failed internally",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    assert original.scene() is scene
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    assert canvas.calls == 0
    canvas.calls = 1
    assert canvas.scene() is scene
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


def test_delete_non_qt_items_capture_failure_restores_pre_items_raw_graph() -> (
    None
):
    primary = SystemExit("later delete scene capture terminated")

    class Item:
        def __init__(self) -> None:
            self.value = "clean"

    item = Item()

    class Scene:
        def __init__(self) -> None:
            self.backing_items = [item]
            self.state = ["clean"]
            self.blocked = False

        def items(self):
            self.state[:] = ["poisoned"]
            item.value = "poisoned"
            canvas.backing[:] = ["poisoned"]
            return []

        def addItem(self, _item) -> None:
            return None

        def removeItem(self, _item) -> None:
            return None

        def blockSignals(self, blocked: bool) -> bool:
            previous = self.blocked
            self.blocked = blocked
            return previous

        def signalsBlocked(self) -> bool:
            return self.blocked

        def selectedItems(self) -> list:
            return []

        @property
        def focusItem(self):
            raise primary

        def setFocusItem(self, _item) -> None:
            return None

        def sceneRect(self) -> QRectF:
            return QRectF(0.0, 0.0, 10.0, 10.0)

        def setSceneRect(self, _rect) -> None:
            return None

        def itemsBoundingRect(self) -> QRectF:
            return QRectF()

    scene = Scene()

    class Canvas:
        def __init__(self) -> None:
            self.model = SimpleNamespace(
                next_atom_id=1,
                atom_annotations={},
                atoms={},
                bonds=[],
            )
            self._scene = scene
            self.backing = ["clean"]

        @property
        def scene(self):
            self.backing[:] = ["scene getter poisoned"]
            return lambda: self._scene

    canvas = Canvas()
    scene_items = scene.backing_items
    scene_state = scene.state
    canvas_backing = canvas.backing

    with pytest.raises(SystemExit) as caught:
        CanvasDeleteTransactionSnapshot.capture(canvas)

    assert caught.value is primary
    assert scene.backing_items is scene_items
    assert scene.backing_items == [item]
    assert scene.state is scene_state
    assert scene.state == ["clean"]
    assert item.value == "clean"
    assert canvas.backing is canvas_backing
    assert canvas.backing == ["clean"]


def test_strict_exact_capture_rejects_complete_scene_contract_without_items() -> None:
    class IncompleteLiveScene:
        def addItem(self, _item) -> None:
            return None

        def removeItem(self, _item) -> None:
            return None

        def blockSignals(self, _blocked: bool) -> bool:
            return False

        def signalsBlocked(self) -> bool:
            return False

        def selectedItems(self) -> list:
            return []

        def focusItem(self):
            return None

        def setFocusItem(self, _item) -> None:
            return None

    canvas = SimpleNamespace(scene=lambda: IncompleteLiveScene())

    with pytest.raises(
        RuntimeError,
        match="live scene does not expose an items snapshot",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas)


def test_strict_exact_capture_rejects_qobject_scene_without_items() -> None:
    canvas = SimpleNamespace(scene=lambda: QObject())

    with pytest.raises(
        RuntimeError,
        match="live scene does not expose an items snapshot",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas)


def test_strict_exact_capture_tolerates_lightweight_scene_sentinel() -> None:
    sentinel = SimpleNamespace(addItem=lambda _item: None)
    canvas = SimpleNamespace(scene=lambda: sentinel)

    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)
    result = snapshot.restore_with_result()

    assert result.authoritative


@pytest.mark.parametrize("getter_name", ["data", "pen"])
def test_strict_exact_capture_propagates_live_item_runtime_error(
    getter_name: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class BrokenLiveItem(QGraphicsRectItem):
        def data(self, role: int):
            if getter_name == "data":
                raise RuntimeError("live item data capture failed")
            return super().data(role)

        def pen(self):
            if getter_name == "pen":
                raise RuntimeError("live item pen capture failed")
            return super().pen()

    item = BrokenLiveItem(QRectF(0.0, 0.0, 10.0, 10.0))
    scene.addItem(item)
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(RuntimeError, match=f"live item {getter_name} capture failed"):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    assert item.scene() is scene
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0


@pytest.mark.parametrize(
    "getter_name",
    ["data", "pen", "isSelected", "setSelected", "isVisible", "childItems"],
)
def test_strict_exact_capture_propagates_live_item_descriptor_attribute_error(
    getter_name: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()

    class BrokenLiveItem(QGraphicsRectItem):
        def _live_getter(self, name: str, getter):
            if getter_name == name:
                raise AttributeError(f"live item {name} descriptor failed internally")
            return getter

        @property
        def data(self):
            return self._live_getter("data", super().data)

        @property
        def pen(self):
            return self._live_getter("pen", super().pen)

        @property
        def isSelected(self):
            return self._live_getter("isSelected", super().isSelected)

        @property
        def setSelected(self):
            return self._live_getter("setSelected", super().setSelected)

        @property
        def isVisible(self):
            return self._live_getter("isVisible", super().isVisible)

        @property
        def childItems(self):
            return self._live_getter("childItems", super().childItems)

    item = BrokenLiveItem(QRectF(0.0, 0.0, 10.0, 10.0))
    item.setData(0, "note_box")
    scene.addItem(item)
    canvas = SimpleNamespace(
        scene=lambda: scene,
        selection_style_state=SimpleNamespace(selected_items=[item]),
    )

    with pytest.raises(
        AttributeError,
        match=f"live item {getter_name} descriptor failed internally",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    assert item.scene() is scene
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0


@pytest.mark.parametrize(
    "getter_name",
    ["items", "signalsBlocked", "blockSignals"],
)
def test_strict_exact_capture_propagates_live_scene_descriptor_attribute_error(
    getter_name: str,
) -> None:
    class BrokenLiveScene:
        def _live_getter(self, name: str, getter):
            if getter_name == name:
                raise AttributeError(f"live scene {name} descriptor failed internally")
            return getter

        @property
        def items(self):
            return self._live_getter("items", lambda: [])

        @property
        def signalsBlocked(self):
            return self._live_getter("signalsBlocked", lambda: False)

        def addItem(self, _item) -> None:
            return None

        def removeItem(self, _item) -> None:
            return None

        @property
        def blockSignals(self):
            return self._live_getter(
                "blockSignals",
                lambda _blocked: False,
            )

        def selectedItems(self) -> list:
            return []

        def focusItem(self):
            return None

        def setFocusItem(self, _item) -> None:
            return None

    scene = BrokenLiveScene()
    canvas = SimpleNamespace(scene=lambda: scene)

    with pytest.raises(
        AttributeError,
        match=f"live scene {getter_name} descriptor failed internally",
    ):
        CanvasDeleteTransactionSnapshot.capture(canvas, guard_scene_rect=True)

    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0


def test_strict_exact_capture_skips_a_deleted_qt_wrapper() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    deleted_item = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    sip.delete(deleted_item)
    canvas = SimpleNamespace(
        scene=lambda: scene,
        atom_graphics_state=SimpleNamespace(
            atom_items={7: deleted_item},
            atom_dots={},
        ),
    )

    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        guard_scene_rect=True,
    )
    snapshot.release()

    assert snapshot.scene_rect_snapshot is not None
    assert snapshot.scene_rect_snapshot.active is False
    assert snapshot.scene_rect_snapshot.tracker.depth == 0


def test_exact_runtime_visibility_failure_is_non_authoritative() -> None:
    canvas = _Canvas()
    item = _VisualRectSceneItem("visibility")
    canvas.scene().attach(item)
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)
    item._visible = False

    def fail_visibility(_visible: bool) -> None:
        raise RuntimeError("visibility restore failed")

    item.setVisible = fail_visibility
    result = snapshot.restore_with_result()

    assert not result.authoritative
    assert not result.fallback_to_inverse
    assert any("visibility restore failed" in str(error) for error in result.errors)
    assert item.isVisible() is False


def test_exact_runtime_collector_reports_list_mark_and_selection_info_failures() -> (
    None
):
    class ListState:
        def __init__(self) -> None:
            self._note_items = ["before"]
            self.fail = False

        @property
        def note_items(self):
            return self._note_items

        @note_items.setter
        def note_items(self, value) -> None:
            if self.fail:
                raise RuntimeError("list owner restore failed")
            self._note_items = value

    class MarkRegistry:
        def __init__(self) -> None:
            self._by_atom = {7: ["before"]}
            self.fail = False

        @property
        def by_atom(self):
            return self._by_atom

        @by_atom.setter
        def by_atom(self, value) -> None:
            if self.fail:
                raise RuntimeError("mark registry restore failed")
            self._by_atom = value

    class SelectionInfo:
        def __init__(self) -> None:
            self.fail = False
            self.signature = "before"
            self.pending_signature = None
            self.cache = ("before", "selection")
            self.rdkit_warmup_pending = False
            self.last_interaction_time = 1.0

        def __setattr__(self, name, value) -> None:
            if name == "signature" and getattr(self, "fail", False):
                raise RuntimeError("selection info restore failed")
            object.__setattr__(self, name, value)

    canvas = _Canvas()
    list_state = ListState()
    registry = MarkRegistry()
    selection_info = SelectionInfo()
    canvas.scene_items_state = list_state
    canvas.mark_registry = registry
    canvas.selection_info_state = selection_info
    snapshot = _scene_runtime_snapshot(canvas, strict=True)

    list_state.note_items.append("mutated")
    registry.by_atom[7].append("mutated")
    selection_info.signature = "mutated"
    list_state.fail = True
    registry.fail = True
    selection_info.fail = True
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert len(errors) >= 3
    assert any("list owner restore failed" in str(error) for error in errors)
    assert any("mark registry restore failed" in str(error) for error in errors)
    assert any("selection info restore failed" in str(error) for error in errors)
    assert list_state.note_items == ["before"]
    assert registry.by_atom == {7: ["before"]}


def test_exact_runtime_restore_preserves_preblocked_scene_signal_state() -> None:
    canvas = _Canvas()
    canvas.scene().blockSignals(True)
    snapshot = _scene_runtime_snapshot(canvas, strict=True)
    canvas.scene().blockSignals(False)

    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert canvas.scene().signalsBlocked() is True


def test_history_topology_depths_scale_linearly_for_1k_2k_4k_chains() -> None:
    for size in (1_000, 2_000, 4_000):
        parent_reads = 0

        class CountingTopologyState:
            def __init__(self, item: object, parent: object | None) -> None:
                self.item = item
                self._parent = parent

            @property
            def parent(self) -> object | None:
                nonlocal parent_reads
                parent_reads += 1
                return self._parent

        items = [object() for _index in range(size)]
        states = [
            CountingTopologyState(
                item,
                items[index - 1] if index else None,
            )
            for index, item in enumerate(items)
        ]

        depths = _topology_depths(list(reversed(states)))

        assert depths[id(items[0])] == 0
        assert depths[id(items[-1])] == size - 1
        assert parent_reads == size

    first = object()
    second = object()
    cycle_states = [
        CountingTopologyState(first, second),
        CountingTopologyState(second, first),
    ]
    with pytest.raises(RuntimeError, match="parent cycle"):
        _topology_depths(cycle_states)


@pytest.mark.parametrize("restore_path", ["runtime", "delete", "move_history"])
def test_actual_qt_runtime_consumers_restore_parent_topology_and_z_value(
    restore_path: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    parent = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    child = QGraphicsRectItem(QRectF(1.0, 1.0, 2.0, 2.0))
    peer = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    for item in (parent, child, peer):
        scene.addItem(item)
    child.setParentItem(parent)
    parent.setZValue(2.0)
    child.setZValue(3.0)
    peer.setZValue(2.0)
    expected_order = list(scene.items())
    canvas = SimpleNamespace(scene=lambda: scene)

    def corrupt_topology_and_z() -> None:
        child.setParentItem(peer)
        parent.setZValue(9.0)
        child.setZValue(-4.0)
        peer.setZValue(-2.0)

    if restore_path == "runtime":
        snapshot = _scene_runtime_snapshot(canvas, strict=True)
        corrupt_topology_and_z()
        assert _restore_scene_runtime_snapshot(snapshot, collect_errors=True) == []
    elif restore_path == "delete":
        snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)
        corrupt_topology_and_z()
        result = snapshot.restore_with_result()
        assert result.authoritative
        assert result.errors == ()
    else:

        def fail_move(*_args, **_kwargs) -> None:
            corrupt_topology_and_z()
            raise RuntimeError("move damaged scene topology")

        with (
            mock.patch("ui.history_commands.move_item_for", side_effect=fail_move),
            pytest.raises(RuntimeError, match="move damaged scene topology"),
        ):
            MoveItemsCommand([child], 4.0, 5.0).redo(canvas)

    assert child.parentItem() is parent
    assert parent.zValue() == 2.0
    assert child.zValue() == 3.0
    assert peer.zValue() == 2.0
    assert list(scene.items()) == expected_order


def test_actual_qt_topology_restore_uses_qt_base_item_ports() -> None:
    class BoundTopologyItem(QGraphicsRectItem):
        topology_port_lookup_blocked = False
        parent_getter_reads = 0
        parent_setter_reads = 0
        z_getter_reads = 0
        z_setter_reads = 0

        def _check_lookup(self, name: str) -> None:
            if self.topology_port_lookup_blocked:
                raise SystemExit(f"{name} was looked up after capture")

        @property
        def parentItem(self):
            self.parent_getter_reads += 1
            self._check_lookup("parentItem")
            return lambda: QGraphicsItem.parentItem(self)

        @property
        def setParentItem(self):
            self.parent_setter_reads += 1
            self._check_lookup("setParentItem")
            return lambda parent: QGraphicsItem.setParentItem(self, parent)

        @property
        def zValue(self):
            self.z_getter_reads += 1
            self._check_lookup("zValue")
            return lambda: QGraphicsItem.zValue(self)

        @property
        def setZValue(self):
            self.z_setter_reads += 1
            self._check_lookup("setZValue")
            return lambda value: QGraphicsItem.setZValue(self, value)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    parent = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    child = BoundTopologyItem(QRectF(1.0, 1.0, 2.0, 2.0))
    peer = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    for item in (parent, child, peer):
        scene.addItem(item)
    QGraphicsItem.setParentItem(child, parent)
    QGraphicsItem.setZValue(child, 3.0)
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )

    QGraphicsItem.setParentItem(child, peer)
    QGraphicsItem.setZValue(child, -4.0)
    child.topology_port_lookup_blocked = True
    assert _restore_scene_runtime_snapshot(snapshot, collect_errors=True) == []

    assert QGraphicsItem.parentItem(child) is parent
    assert QGraphicsItem.zValue(child) == 3.0
    assert child.parent_getter_reads == 0
    assert child.parent_setter_reads == 0
    assert child.z_getter_reads == 0
    assert child.z_setter_reads == 0


def test_actual_qt_sibling_restore_uses_qt_base_stack_port() -> None:
    class BoundStackItem(QGraphicsRectItem):
        block_stack_lookup = False
        stack_reads = 0

        @property
        def stackBefore(self):
            self.stack_reads += 1
            if self.block_stack_lookup:
                raise SystemExit("stackBefore was looked up after capture")
            return lambda sibling: QGraphicsItem.stackBefore(self, sibling)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    lower = BoundStackItem(QRectF(0.0, 0.0, 10.0, 10.0))
    higher = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    scene.addItem(lower)
    scene.addItem(higher)
    expected_order = list(scene.items())
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )

    QGraphicsItem.stackBefore(higher, lower)
    lower.block_stack_lookup = True
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert list(scene.items()) == expected_order
    assert lower.stack_reads == 0


def test_actual_qt_selection_callback_cannot_repollute_restored_z_value() -> None:
    class CrossMutatingItem(QGraphicsRectItem):
        armed = False

        def setSelected(self, selected: bool) -> None:
            QGraphicsItem.setSelected(self, selected)
            if self.armed:
                QGraphicsItem.setZValue(self, 99.0)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = CrossMutatingItem(QRectF(0.0, 0.0, 10.0, 10.0))
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(item)
    QGraphicsItem.setZValue(item, 3.0)
    QGraphicsItem.setSelected(item, True)
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )

    QGraphicsItem.setSelected(item, False)
    QGraphicsItem.setZValue(item, -4.0)
    item.armed = True
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert item.isSelected()
    assert item.zValue() == 3.0


def test_actual_qt_selected_restore_cannot_leave_captured_false_peer_selected() -> (
    None
):
    class SelectingPeerItem(QGraphicsRectItem):
        def __init__(self, rect: QRectF) -> None:
            super().__init__(rect)
            self.armed = False
            self.peer: QGraphicsItem | None = None
            self.callback_calls = 0

        def setSelected(self, selected: bool) -> None:
            QGraphicsItem.setSelected(self, selected)
            if self.armed and selected and self.peer is not None:
                self.callback_calls += 1
                QGraphicsItem.setSelected(self.peer, True)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    selected = SelectingPeerItem(QRectF(0.0, 0.0, 10.0, 10.0))
    unselected_peer = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    for item in (selected, unselected_peer):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
    QGraphicsItem.setSelected(selected, True)
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )
    assert [state.item for state in snapshot.selected_states] == [
        unselected_peer,
        selected,
    ]

    QGraphicsItem.setSelected(selected, False)
    selected.peer = unselected_peer
    selected.armed = True
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert selected.isSelected()
    assert not unselected_peer.isSelected()
    assert selected.callback_calls == 1


@pytest.mark.parametrize("restore_target", ["parent", "z"])
@pytest.mark.parametrize("persistent", [False, True])
def test_actual_qt_topology_restore_bypasses_subclass_setter_overrides(
    restore_target: str,
    persistent: bool,
) -> None:
    class RetryTopologyItem(QGraphicsRectItem):
        remaining_no_ops = 0
        parent_restore_calls = 0
        z_restore_calls = 0

        def setParentItem(self, parent) -> None:
            self.parent_restore_calls += 1
            if restore_target == "parent" and self.remaining_no_ops:
                self.remaining_no_ops -= 1
                return
            QGraphicsItem.setParentItem(self, parent)

        def setZValue(self, value: float) -> None:
            self.z_restore_calls += 1
            if restore_target == "z" and self.remaining_no_ops:
                self.remaining_no_ops -= 1
                return
            QGraphicsItem.setZValue(self, value)

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    parent = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    child = RetryTopologyItem(QRectF(1.0, 1.0, 2.0, 2.0))
    peer = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    for item in (parent, child, peer):
        scene.addItem(item)
    QGraphicsItem.setParentItem(child, parent)
    QGraphicsItem.setZValue(child, 3.0)
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )

    if restore_target == "parent":
        QGraphicsItem.setParentItem(child, peer)
    else:
        QGraphicsItem.setZValue(child, -4.0)
    child.remaining_no_ops = 99 if persistent else 1
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    restore_calls = (
        child.parent_restore_calls
        if restore_target == "parent"
        else child.z_restore_calls
    )
    assert restore_calls == 0
    assert errors == []
    assert QGraphicsItem.parentItem(child) is parent
    assert QGraphicsItem.zValue(child) == 3.0


def test_exact_runtime_signal_restore_uses_captured_ports_and_retries_once() -> None:
    class SignalScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self.signal_getter_reads = 0
            self.signal_setter_reads = 0
            self.signal_getter_calls = 0
            self.signal_setter_calls = 0
            self.fail_port_lookup = False
            self.fail_next_signal_set = False

        @property
        def signalsBlocked(self):
            self.signal_getter_reads += 1
            if self.fail_port_lookup:
                raise SystemExit("signal getter port was looked up after capture")
            return self._signals_blocked_value

        def _signals_blocked_value(self) -> bool:
            self.signal_getter_calls += 1
            return self._signals_blocked

        @property
        def blockSignals(self):
            self.signal_setter_reads += 1
            if self.fail_port_lookup:
                raise SystemExit("signal setter port was looked up after capture")
            return self._set_signals_blocked

        def _set_signals_blocked(self, blocked: bool) -> bool:
            self.signal_setter_calls += 1
            if self.fail_next_signal_set:
                self.fail_next_signal_set = False
                raise KeyboardInterrupt("signal setter failed once")
            previous = self._signals_blocked
            self._signals_blocked = bool(blocked)
            return previous

    scene = SignalScene()
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )
    scene._signals_blocked = True
    scene.fail_port_lookup = True
    scene.fail_next_signal_set = True

    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert scene._signals_blocked is False
    assert scene.signal_getter_reads == 1
    assert scene.signal_setter_reads == 1
    assert scene.signal_getter_calls == 3
    assert scene.signal_setter_calls == 3


@pytest.mark.parametrize("failure_mode", ["raise", "no_op"])
def test_persistent_scene_signal_restore_is_critical(
    failure_mode: str,
) -> None:
    class PersistentSignalScene(_Scene):
        failure_mode: str | None = None

        def blockSignals(self, blocked: bool) -> bool:
            previous = self._signals_blocked
            if self.failure_mode == "raise":
                raise SystemExit("persistent signal setter failure")
            if self.failure_mode != "no_op":
                self._signals_blocked = bool(blocked)
            return previous

    scene = PersistentSignalScene()
    canvas = SimpleNamespace(scene=lambda: scene)
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)
    scene.failure_mode = failure_mode

    result = snapshot.restore_with_result()

    assert not result.authoritative
    assert not result.fallback_to_inverse
    if failure_mode == "raise":
        assert any(
            "persistent signal setter failure" in str(error) for error in result.errors
        )
    else:
        assert any(
            "did not restore the requested state" in str(error)
            for error in result.errors
        )


def test_exact_delete_final_repair_runs_after_raw_z_value_restore() -> None:
    class ZSceneItem(_SceneItem):
        def __init__(self, name: str) -> None:
            super().__init__(name)
            self._z = 0.0

        def zValue(self) -> float:
            return self._z

        def setZValue(self, value: float) -> None:
            self._z = float(value)

    class ZScene(_Scene):
        def items(self) -> list[_SceneItem]:
            return sorted(
                self._items,
                key=lambda item: item.zValue(),
                reverse=True,
            )

    scene = ZScene()
    items = [ZSceneItem(name) for name in ("first", "second", "third")]
    for item in items:
        scene.attach(item)
    expected_order = list(scene.items())
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        SimpleNamespace(scene=lambda: scene),
    )

    # Hide the corrupted sibling stack behind distinct z values. The early
    # runtime verification sees the expected visible order; restoring raw z
    # values later reveals the wrong underlying order unless a final pass runs.
    scene._items.reverse()
    for z_value, item in zip((3.0, 2.0, 1.0), items, strict=True):
        item.setZValue(z_value)
    assert scene.items() == expected_order

    result = snapshot.restore_with_result()

    assert result.authoritative
    assert result.errors == ()
    assert all(item.zValue() == 0.0 for item in items)
    assert all(
        current is expected
        for current, expected in zip(
            scene.items(),
            expected_order,
            strict=True,
        )
    )


@pytest.mark.parametrize("mutation_mode", ["fail_once", "persistent_reverse"])
def test_exact_delete_final_repair_verifies_after_signal_unblock(
    mutation_mode: str,
) -> None:
    class MutatingUnblockScene(_Scene):
        mode: str | None = None
        unblock_calls = 0

        def blockSignals(self, blocked: bool) -> bool:
            previous = super().blockSignals(blocked)
            if blocked:
                return previous
            self.unblock_calls += 1
            if self.unblock_calls < 2 or self.mode is None:
                return previous
            self._items.reverse()
            if self.mode == "fail_once":
                self.mode = None
                raise SystemExit("signal unblock mutated then failed")
            return previous

    scene = MutatingUnblockScene()
    first = _SceneItem("first")
    second = _SceneItem("second")
    for item in (first, second):
        scene.attach(item)
    expected_order = list(scene.items())
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        SimpleNamespace(scene=lambda: scene),
    )
    scene._items.reverse()
    scene.mode = mutation_mode

    result = snapshot.restore_with_result()

    if mutation_mode == "fail_once":
        assert result.authoritative
        assert result.errors == ()
        assert all(
            current is expected
            for current, expected in zip(
                scene.items(),
                expected_order,
                strict=True,
            )
        )
    else:
        assert not result.authoritative
        assert any(
            "exact ordered item identity" in str(error) for error in result.errors
        )


def test_exact_delete_verifies_identity_after_scene_rect_restore() -> None:
    scene = _Scene()
    first = _SceneItem("first")
    second = _SceneItem("second")
    for item in (first, second):
        scene.attach(item)
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        SimpleNamespace(scene=lambda: scene),
    )

    class MutatingSceneRectSnapshot:
        def restore(self) -> None:
            scene._items.reverse()

    snapshot.scene_rect_snapshot = MutatingSceneRectSnapshot()

    result = snapshot.restore_with_result()

    assert not result.authoritative
    assert any("exact ordered item identity" in str(error) for error in result.errors)


@pytest.mark.parametrize("restore_target", ["selection", "stacking"])
@pytest.mark.parametrize("failure_mode", ["fail_once", "no_op"])
def test_exact_scene_order_and_selection_restore_is_verified_and_retried(
    restore_target: str,
    failure_mode: str,
) -> None:
    class RetrySceneItem(_SceneItem):
        selection_failure_mode: str | None = None
        stacking_failure_mode: str | None = None

        def setSelected(self, selected: bool) -> None:
            if self.selection_failure_mode == "fail_once":
                self.selection_failure_mode = None
                raise KeyboardInterrupt("selection setter failed once")
            if self.selection_failure_mode != "no_op":
                super().setSelected(selected)

        def stackBefore(self, sibling: _SceneItem) -> None:
            if self.stacking_failure_mode == "fail_once":
                self.stacking_failure_mode = None
                raise SystemExit("stacking setter failed once")
            if self.stacking_failure_mode != "no_op":
                super().stackBefore(sibling)

    canvas = _Canvas()
    first = RetrySceneItem("first")
    second = RetrySceneItem("second")
    first.setSelected(True)
    for item in (first, second):
        canvas.scene().attach(item)
    expected_order = list(canvas.scene().items())
    snapshot = CanvasDeleteTransactionSnapshot.capture(canvas)

    if restore_target == "selection":
        first._selected = False
        first.selection_failure_mode = failure_mode
    else:
        canvas.scene()._items[:] = [second, first]
        second.stacking_failure_mode = failure_mode

    result = snapshot.restore_with_result()

    if failure_mode == "fail_once":
        assert result.authoritative
        assert result.errors == ()
        assert first.isSelected()
        assert all(
            current is expected
            for current, expected in zip(
                canvas.scene().items(),
                expected_order,
                strict=True,
            )
        )
    else:
        assert not result.authoritative
        assert not result.fallback_to_inverse
        expected_message = (
            "selection state"
            if restore_target == "selection"
            else "ordered item identity"
        )
        assert any(expected_message in str(error) for error in result.errors)


def test_exact_runtime_focus_restore_uses_captured_ports_and_retries_once() -> None:
    class FocusScene(_Scene):
        def __init__(self) -> None:
            super().__init__()
            self._focus_item_value = None
            self.focus_getter_reads = 0
            self.focus_setter_reads = 0
            self.focus_setter_calls = 0
            self.fail_next_focus_set = False

        @property
        def focusItem(self):
            self.focus_getter_reads += 1
            return self._focus_item

        def _focus_item(self):
            return self._focus_item_value

        @property
        def setFocusItem(self):
            self.focus_setter_reads += 1
            return self._set_focus_item

        def _set_focus_item(self, item) -> None:
            self.focus_setter_calls += 1
            if self.fail_next_focus_set:
                self.fail_next_focus_set = False
                raise SystemExit("focus restore terminated")
            self._focus_item_value = item

    scene = FocusScene()
    focused = _SceneItem("focused")
    replacement = _SceneItem("replacement")
    for item in (focused, replacement):
        scene.attach(item)
    focused.setSelected(True)
    scene._focus_item_value = focused
    snapshot = _scene_runtime_snapshot(
        SimpleNamespace(scene=lambda: scene),
        strict=True,
    )

    scene.detach(focused)
    scene._focus_item_value = replacement
    scene.fail_next_focus_set = True
    errors = _restore_scene_runtime_snapshot(snapshot, collect_errors=True)

    assert errors == []
    assert focused.scene() is scene
    assert focused.isSelected()
    assert scene._focus_item_value is focused
    assert scene.focus_getter_reads == 1
    assert scene.focus_setter_reads == 1
    assert scene.focus_setter_calls == 2

    transaction = CanvasDeleteTransactionSnapshot.capture(
        SimpleNamespace(scene=lambda: scene),
    )
    scene._focus_item_value = replacement
    scene.fail_next_focus_set = True

    result = transaction.restore_with_result()

    assert result.authoritative is True
    assert result.errors == ()
    assert scene._focus_item_value is focused
    assert scene.focus_getter_reads == 2
    assert scene.focus_setter_reads == 2
    # The transaction performs one final identity reassertion after restoring
    # raw scene-item state, in addition to the fail-once setter retry.
    assert scene.focus_setter_calls == 5


@pytest.mark.parametrize("getter_name", ["focusItem", "setFocusItem"])
def test_strict_runtime_focus_capture_propagates_live_descriptor_error(
    getter_name: str,
) -> None:
    class BrokenFocusScene(_Scene):
        _focus_item_value = None

        @property
        def focusItem(self):
            if getter_name == "focusItem":
                raise AttributeError("focusItem descriptor failed")
            return lambda: self._focus_item_value

        @property
        def setFocusItem(self):
            if getter_name == "setFocusItem":
                raise AttributeError("setFocusItem descriptor failed")
            return lambda item: setattr(self, "_focus_item_value", item)

    scene = BrokenFocusScene()

    with pytest.raises(
        AttributeError,
        match=rf"{getter_name} descriptor failed",
    ):
        _scene_runtime_snapshot(
            SimpleNamespace(scene=lambda: scene),
            strict=True,
        )


@pytest.mark.parametrize("operation", ["add", "delete", "update"])
def test_scene_item_command_failure_restores_exact_focus_identity(
    operation: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    focused = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
    other = QGraphicsRectItem(QRectF(20.0, 0.0, 10.0, 10.0))
    for item in (focused, other):
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
    focused.setSelected(True)
    scene.setFocusItem(focused)
    canvas = SimpleNamespace(scene=lambda: scene)
    primary = KeyboardInterrupt(f"{operation} command interrupted")

    if operation == "add":
        command = AddSceneItemsCommand([{"name": "new"}])

        def create_then_interrupt(_canvas, _state):
            created = QGraphicsRectItem(QRectF(40.0, 0.0, 10.0, 10.0))
            created.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
            scene.addItem(created)
            scene.setFocusItem(created)
            raise primary

        patches = {
            "_create_scene_item_from_state": create_then_interrupt,
            "_remove_scene_item": lambda _canvas, item: scene.removeItem(item),
        }

        def run() -> None:
            command.redo(canvas)

    elif operation == "delete":
        command = DeleteSceneItemsCommand([], [focused])

        def remove_then_interrupt(_canvas, item) -> None:
            scene.removeItem(item)
            scene.setFocusItem(other)
            raise primary

        patches = {
            "_remove_scene_item": remove_then_interrupt,
            "_restore_scene_item": lambda _canvas, item: scene.addItem(item),
        }

        def run() -> None:
            command.redo(canvas)

    else:
        command = UpdateSceneItemCommand(
            focused,
            {"x": 0.0},
            {"x": 25.0},
        )
        apply_calls = 0

        def apply_then_interrupt(_canvas, item, state) -> None:
            nonlocal apply_calls
            apply_calls += 1
            item.setPos(state["x"], 0.0)
            if apply_calls == 1:
                scene.setFocusItem(other)
                raise primary

        patches = {
            "_apply_scene_item_state": apply_then_interrupt,
            "refresh_selection_outline_for_canvas": lambda _canvas: None,
        }

        def run() -> None:
            command.redo(canvas)

    with (
        mock.patch.multiple("ui.history_commands", **patches),
        pytest.raises(KeyboardInterrupt) as caught,
    ):
        run()

    assert caught.value is primary
    assert focused.scene() is scene
    assert focused.isSelected()
    assert scene.focusItem() is focused


def test_delete_transaction_release_baseexception_restores_original_mutation() -> None:
    canvas = _Canvas()
    atom = SimpleNamespace(x=1.0, y=2.0)
    canvas.model = SimpleNamespace(atoms={7: atom}, bonds=[])
    original_release = CanvasDeleteTransactionSnapshot.release

    def release_then_terminate(snapshot) -> None:
        original_release(snapshot)
        raise SystemExit("delete transaction release failed")

    with (
        mock.patch.object(
            CanvasDeleteTransactionSnapshot,
            "release",
            new=release_then_terminate,
        ),
        pytest.raises(SystemExit, match="delete transaction release failed"),
    ):
        with canvas_delete_transaction(canvas):
            atom.x = 99.0
            atom.y = 199.0

    assert canvas.model.atoms[7] is atom
    assert (atom.x, atom.y) == (1.0, 2.0)


@pytest.mark.parametrize(
    ("command", "method_name", "starts_attached", "operation_name"),
    [
        (AddSceneItemsCommand([], []), "redo", False, "restore"),
        (AddSceneItemsCommand([], []), "undo", True, "remove"),
        (DeleteSceneItemsCommand([], []), "redo", True, "remove"),
        (DeleteSceneItemsCommand([], []), "undo", False, "restore"),
    ],
)
def test_existing_scene_item_commands_rollback_a_second_item_that_mutates_then_raises(
    command,
    method_name: str,
    starts_attached: bool,
    operation_name: str,
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    command.items[:] = items
    if starts_attached:
        for item in items:
            canvas.scene().attach(item)
    before = canvas.scene().items()
    failed = False

    def restore_with_failure(canvas_arg, item) -> None:
        nonlocal failed
        _restore_scene_item(canvas_arg, item)
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("restore failed after mutation")

    def remove_with_failure(canvas_arg, item) -> None:
        nonlocal failed
        _remove_scene_item(canvas_arg, item)
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("remove failed after mutation")

    patches = {
        "_restore_scene_item": restore_with_failure,
        "_remove_scene_item": remove_with_failure,
    }
    with mock.patch.multiple("ui.history_commands", **patches):
        with pytest.raises(
            RuntimeError, match=f"{operation_name} failed after mutation"
        ):
            getattr(command, method_name)(canvas)

    assert canvas.scene().items() == before


@pytest.mark.parametrize("control_flow_error", [KeyboardInterrupt, SystemExit])
def test_existing_scene_item_command_rolls_back_mutate_then_control_flow_exception(
    control_flow_error: type[BaseException],
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for item in items:
        canvas.scene().attach(item)
    before = canvas.scene().items()

    def remove_then_interrupt(canvas_arg, item) -> None:
        _remove_scene_item(canvas_arg, item)
        if item is items[1]:
            raise control_flow_error("control-flow after scene mutation")

    command = DeleteSceneItemsCommand([], items)
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_then_interrupt,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item",
            side_effect=_restore_scene_item,
        ),
        pytest.raises(
            control_flow_error,
            match="control-flow after scene mutation",
        ),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before
    assert all(item.scene() is canvas.scene() for item in items)


def test_scene_item_control_flow_rollback_preserves_primary_and_notes_secondary_failure() -> (
    None
):
    canvas = _Canvas()
    item = _SceneItem("item")
    canvas.scene().attach(item)
    before = canvas.scene().items()

    def remove_then_interrupt(canvas_arg, target) -> None:
        _remove_scene_item(canvas_arg, target)
        raise KeyboardInterrupt("primary interruption")

    def fail_reattach(_canvas, _target) -> None:
        raise SystemExit("secondary rollback termination")

    command = DeleteSceneItemsCommand([], [item])
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_then_interrupt,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item",
            side_effect=fail_reattach,
        ),
        pytest.raises(KeyboardInterrupt, match="primary interruption") as caught,
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before
    assert item.scene() is canvas.scene()
    assert any(
        "SystemExit: secondary rollback termination" in note
        for note in getattr(caught.value, "__notes__", [])
    )


@pytest.mark.parametrize(
    "command",
    [
        AddSceneItemsCommand([{"name": "first"}, {"name": "second", "fail": True}]),
        DeleteSceneItemsCommand([{"name": "first"}, {"name": "second", "fail": True}]),
    ],
)
def test_initial_scene_item_creation_rollback_finds_the_unreturned_failed_item(
    command,
) -> None:
    canvas = _Canvas()
    existing = _SceneItem("existing")
    canvas.scene().attach(existing)
    before = canvas.scene().items()

    def create_with_failure(canvas_arg, state):
        item = _SceneItem(state["name"])
        canvas_arg.scene().attach(item)
        if state.get("fail"):
            raise RuntimeError("create failed after mutation")
        return item

    method = command.redo if isinstance(command, AddSceneItemsCommand) else command.undo
    with (
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_with_failure,
        ),
        mock.patch(
            "ui.history_commands._remove_scene_item", side_effect=_remove_scene_item
        ),
        pytest.raises(RuntimeError, match="create failed after mutation"),
    ):
        method(canvas)

    assert canvas.scene().items() == before
    assert command.items == []


@pytest.mark.parametrize("control_flow_error", [KeyboardInterrupt, SystemExit])
def test_initial_scene_item_creation_rolls_back_control_flow_exception(
    control_flow_error: type[BaseException],
) -> None:
    canvas = _Canvas()
    existing = _SceneItem("existing")
    canvas.scene().attach(existing)
    before = canvas.scene().items()
    command = AddSceneItemsCommand(
        [{"name": "first"}, {"name": "second", "interrupt": True}]
    )

    def create_then_interrupt(canvas_arg, state):
        item = _SceneItem(state["name"])
        canvas_arg.scene().attach(item)
        if state.get("interrupt"):
            raise control_flow_error("control-flow after item creation")
        return item

    with (
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_then_interrupt,
        ),
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=_remove_scene_item,
        ),
        pytest.raises(
            control_flow_error,
            match="control-flow after item creation",
        ),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before
    assert command.items == []


@pytest.mark.parametrize(
    ("command_type", "method_name"),
    [
        (AddSceneItemsCommand, "redo"),
        (DeleteSceneItemsCommand, "undo"),
    ],
)
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_initial_scene_item_creation_restores_actual_qt_auto_rect_after_second_exit(
    command_type,
    method_name: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    baseline_item = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline = QRectF(scene.sceneRect())
    command = command_type(
        [
            {"x": 10_000.0, "fail": False},
            {"x": 20_000.0, "fail": True},
        ]
    )
    created: list[QGraphicsRectItem] = []

    def create_with_nested_attach(_canvas, state):
        item = QGraphicsRectItem(QRectF(state["x"], 0.0, 10.0, 10.0))
        child_snapshot = SceneRectSnapshot.capture(scene)
        assert child_snapshot is not None
        scene.addItem(item)
        scene.sceneRect()
        child_snapshot.release(
            item.sceneBoundingRect(),
            expansion_key=item,
        )
        created.append(item)
        if state["fail"]:
            raise error_type("second Qt scene-item creation terminated")
        return item

    with (
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_with_nested_attach,
        ),
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=lambda _canvas, item: scene.removeItem(item),
        ),
        pytest.raises(
            error_type,
            match="second Qt scene-item creation terminated",
        ),
    ):
        getattr(command, method_name)(canvas)

    assert baseline_item.scene() is scene
    assert all(item.scene() is None for item in created)
    assert command.items == []
    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert scene.sceneRect() == baseline
    future = scene.addRect(QRectF(30_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 30_000.0


@pytest.mark.parametrize(
    ("command_type", "method_name", "starts_attached", "operation_name"),
    [
        (AddSceneItemsCommand, "redo", False, "restore"),
        (AddSceneItemsCommand, "undo", True, "remove"),
        (DeleteSceneItemsCommand, "redo", True, "remove"),
        (DeleteSceneItemsCommand, "undo", False, "restore"),
    ],
)
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_existing_scene_item_commands_restore_actual_qt_auto_rect_after_second_exit(
    command_type,
    method_name: str,
    starts_attached: bool,
    operation_name: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    baseline_item = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    items = [
        QGraphicsRectItem(QRectF(10_000.0, 0.0, 10.0, 10.0)),
        QGraphicsRectItem(QRectF(20_000.0, 0.0, 10.0, 10.0)),
    ]
    if starts_attached:
        for item in items:
            scene.addItem(item)
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline_items = {id(item) for item in scene.items()}
    baseline = QRectF(scene.sceneRect())
    command = command_type([], items)
    attempted = 0
    transients: list[QGraphicsRectItem] = []

    def restore_with_nested_attach(_canvas, item) -> None:
        nonlocal attempted
        attempted += 1
        child_snapshot = SceneRectSnapshot.capture(scene)
        assert child_snapshot is not None
        scene.addItem(item)
        scene.sceneRect()
        child_snapshot.release(
            item.sceneBoundingRect(),
            expansion_key=item,
        )
        if attempted == 2:
            raise error_type("second Qt scene-item restore terminated")

    def remove_with_nested_transient(_canvas, item) -> None:
        nonlocal attempted
        attempted += 1
        child_snapshot = SceneRectSnapshot.capture(scene)
        assert child_snapshot is not None
        transient = QGraphicsRectItem(
            QRectF(30_000.0 + attempted * 1_000.0, 0.0, 10.0, 10.0)
        )
        transients.append(transient)
        scene.addItem(transient)
        scene.sceneRect()
        scene.removeItem(item)
        scene.removeItem(transient)
        child_snapshot.release(
            transient.sceneBoundingRect(),
            expansion_key=transient,
        )
        if attempted == 2:
            raise error_type("second Qt scene-item remove terminated")

    patches = {
        "_remove_scene_item": (
            remove_with_nested_transient
            if operation_name == "remove"
            else lambda _canvas, item: scene.removeItem(item)
        ),
        "_restore_scene_item": (
            restore_with_nested_attach
            if operation_name == "restore"
            else lambda _canvas, item: scene.addItem(item)
        ),
    }
    with (
        mock.patch.multiple("ui.history_commands", **patches),
        pytest.raises(
            error_type,
            match=f"second Qt scene-item {operation_name} terminated",
        ),
    ):
        getattr(command, method_name)(canvas)

    assert baseline_item.scene() is scene
    assert {id(item) for item in scene.items()} == baseline_items
    assert all(item.scene() is (scene if starts_attached else None) for item in items)
    assert all(item.scene() is None for item in transients)
    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.depth == 0
    assert tracker.pending_expansions == {}
    assert tracker.pending_journal == []
    assert scene.sceneRect() == baseline
    future = scene.addRect(QRectF(50_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 50_000.0


def test_scene_item_batch_success_releases_one_final_bounds_scan_after_o1_children() -> (
    None
):
    class CountingDict(dict):
        values_calls = 0

        def values(self):
            self.values_calls += 1
            return super().values()

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    primer = SceneRectSnapshot.capture(scene)
    assert primer is not None
    primer.release(scene.itemsBoundingRect())
    pending = CountingDict()
    primer.tracker.pending_expansions = pending
    states = [{"x": 10_000.0 + index * 20.0} for index in range(64)]
    command = AddSceneItemsCommand(states)

    def create_with_nested_attach(_canvas, state):
        item = QGraphicsRectItem(QRectF(state["x"], 0.0, 10.0, 10.0))
        child_snapshot = SceneRectSnapshot.capture(scene)
        assert child_snapshot is not None
        scene.addItem(item)
        child_snapshot.release(
            item.sceneBoundingRect(),
            expansion_key=item,
        )
        return item

    with (
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_with_nested_attach,
        ),
        mock.patch.object(
            scene,
            "itemsBoundingRect",
            wraps=scene.itemsBoundingRect,
        ) as bounds_scan,
    ):
        command.redo(canvas)

    assert len(command.items) == len(states)
    assert all(item.scene() is scene for item in command.items)
    assert bounds_scan.call_count == 1
    assert pending.values_calls == 1
    assert scene.sceneRect().right() > states[-1]["x"]
    future = scene.addRect(QRectF(100_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 100_000.0


@pytest.mark.parametrize("operation", ["create", "remove", "update"])
def test_explicit_scene_item_history_success_never_scans_global_item_bounds(
    operation: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    explicit_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
    set_explicit_scene_rect(scene, explicit_rect)

    if operation == "create":
        command = AddSceneItemsCommand([{"x": 25.0}])

        def run() -> None:
            with mock.patch(
                "ui.history_commands._create_scene_item_from_state",
                side_effect=lambda _canvas, _state: scene.addRect(
                    QRectF(25.0, 0.0, 10.0, 10.0)
                ),
            ):
                command.redo(canvas)

    elif operation == "remove":
        command = DeleteSceneItemsCommand([], [item])

        def run() -> None:
            with mock.patch(
                "ui.history_commands._remove_scene_item",
                side_effect=lambda _canvas, target: scene.removeItem(target),
            ):
                command.redo(canvas)

    else:
        command = UpdateSceneItemCommand(item, {"x": 0.0}, {"x": 25.0})

        def run() -> None:
            with (
                mock.patch(
                    "ui.history_commands._apply_scene_item_state",
                    side_effect=lambda _canvas, target, state: target.setPos(
                        state["x"],
                        0.0,
                    ),
                ),
                mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
            ):
                command.redo(canvas)

    with mock.patch.object(
        scene,
        "itemsBoundingRect",
        wraps=scene.itemsBoundingRect,
    ) as bounds_scan:
        run()

    assert bounds_scan.call_count == 0
    assert scene.sceneRect() == explicit_rect


@pytest.mark.parametrize("mutate_before_raise", [False, True])
def test_scene_item_batch_scene_rect_restore_retries_once_and_notes_first_failure(
    mutate_before_raise: bool,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline = QRectF(scene.sceneRect())
    command = AddSceneItemsCommand([{"fail": False}, {"fail": True}])
    original_set_scene_rect = scene.setSceneRect
    setter_calls = 0

    def set_scene_rect_with_one_restore_failure(rect: QRectF) -> None:
        nonlocal setter_calls
        setter_calls += 1
        # Capture itself now performs two verified setter roundtrips; inject
        # the failure into the first restore attempt that follows mutation.
        if setter_calls == 3:
            if mutate_before_raise:
                original_set_scene_rect(rect)
            raise SystemExit("first scene-rect restore attempt terminated")
        original_set_scene_rect(rect)

    def create_then_interrupt(_canvas, state):
        item = QGraphicsRectItem(QRectF(10_000.0, 0.0, 10.0, 10.0))
        scene.addItem(item)
        scene.sceneRect()
        if state["fail"]:
            raise KeyboardInterrupt("scene item batch interrupted")
        return item

    with (
        mock.patch.object(
            scene,
            "setSceneRect",
            side_effect=set_scene_rect_with_one_restore_failure,
        ),
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_then_interrupt,
        ),
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=lambda _canvas, item: scene.removeItem(item),
        ),
        pytest.raises(
            KeyboardInterrupt,
            match="scene item batch interrupted",
        ) as caught,
    ):
        command.redo(canvas)

    assert setter_calls == 5
    assert any(
        "first scene-rect restore attempt terminated" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.depth == 0
    assert scene.sceneRect() == baseline
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


def test_scene_item_batch_scene_rect_restore_notes_both_failed_attempts() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    command = AddSceneItemsCommand([{"fail": False}, {"fail": True}])
    original_capture = SceneRectSnapshot.capture
    original_set_scene_rect = scene.setSceneRect
    captured: list[SceneRectSnapshot] = []
    setter_calls = 0

    def capture(scene_arg):
        snapshot = original_capture(scene_arg)
        assert snapshot is not None
        captured.append(snapshot)
        return snapshot

    def fail_both_restore_attempts(rect: QRectF) -> None:
        nonlocal setter_calls
        setter_calls += 1
        # Capture owns calls 1-2. Fail both verified attempts of the first
        # restore (probe call 3, inherited-mode call 5); the command-level
        # retry must then finish the still-active savepoint on calls 6-7.
        if setter_calls in {3, 5}:
            raise KeyboardInterrupt(f"scene-rect restore failure {setter_calls}")
        original_set_scene_rect(rect)

    def create_then_terminate(_canvas, state):
        item = QGraphicsRectItem(QRectF(10_000.0, 0.0, 10.0, 10.0))
        scene.addItem(item)
        scene.sceneRect()
        if state["fail"]:
            raise SystemExit("scene item batch terminated")
        return item

    with (
        mock.patch(
            "ui.history_commands.SceneRectSnapshot.capture",
            side_effect=capture,
        ),
        mock.patch.object(
            scene,
            "setSceneRect",
            side_effect=fail_both_restore_attempts,
        ),
        mock.patch(
            "ui.history_commands._create_scene_item_from_state",
            side_effect=create_then_terminate,
        ),
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=lambda _canvas, item: scene.removeItem(item),
        ),
        pytest.raises(
            SystemExit,
            match="scene item batch terminated",
        ) as caught,
    ):
        command.redo(canvas)

    restore_notes = [
        note
        for note in getattr(caught.value, "__notes__", [])
        if "scene-rect restore failure" in note
    ]
    assert setter_calls == 7
    assert len(restore_notes) == 2
    assert len(captured) == 1
    assert not captured[0].active
    assert captured[0].tracker.depth == 0


@pytest.mark.parametrize("method_name", ["redo", "undo"])
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_update_scene_item_restores_actual_qt_auto_rect_after_refresh_exit(
    method_name: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    item = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    baseline = QRectF(scene.sceneRect())
    before_state = {"x": 0.0 if method_name == "redo" else 10_000.0}
    after_state = {"x": 10_000.0 if method_name == "redo" else 0.0}
    command = UpdateSceneItemCommand(item, before_state, after_state)
    refresh_calls = 0

    def apply_state(_canvas, target, state) -> None:
        target.setPos(state["x"], 0.0)
        scene.sceneRect()

    def refresh_then_exit(_canvas) -> None:
        nonlocal refresh_calls
        refresh_calls += 1
        if refresh_calls == 1:
            raise error_type("selection outline refresh terminated")

    with (
        mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=apply_state,
        ),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_exit,
        ),
        pytest.raises(
            error_type,
            match="selection outline refresh terminated",
        ),
    ):
        getattr(command, method_name)(canvas)

    assert item.pos().x() == 0.0
    assert scene.sceneRect() == baseline
    tracker = scene._chemvas_scene_rect_tracker
    assert tracker.depth == 0
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


def test_note_remove_failure_restores_collections_selection_and_container_identity() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    other = _SceneItem("other")
    note = _SceneItem("note")
    tail = _SceneItem("tail")
    for item in (other, note, tail):
        canvas.scene().attach(item)
    note.setSelected(True)

    note_items = [other, note]
    selected_notes = [note]
    selected_style_items = [note]
    outlines = [_SceneItem("outline")]
    canvas.scene_items_state.note_items = note_items
    canvas.scene_items_state.selected_notes = selected_notes
    canvas.selection_style_state.selected_items = selected_style_items
    canvas.selection_outline_state.outlines = outlines
    before_order = canvas.scene().items()
    before_info = vars(canvas.selection_info_state).copy()

    def remove_after_registration_mutation(_canvas, item) -> None:
        note_items.remove(item)
        selected_notes.remove(item)
        item.setSelected(False)
        canvas.selection_style_state.selected_items = []
        canvas.selection_outline_state.outlines = []
        canvas.selection_info_state.signature = None
        canvas.selection_info_state.cache = ("mutated", "selection")
        raise RuntimeError("note remove failed before detach")

    command = DeleteSceneItemsCommand([], [note])
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_after_registration_mutation,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item", side_effect=_restore_scene_item
        ),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before_order
    assert note.isSelected()
    assert canvas.scene_items_state.note_items is note_items
    assert note_items == [other, note]
    assert canvas.scene_items_state.selected_notes is selected_notes
    assert selected_notes == [note]
    assert canvas.selection_style_state.selected_items is selected_style_items
    assert selected_style_items == [note]
    assert canvas.selection_outline_state.outlines is outlines
    assert vars(canvas.selection_info_state) == before_info


def test_note_remove_failure_restores_selection_child_visual_state() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    note = _SceneItem("note")
    selection_box = _VisualRectSceneItem("note-select")
    canvas.scene().attach(note)
    canvas.scene().attach(selection_box)
    selected_notes = [note]
    note_items = [note]
    canvas.scene_items_state.selected_notes = selected_notes
    canvas.scene_items_state.note_items = note_items

    def remove_after_selection_box_mutation(_canvas, item) -> None:
        selected_notes.remove(item)
        note_items.remove(item)
        selection_box.setVisible(False)
        selection_box.setRect("mutated-rect")
        selection_box.setPen("mutated-pen")
        selection_box.setBrush("mutated-brush")
        canvas.scene().detach(item)
        raise RuntimeError("note detach failed after hiding selection box")

    command = DeleteSceneItemsCommand([], [note])
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_after_selection_box_mutation,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item", side_effect=_restore_scene_item
        ),
        pytest.raises(RuntimeError, match="after hiding selection box"),
    ):
        command.redo(canvas)

    assert canvas.scene_items_state.selected_notes is selected_notes
    assert selected_notes == [note]
    assert canvas.scene_items_state.note_items is note_items
    assert note_items == [note]
    assert selection_box.isVisible()
    assert selection_box.rect_value == "before-rect"
    assert selection_box.pen_value == "before-pen"
    assert selection_box.brush_value == "before-brush"
    assert canvas.scene().items() == [note, selection_box]


def test_mark_remove_failure_restores_registry_nested_lists_and_mapping_identity() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    mark = _SceneItem("mark")
    canvas.scene().attach(mark)
    mark_items = [mark]
    marks_for_atom = [mark]
    by_atom = {7: marks_for_atom}
    canvas.scene_items_state.mark_items = mark_items
    canvas.mark_registry.by_atom = by_atom

    def remove_after_registry_mutation(_canvas, item) -> None:
        mark_items.remove(item)
        marks_for_atom.remove(item)
        by_atom.pop(7)
        raise RuntimeError("mark remove failed before detach")

    command = AddSceneItemsCommand([], [mark])
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_after_registry_mutation,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item", side_effect=_restore_scene_item
        ),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.undo(canvas)

    assert canvas.scene_items_state.mark_items is mark_items
    assert mark_items == [mark]
    assert canvas.mark_registry.by_atom is by_atom
    assert by_atom[7] is marks_for_atom
    assert marks_for_atom == [mark]
    assert mark.scene() is canvas.scene()


@pytest.mark.parametrize("collection_name", ["shape_items", "orbital_items"])
def test_handle_target_remove_failure_restores_handles_scene_order_and_container_identity(
    collection_name: str,
) -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    target = _StyledSceneItem("target")
    first_handle = _SceneItem("first-handle")
    second_handle = _SceneItem("second-handle")
    other = _SceneItem("other")
    for item in (target, first_handle, second_handle, other):
        canvas.scene().attach(item)
    target_collection = [target]
    setattr(canvas.scene_items_state, collection_name, target_collection)
    active_handles = [first_handle, second_handle]
    canvas.handle_state.active_handles = active_handles
    canvas.handle_state.target = target
    selected_style_items = [target]
    canvas.selection_style_state.selected_items = selected_style_items
    before_order = canvas.scene().items()

    def remove_after_handle_clear(_canvas, item) -> None:
        target_collection.remove(item)
        canvas.scene().detach(first_handle)
        canvas.scene().detach(second_handle)
        canvas.handle_state.active_handles = []
        canvas.handle_state.target = None
        target.pen_value = "normal"
        target.original_pen = None
        canvas.selection_style_state.selected_items = []
        raise RuntimeError("target remove failed before detach")

    command = DeleteSceneItemsCommand([], [target])
    with (
        mock.patch(
            "ui.history_commands._remove_scene_item",
            side_effect=remove_after_handle_clear,
        ),
        mock.patch(
            "ui.history_commands._restore_scene_item", side_effect=_restore_scene_item
        ),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before_order
    assert getattr(canvas.scene_items_state, collection_name) is target_collection
    assert target_collection == [target]
    assert canvas.handle_state.active_handles is active_handles
    assert active_handles == [first_handle, second_handle]
    assert canvas.handle_state.target is target
    assert canvas.selection_style_state.selected_items is selected_style_items
    assert selected_style_items == [target]
    assert target.pen_value == "highlight"
    assert target.original_pen == "normal"


@pytest.mark.parametrize(("method_name", "direction"), [("redo", 1.0), ("undo", -1.0)])
def test_move_items_command_rolls_back_a_second_item_that_mutates_then_raises(
    method_name: str,
    direction: float,
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for item in items:
        canvas.scene().attach(item)
    before = [(item.x, item.y) for item in items]
    failed = False

    def move_with_failure(_canvas, item, dx, dy, *, update_selection) -> None:
        nonlocal failed
        assert not update_selection
        item.x += dx
        item.y += dy
        if item is items[1] and dx == direction * 3.0 and not failed:
            failed = True
            raise RuntimeError("move failed after mutation")

    command = MoveItemsCommand(items, 3.0, 5.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="move failed after mutation"),
    ):
        getattr(command, method_name)(canvas)

    assert [(item.x, item.y) for item in items] == before


@pytest.mark.parametrize("control_flow_error", [KeyboardInterrupt, SystemExit])
def test_move_items_command_rolls_back_mutate_then_control_flow_exception(
    control_flow_error: type[BaseException],
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for item in items:
        canvas.scene().attach(item)
    before = [(item.x, item.y) for item in items]
    interrupted = False

    def move_then_interrupt(_canvas, item, dx, dy, *, update_selection) -> None:
        nonlocal interrupted
        assert not update_selection
        item.x += dx
        item.y += dy
        if item is items[1] and dx == 3.0 and not interrupted:
            interrupted = True
            raise control_flow_error("control-flow after move mutation")

    command = MoveItemsCommand(items, 3.0, 5.0)
    with (
        mock.patch(
            "ui.history_commands.move_item_for", side_effect=move_then_interrupt
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(
            control_flow_error,
            match="control-flow after move mutation",
        ),
    ):
        command.redo(canvas)

    assert [(item.x, item.y) for item in items] == before


def test_move_items_command_restores_absolute_state_after_partial_field_mutation() -> (
    None
):
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for index, item in enumerate(items):
        item.x = float(index)
        item.metadata_x = float(index)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "test", "x": item.x, "metadata_x": item.metadata_x}

    def apply_state(_canvas, item, state) -> None:
        item.x = state["x"]
        item.metadata_x = state["metadata_x"]

    def move_with_partial_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal failed
        assert not update_selection
        item.x += dx
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("move failed between geometry and metadata")
        item.metadata_x += dx

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for", side_effect=snapshot_state
        ),
        mock.patch(
            "ui.history_commands._apply_scene_item_state", side_effect=apply_state
        ),
        mock.patch(
            "ui.history_commands.move_item_for", side_effect=move_with_partial_failure
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="between geometry and metadata"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


@pytest.mark.parametrize(
    ("kind", "item_id", "moved_atom_ids"),
    [
        ("atom", 7, (7,)),
        ("bond", 0, (7, 8)),
    ],
)
def test_move_model_backed_item_restores_absolute_model_and_3d_state_on_refresh_failure(
    kind: str,
    item_id: int,
    moved_atom_ids: tuple[int, ...],
) -> None:
    canvas = _Canvas()
    atoms = {
        7: SimpleNamespace(x=1.0, y=2.0),
        8: SimpleNamespace(x=5.0, y=6.0),
    }
    canvas.model = SimpleNamespace(
        atoms=atoms,
        bonds=[SimpleNamespace(a=7, b=8)],
    )
    coords_3d = {
        7: (1.0, 2.0, 3.0),
        8: (5.0, 6.0, 7.0),
    }
    canvas.atom_coords_3d_state = SimpleNamespace(atom_coords_3d=coords_3d)
    item = _ModelBackedSceneItem(kind, kind, item_id)
    canvas.scene().attach(item)
    before_positions = {
        atom_id: (atoms[atom_id].x, atoms[atom_id].y) for atom_id in moved_atom_ids
    }
    before_coords = {atom_id: coords_3d[atom_id] for atom_id in moved_atom_ids}

    def move_model_item(_canvas, current_item, dx, dy, *, update_selection) -> None:
        assert not update_selection
        current_item.x += dx
        for atom_id in moved_atom_ids:
            atoms[atom_id].x += dx
            atoms[atom_id].y += dy
            x, y, z = coords_3d[atom_id]
            coords_3d[atom_id] = (x + dx, y + dy, z)

    restore_calls: list[tuple[dict, dict | None]] = []

    def restore_model_state(
        _canvas, positions, *, update_selection, coords_3d=None
    ) -> None:
        assert not update_selection
        restore_calls.append(
            (dict(positions), dict(coords_3d) if coords_3d is not None else None)
        )
        for atom_id, (x, y) in positions.items():
            atoms[atom_id].x = x
            atoms[atom_id].y = y
        if coords_3d is not None:
            canvas.atom_coords_3d_state.atom_coords_3d.update(coords_3d)

    command = MoveItemsCommand([item], 4.0, 9.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_model_item),
        mock.patch(
            "ui.history_commands._set_atom_positions_for_history",
            side_effect=restore_model_state,
        ),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=RuntimeError("selection refresh failed"),
        ),
        pytest.raises(RuntimeError, match="selection refresh failed"),
    ):
        command.redo(canvas)

    assert item.x == 0.0
    assert {
        atom_id: (atoms[atom_id].x, atoms[atom_id].y) for atom_id in moved_atom_ids
    } == before_positions
    assert {atom_id: coords_3d[atom_id] for atom_id in moved_atom_ids} == before_coords
    assert restore_calls == [(before_positions, before_coords)]


def test_move_items_exact_restore_survives_partial_bulk_rollback_baseexception() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    atoms = {
        7: SimpleNamespace(x=1.0, y=2.0),
        8: SimpleNamespace(x=5.0, y=6.0),
    }
    canvas.model = SimpleNamespace(
        atoms=atoms,
        bonds=[SimpleNamespace(a=7, b=8)],
    )
    coords_3d = {
        7: (1.0, 2.0, 3.0),
        8: (5.0, 6.0, 7.0),
    }
    canvas.atom_coords_3d_state = SimpleNamespace(atom_coords_3d=coords_3d)
    item = _ModelBackedSceneItem("bond", "bond", 0)
    canvas.scene().attach(item)
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )
    before_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms.items()}
    before_coords = dict(coords_3d)

    def move_model_item(_canvas, current_item, dx, dy, *, update_selection) -> None:
        assert not update_selection
        current_item.x += dx
        for atom_id, atom in atoms.items():
            atom.x += dx
            atom.y += dy
            x, y, z = coords_3d[atom_id]
            coords_3d[atom_id] = (x + dx, y + dy, z)

    def partial_restore(
        _canvas, positions, *, update_selection, coords_3d=None
    ) -> None:
        assert not update_selection
        atom_id = 7
        atoms[atom_id].x, atoms[atom_id].y = positions[atom_id]
        if coords_3d is not None:
            canvas.atom_coords_3d_state.atom_coords_3d[atom_id] = coords_3d[atom_id]
        raise SystemExit("persistent bulk rollback termination")

    command = MoveItemsCommand([item], 4.0, 9.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_model_item),
        mock.patch(
            "ui.history_commands._set_atom_positions_for_history",
            side_effect=partial_restore,
        ),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(
            RuntimeError, match="persistent outline rebuild failure"
        ) as caught,
    ):
        command.redo(canvas)

    assert {
        atom_id: (atom.x, atom.y) for atom_id, atom in atoms.items()
    } == before_positions
    assert coords_3d == before_coords
    assert item.x == 0.0
    _assert_original_outline_restored(canvas, old_outline, outlines, partial_outlines)
    assert any(
        "SystemExit: persistent bulk rollback termination" in note
        for note in getattr(caught.value, "__notes__", [])
    )


@pytest.mark.parametrize(("kind", "data_role"), [("shape", 1), ("arrow", 2)])
def test_move_exact_restore_keeps_data_identity_and_history_retryable(
    kind: str,
    data_role: int,
) -> None:
    class ExactDataSceneItem(_SceneItem):
        def __init__(self) -> None:
            super().__init__(kind)
            self._data: dict[int, object] = {
                0: kind,
                data_role: {"point": (3.0, 7.0)},
            }

        def pos(self) -> tuple[float, float]:
            return (self.x, self.y)

        def setPos(self, position: tuple[float, float]) -> None:
            self.x, self.y = position

        def data(self, role: int):
            return self._data.get(role)

        def setData(self, role: int, value) -> None:
            self._data[role] = value

    canvas = _Canvas()
    item = ExactDataSceneItem()
    canvas.scene().attach(item)
    original_data = item.data(data_role)
    command = MoveItemsCommand([item], 5.0, 9.0)
    history_sentinel = object()
    redo_sentinel = object()
    history = [history_sentinel]
    redo_stack = [redo_sentinel, command]
    state = CanvasHistoryState(history=history, redo_stack=redo_stack)  # type: ignore[list-item]
    service = CanvasHistoryService(canvas, state)
    primary = RuntimeError("move failed after replacing item data")

    def snapshot_state(_canvas, _item) -> dict[str, object]:
        return {"kind": kind, "data": dict(original_data)}

    def apply_state(_canvas, current_item, state) -> None:
        current_item.setData(data_role, dict(state["data"]))

    def move_then_fail(_canvas, current_item, _dx, _dy, *, update_selection) -> None:
        assert not update_selection
        current_item.setData(data_role, {"point": (100.0, 200.0)})
        raise primary

    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for",
            side_effect=snapshot_state,
        ),
        mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=apply_state,
        ),
        mock.patch(
            "ui.history_commands.move_item_for",
            side_effect=move_then_fail,
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError) as caught,
    ):
        service.redo()

    assert caught.value is primary
    assert item.data(data_role) is original_data
    assert item.data(data_role) == {"point": (3.0, 7.0)}
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert state.history == [history_sentinel]
    assert state.redo_stack == [redo_sentinel, command]


@pytest.mark.parametrize("failure_source", ["item_snapshot", "handle_snapshot"])
def test_move_preflight_failure_keeps_history_stacks_retryable(
    failure_source: str,
) -> None:
    canvas = _Canvas()
    item = _SceneItem("moved")
    canvas.scene().attach(item)
    command = MoveItemsCommand([item], 5.0, 9.0)
    history_sentinel = object()
    redo_sentinel = object()
    history = [history_sentinel]
    redo_stack = [redo_sentinel, command]
    state = CanvasHistoryState(history=history, redo_stack=redo_stack)  # type: ignore[list-item]
    service = CanvasHistoryService(canvas, state)
    primary = KeyboardInterrupt(f"{failure_source} failed before move")
    item_snapshot_error = primary if failure_source == "item_snapshot" else None
    handle_snapshot_error = primary if failure_source == "handle_snapshot" else None

    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for",
            side_effect=item_snapshot_error,
            return_value={},
        ),
        mock.patch(
            "ui.history_commands._active_handle_position_snapshots",
            side_effect=handle_snapshot_error,
            return_value=[] if handle_snapshot_error is None else None,
        ),
        mock.patch("ui.history_commands.move_item_for") as move_item,
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(KeyboardInterrupt) as caught,
    ):
        service.redo()

    assert caught.value is primary
    move_item.assert_not_called()
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert state.history == [history_sentinel]
    assert state.redo_stack == [redo_sentinel, command]


def test_move_live_membership_failure_keeps_history_stacks_retryable() -> None:
    primary = RuntimeError("live item scene lookup failed")

    class FailOnceMembershipItem(_SceneItem):
        scene_calls = 0

        def scene(self) -> _Scene | None:
            self.scene_calls += 1
            if self.scene_calls == 1:
                raise primary
            return super().scene()

    canvas = _Canvas()
    item = FailOnceMembershipItem("moved")
    canvas.scene().attach(item)
    command = MoveItemsCommand([item], 5.0, 9.0)
    history_sentinel = object()
    redo_sentinel = object()
    history = [history_sentinel]
    redo_stack = [redo_sentinel, command]
    state = CanvasHistoryState(history=history, redo_stack=redo_stack)  # type: ignore[list-item]
    service = CanvasHistoryService(canvas, state)

    with (
        mock.patch("ui.history_commands.move_item_for") as move_item,
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError) as caught,
    ):
        service.redo()

    assert caught.value is primary
    move_item.assert_not_called()
    assert item.scene() is canvas.scene()
    assert state.history is history
    assert state.redo_stack is redo_stack
    assert state.history == [history_sentinel]
    assert state.redo_stack == [redo_sentinel, command]


def test_move_atoms_access_exact_restore_survives_partial_bulk_rollback_baseexception() -> (
    None
):
    canvas = _Canvas()
    atoms = {
        7: SimpleNamespace(x=1.0, y=2.0),
        8: SimpleNamespace(x=5.0, y=6.0),
    }
    canvas.model = SimpleNamespace(atoms=atoms, bonds=[])
    coords_3d = {
        7: (1.0, 2.0, 3.0),
        8: (5.0, 6.0, 7.0),
    }
    canvas.atom_coords_3d_state = SimpleNamespace(atom_coords_3d=coords_3d)
    before_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in atoms.items()}
    before_coords = dict(coords_3d)

    def partial_move(_canvas, atom_ids, dx, dy, **_kwargs) -> None:
        for atom_id in atom_ids:
            atom = atoms[atom_id]
            atom.x += dx
            atom.y += dy
            x, y, z = coords_3d[atom_id]
            coords_3d[atom_id] = (x + dx, y + dy, z)
        raise RuntimeError("primary atom move failure")

    def partial_restore(
        _canvas, positions, *, update_selection, coords_3d=None
    ) -> None:
        del update_selection
        atom_id = 7
        atoms[atom_id].x, atoms[atom_id].y = positions[atom_id]
        if coords_3d is not None:
            canvas.atom_coords_3d_state.atom_coords_3d[atom_id] = coords_3d[atom_id]
        raise SystemExit("persistent atom rollback termination")

    with (
        mock.patch("ui.history_canvas_access.move_atoms_for", side_effect=partial_move),
        mock.patch(
            "ui.history_canvas_access.set_atom_positions_for_history",
            side_effect=partial_restore,
        ),
        pytest.raises(RuntimeError, match="primary atom move failure") as caught,
    ):
        move_atoms_for_history(canvas, {7, 8}, 4.0, 9.0)

    assert {
        atom_id: (atom.x, atom.y) for atom_id, atom in atoms.items()
    } == before_positions
    assert coords_3d == before_coords
    assert any(
        "SystemExit: persistent atom rollback termination" in note
        for note in getattr(caught.value, "__notes__", [])
    )


def test_move_items_restores_exact_outline_runtime_after_persistent_refresh_failure() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    item = _SceneItem("moved")
    canvas.scene().attach(item)
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )

    def move_item(_canvas, target, dx, dy, *, update_selection) -> None:
        assert not update_selection
        target.x += dx
        target.y += dy

    command = MoveItemsCommand([item], 4.0, 9.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_item),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert (item.x, item.y) == (0.0, 0.0)
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )


def test_move_rollback_uses_raw_savepoint_when_canonical_apply_mutates_then_raises() -> (
    None
):
    canvas = _Canvas()
    items = [_RawStateSceneItem("first"), _RawStateSceneItem("second")]
    for index, item in enumerate(items):
        item.x = float(index)
        item.metadata_x = float(index)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    move_failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "test", "x": item.x, "metadata_x": item.metadata_x}

    def partially_failing_apply(_canvas, item, state) -> None:
        item.x = state["x"] + 100.0
        item.metadata_x = state["metadata_x"] + 100.0
        raise RuntimeError("canonical apply failed after mutation")

    def move_with_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal move_failed
        assert not update_selection
        item.x += dx
        item.metadata_x += dx
        if item is items[1] and not move_failed:
            move_failed = True
            raise RuntimeError("move failed after mutation")

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for", side_effect=snapshot_state
        ),
        mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=partially_failing_apply,
        ),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="move failed after mutation"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


def test_move_rollback_restores_raw_orbital_center_before_canonical_apply() -> None:
    canvas = _Canvas()
    items = [_RawStateSceneItem("first"), _RawStateSceneItem("second")]
    for index, item in enumerate(items, start=1):
        item.x = float(index)
        item.metadata_x = float(index * 10)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    move_failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "orbital", "center": item.metadata_x}

    def apply_orbital_state(_canvas, item, state) -> None:
        desired_center = state["center"]
        item.x += desired_center - item.metadata_x
        item.metadata_x = desired_center

    def move_before_center_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal move_failed
        assert not update_selection
        item.x += dx
        if item is items[1] and not move_failed:
            move_failed = True
            raise RuntimeError("orbital move failed before center update")
        item.metadata_x += dx

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for", side_effect=snapshot_state
        ),
        mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=apply_orbital_state,
        ),
        mock.patch(
            "ui.history_commands.move_item_for", side_effect=move_before_center_failure
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="before center update"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


@pytest.mark.parametrize("kind", ["arrow", "ts_bracket"])
def test_move_exact_restore_is_final_after_canonical_absolute_path_repair(
    kind: str,
) -> None:
    class AbsolutePathSceneItem(_RawStateSceneItem):
        def path(self) -> float:
            return self.geometry_x

        def setPath(self, path: float) -> None:
            self.geometry_x = path

    canvas = _Canvas()
    item = AbsolutePathSceneItem(kind)
    item.x = 3.0
    item.metadata_x = 13.0
    item.geometry_x = 10.0
    canvas.scene().attach(item)

    def snapshot_state(_canvas, current_item):
        return {"kind": kind, "absolute_x": current_item.metadata_x}

    def apply_absolute_state(_canvas, current_item, state) -> None:
        current_item.x = 0.0
        current_item.geometry_x = state["absolute_x"]
        current_item.metadata_x = state["absolute_x"]

    def move_then_fail(_canvas, current_item, dx, _dy, *, update_selection) -> None:
        assert not update_selection
        current_item.x += dx
        current_item.metadata_x += dx
        raise RuntimeError("absolute item move failed")

    command = MoveItemsCommand([item], 4.0, 0.0)
    with (
        mock.patch(
            "ui.history_commands.scene_item_state_for", side_effect=snapshot_state
        ),
        mock.patch(
            "ui.history_commands._apply_scene_item_state",
            side_effect=apply_absolute_state,
        ),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_then_fail),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="absolute item move failed"),
    ):
        command.redo(canvas)

    assert item.x == 3.0
    assert item.geometry_x == 10.0
    assert item.metadata_x == 13.0


@pytest.mark.parametrize("method_name", ["redo", "undo"])
@pytest.mark.parametrize("failure_point", ["apply", "refresh"])
def test_update_scene_item_command_compensates_current_child_failure(
    method_name: str,
    failure_point: str,
) -> None:
    before_state = {"value": 1}
    after_state = {"value": 2}
    target_state = after_state if method_name == "redo" else before_state
    rollback_state = before_state if method_name == "redo" else after_state
    canvas = SimpleNamespace(value=rollback_state["value"])
    command = UpdateSceneItemCommand("item", before_state, after_state)
    apply_failed = False
    refresh_failed = False

    def apply_state(_canvas, _item, state) -> None:
        nonlocal apply_failed
        canvas.value = state["value"]
        if failure_point == "apply" and state is target_state and not apply_failed:
            apply_failed = True
            raise RuntimeError("scene apply failed after mutation")

    def refresh(_canvas) -> None:
        nonlocal refresh_failed
        if failure_point == "refresh" and not refresh_failed:
            refresh_failed = True
            raise RuntimeError("refresh failed after scene apply")

    with (
        mock.patch(
            "ui.history_commands._apply_scene_item_state", side_effect=apply_state
        ),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh,
        ),
        pytest.raises(RuntimeError, match="failed"),
    ):
        getattr(command, method_name)(canvas)

    assert canvas.value == rollback_state["value"]


def test_update_scene_item_restores_old_outline_objects_when_refresh_rebuild_fails() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    canvas.value = 1
    old_outline = _SceneItem("old-outline")
    canvas.scene().attach(old_outline)
    outlines = [old_outline]
    canvas.selection_outline_state.outlines = outlines
    partial_outlines: list[_SceneItem] = []

    def apply_state(_canvas, _item, state) -> None:
        canvas.value = state["value"]

    def refresh_then_fail(_canvas) -> None:
        for outline in list(canvas.selection_outline_state.outlines):
            canvas.scene().detach(outline)
        partial = _SceneItem(f"partial-{len(partial_outlines)}")
        partial_outlines.append(partial)
        canvas.scene().attach(partial)
        canvas.selection_outline_state.outlines = [partial]
        raise RuntimeError("outline rebuild failed after clear")

    command = UpdateSceneItemCommand("item", {"value": 1}, {"value": 2})
    with (
        mock.patch(
            "ui.history_commands._apply_scene_item_state", side_effect=apply_state
        ),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="outline rebuild failed after clear"),
    ):
        command.redo(canvas)

    assert canvas.value == 1
    assert canvas.selection_outline_state.outlines is outlines
    assert outlines == [old_outline]
    assert canvas.scene().items() == [old_outline]
    assert all(partial.scene() is None for partial in partial_outlines)


@pytest.mark.parametrize("method_name", ["redo", "undo"])
def test_change_atom_label_command_compensates_smiles_failure_after_label_mutation(
    method_name: str,
) -> None:
    before = ("C", False, "before")
    after = ("N", True, "after")
    target = after if method_name == "redo" else before
    rollback = before if method_name == "redo" else after
    canvas = SimpleNamespace(
        element=rollback[0], explicit_label=rollback[1], smiles=rollback[2]
    )
    command = ChangeAtomLabelCommand(
        atom_id=7,
        before_element=before[0],
        after_element=after[0],
        before_explicit_label=before[1],
        after_explicit_label=after[1],
        before_smiles_input=before[2],
        after_smiles_input=after[2],
    )
    smiles_failed = False

    def apply_label(
        _canvas,
        _atom_id,
        element,
        *,
        clear_smiles,
        record,
        allow_merge,
        show_carbon,
    ) -> None:
        assert not clear_smiles
        assert not record
        assert not allow_merge
        canvas.element = element
        canvas.explicit_label = show_carbon

    def apply_smiles(_canvas, value) -> None:
        nonlocal smiles_failed
        canvas.smiles = value
        if value == target[2] and not smiles_failed:
            smiles_failed = True
            raise RuntimeError("smiles failed after label mutation")

    with (
        mock.patch(
            "ui.history_commands.add_or_update_atom_label", side_effect=apply_label
        ),
        mock.patch(
            "ui.history_commands.set_last_smiles_input_for", side_effect=apply_smiles
        ),
        pytest.raises(RuntimeError, match="smiles failed"),
    ):
        getattr(command, method_name)(canvas)

    assert (canvas.element, canvas.explicit_label, canvas.smiles) == rollback


@pytest.mark.parametrize("method_name", ["redo", "undo"])
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_change_atom_label_restores_actual_qt_auto_rect_after_smiles_exit(
    method_name: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    label = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    baseline = QRectF(scene.sceneRect())
    target = ("far", "target")
    rollback = ("near", "rollback")
    before = rollback if method_name == "redo" else target
    after = target if method_name == "redo" else rollback
    canvas = SimpleNamespace(
        scene=lambda: scene,
        element=rollback[0],
        smiles=rollback[1],
    )
    command = ChangeAtomLabelCommand(
        atom_id=7,
        before_element=before[0],
        after_element=after[0],
        before_explicit_label=False,
        after_explicit_label=False,
        before_smiles_input=before[1],
        after_smiles_input=after[1],
    )
    target_smiles_failed = False

    def apply_label(
        _canvas,
        _atom_id,
        element,
        *,
        clear_smiles,
        record,
        allow_merge,
        show_carbon,
    ) -> None:
        assert not clear_smiles
        assert not record
        assert not allow_merge
        assert not show_carbon
        canvas.element = element
        label.setPos(10_000.0 if element == target[0] else 0.0, 0.0)
        scene.sceneRect()

    def set_smiles_then_exit(_canvas, value) -> None:
        nonlocal target_smiles_failed
        canvas.smiles = value
        if value == target[1] and not target_smiles_failed:
            target_smiles_failed = True
            raise error_type("SMILES publication terminated after far label geometry")

    with (
        mock.patch(
            "ui.history_commands.add_or_update_atom_label",
            side_effect=apply_label,
        ),
        mock.patch(
            "ui.history_commands.set_last_smiles_input_for",
            side_effect=set_smiles_then_exit,
        ),
        pytest.raises(
            error_type,
            match="SMILES publication terminated after far label geometry",
        ),
    ):
        getattr(command, method_name)(canvas)

    assert canvas.element == rollback[0]
    assert canvas.smiles == rollback[1]
    assert label.pos().x() == 0.0
    assert scene.sceneRect() == baseline
    assert scene._chemvas_scene_rect_tracker.depth == 0
    future = scene.addRect(QRectF(20_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 20_000.0


def _group_snapshot(canvas) -> tuple[dict[int, CanvasSceneGroup], int, bool]:
    state = group_state_for(canvas)
    return dict(state.groups), state.next_group_id, state.expanding


def test_group_redo_rolls_back_when_second_absorbed_group_removal_mutates_then_raises() -> (
    None
):
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    absorbed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    state.groups.update(absorbed)
    state.next_group_id = 3
    before = _group_snapshot(canvas)
    command = GroupSceneItemsCommand({1, 2, 3}, [], absorbed=absorbed)

    def remove_with_failure(_canvas, group_id):
        removed = state.groups.pop(group_id, None)
        if group_id == 2:
            raise RuntimeError("remove group failed after mutation")
        return removed

    with (
        mock.patch(
            "ui.history_commands.remove_group_for", side_effect=remove_with_failure
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="remove group failed after mutation"),
    ):
        command.redo(canvas)

    assert _group_snapshot(canvas) == before
    assert command.group_id is None


def test_group_undo_rolls_back_when_second_absorbed_group_restore_mutates_then_raises() -> (
    None
):
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    absorbed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    merged = CanvasSceneGroup({1, 2, 3}, [])
    state.groups[3] = merged
    state.next_group_id = 4
    before = _group_snapshot(canvas)
    command = GroupSceneItemsCommand({1, 2, 3}, [], absorbed=absorbed, group_id=3)

    def restore_with_failure(_canvas, group_id, group):
        state.groups[group_id] = group
        if group_id == 2:
            raise RuntimeError("restore group failed after mutation")

    with (
        mock.patch(
            "ui.history_commands.restore_group_for", side_effect=restore_with_failure
        ),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="restore group failed after mutation"),
    ):
        command.undo(canvas)

    assert _group_snapshot(canvas) == before
    assert command.group_id == 3


def test_group_command_restores_exact_outline_runtime_after_persistent_refresh_failure() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    state = group_state_for(canvas)
    absorbed_group = CanvasSceneGroup({1}, [])
    state.groups[1] = absorbed_group
    groups_object = state.groups
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )
    command = GroupSceneItemsCommand(
        {1, 2},
        [],
        absorbed=[(1, absorbed_group)],
    )

    with (
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert state.groups is groups_object
    assert state.groups == {1: absorbed_group}
    assert state.groups[1] is absorbed_group
    assert command.group_id is None
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )


@pytest.mark.parametrize("method_name", ["redo", "undo"])
def test_ungroup_command_rolls_back_when_second_group_mutates_then_raises(
    method_name: str,
) -> None:
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    removed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    if method_name == "redo":
        state.groups.update(removed)
    state.next_group_id = 3
    before = _group_snapshot(canvas)
    command = UngroupSceneItemsCommand(removed)

    def remove_with_failure(_canvas, group_id):
        group = state.groups.pop(group_id, None)
        if group_id == 2:
            raise RuntimeError("remove group failed after mutation")
        return group

    def restore_with_failure(_canvas, group_id, group):
        state.groups[group_id] = group
        if group_id == 2:
            raise RuntimeError("restore group failed after mutation")

    operation = remove_with_failure if method_name == "redo" else restore_with_failure
    operation_name = (
        "remove_group_for" if method_name == "redo" else "restore_group_for"
    )
    error_pattern = (
        "remove group failed" if method_name == "redo" else "restore group failed"
    )
    with (
        mock.patch(f"ui.history_commands.{operation_name}", side_effect=operation),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match=error_pattern),
    ):
        getattr(command, method_name)(canvas)

    assert _group_snapshot(canvas) == before


def test_ungroup_command_restores_exact_outline_runtime_after_persistent_refresh_failure() -> (
    None
):
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    state = group_state_for(canvas)
    removed_group = CanvasSceneGroup({1}, [])
    state.groups[1] = removed_group
    groups_object = state.groups
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )
    command = UngroupSceneItemsCommand([(1, removed_group)])

    with (
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert state.groups is groups_object
    assert state.groups == {1: removed_group}
    assert state.groups[1] is removed_group
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )


@pytest.mark.parametrize(
    "operation",
    ["group_redo", "group_undo", "ungroup_redo", "ungroup_undo"],
)
@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_group_history_restores_actual_qt_auto_rect_after_outline_exit(
    operation: str,
    error_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    state = group_state_for(canvas)
    original_group = CanvasSceneGroup({7}, [])
    if operation in {"group_undo", "ungroup_redo"}:
        state.groups[7] = original_group
    groups_object = state.groups
    groups_before = dict(state.groups)
    next_group_id_before = state.next_group_id
    if operation.startswith("group_"):
        command = GroupSceneItemsCommand(
            {7},
            [],
            group_id=7 if operation == "group_undo" else None,
        )
    else:
        command = UngroupSceneItemsCommand([(7, original_group)])
    method_name = "redo" if operation.endswith("redo") else "undo"
    group_id_before = getattr(command, "group_id", None)
    baseline = QRectF(scene.sceneRect())
    partial_outlines: list[QGraphicsRectItem] = []
    refresh_calls = 0

    def refresh_with_first_exit(_canvas) -> None:
        nonlocal refresh_calls
        refresh_calls += 1
        outline = scene.addRect(QRectF(10_000.0 * refresh_calls, 0.0, 10.0, 10.0))
        partial_outlines.append(outline)
        scene.sceneRect()
        if refresh_calls == 1:
            raise error_type("group outline rebuild terminated after far geometry")

    with (
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_with_first_exit,
        ),
        pytest.raises(
            error_type,
            match="group outline rebuild terminated after far geometry",
        ),
    ):
        getattr(command, method_name)(canvas)

    assert state.groups is groups_object
    assert state.groups == groups_before
    assert state.next_group_id == next_group_id_before
    if isinstance(command, GroupSceneItemsCommand):
        assert command.group_id == group_id_before
    assert all(outline.scene() is None for outline in partial_outlines)
    assert scene.sceneRect() == baseline
    assert scene._chemvas_scene_rect_tracker.depth == 0
    future = scene.addRect(QRectF(30_000.0, 0.0, 10.0, 10.0))
    assert future.scene() is scene
    assert scene.sceneRect().right() > 30_000.0


@pytest.mark.parametrize(
    "operation",
    [
        "group_redo",
        "group_undo",
        "ungroup_redo",
        "ungroup_undo",
        "change_label",
    ],
)
def test_explicit_group_and_label_history_success_never_scans_global_item_bounds(
    operation: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    label = scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = SimpleNamespace(scene=lambda: scene)
    explicit_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
    set_explicit_scene_rect(scene, explicit_rect)
    state = group_state_for(canvas)
    group = CanvasSceneGroup({7}, [])

    if operation == "group_redo":
        command = GroupSceneItemsCommand({7}, [])
        method_name = "redo"
    elif operation == "group_undo":
        state.groups[7] = group
        command = GroupSceneItemsCommand({7}, [], group_id=7)
        method_name = "undo"
    elif operation == "ungroup_redo":
        state.groups[7] = group
        command = UngroupSceneItemsCommand([(7, group)])
        method_name = "redo"
    elif operation == "ungroup_undo":
        command = UngroupSceneItemsCommand([(7, group)])
        method_name = "undo"
    else:
        command = ChangeAtomLabelCommand(
            atom_id=7,
            before_element="near",
            after_element="far",
            before_explicit_label=False,
            after_explicit_label=False,
            before_smiles_input="before",
            after_smiles_input="after",
        )
        method_name = "redo"

    def apply_label(
        _canvas,
        _atom_id,
        element,
        **_kwargs,
    ) -> None:
        label.setPos(25.0 if element == "far" else 0.0, 0.0)

    with (
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        mock.patch(
            "ui.history_commands.add_or_update_atom_label",
            side_effect=apply_label,
        ),
        mock.patch("ui.history_commands.set_last_smiles_input_for"),
        mock.patch.object(
            scene,
            "itemsBoundingRect",
            wraps=scene.itemsBoundingRect,
        ) as bounds_scan,
    ):
        getattr(command, method_name)(canvas)

    assert bounds_scan.call_count == 0
    assert scene.sceneRect() == explicit_rect
