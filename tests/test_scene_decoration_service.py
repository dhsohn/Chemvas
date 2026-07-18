import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.transactions import HistoryStackSnapshot
    from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
    from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
    from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
    from chemvas.ui.history_commands import AddSceneItemsCommand
    from chemvas.ui.scene_decoration_service import SceneDecorationService
    from chemvas.ui.scene_item_lifecycle_service import SceneItemLifecycleService


class _FakeScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)

    def removeItem(self, item) -> None:
        if item in self.items:
            self.items.remove(item)


class _FakeItem:
    def __init__(self) -> None:
        self._data = {}

    def setData(self, key, value) -> None:
        self._data[key] = value

    def data(self, key):
        return self._data.get(key)


class _FakeSceneItemController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def attach_scene_item(self, item) -> None:
        self.canvas.attach_scene_item(item)

    def remove_scene_item(self, item) -> None:
        self.canvas.remove_scene_item(item)

    def create_scene_item_from_state(self, state):
        return self.canvas.create_scene_item_from_state(state)


def _scene_decoration_service(canvas) -> SceneDecorationService:
    return SceneDecorationService(
        canvas,
        history_service=canvas.services.history_service,
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for scene decoration tests"
)
class SceneDecorationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_add_mark_tracks_registry_and_optional_history(self) -> None:
        scene = _FakeScene()
        pushed = []
        text_mark = QGraphicsTextItem("-")
        set_mark_center = mock.Mock(
            side_effect=lambda item, center: item.setPos(center)
        )
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(side_effect=[text_mark, None]),
            set_mark_center=set_mark_center,
        )

        def _attach(item) -> None:
            scene.addItem(item)
            canvas.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            if isinstance(atom_id, int):
                canvas.mark_registry.add_for_atom(atom_id, item)

        canvas = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            mark_items=[],
            mark_registry=CanvasMarkRegistry(),
            attach_scene_item=mock.Mock(side_effect=_attach),
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(push=pushed.append),
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        item = service.add_mark(
            QPointF(4.0, 5.0),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=True,
        )

        self.assertIs(item, text_mark)
        self.assertEqual(item.data(0), "mark")
        self.assertEqual(
            item.data(1),
            {"kind": "minus", "atom_id": 7, "dx": 1.5, "dy": -2.5, "text": "-"},
        )
        self.assertEqual(canvas.mark_items, [item])
        self.assertEqual(canvas.mark_registry.by_atom, {7: [item]})
        self.assertEqual(scene.items, [item])
        canvas.attach_scene_item.assert_called_once_with(item)
        build_service.set_mark_center.assert_called_once_with(item, QPointF(4.0, 5.0))
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], AddSceneItemsCommand)
        self.assertEqual(
            pushed[0].item_states,
            [
                {
                    "kind": "mark",
                    "mark_kind": "minus",
                    "text": "-",
                    "atom_id": 7,
                    "dx": 1.5,
                    "dy": -2.5,
                    "x": 4.0,
                    "y": 5.0,
                }
            ],
        )

        self.assertIsNone(service.add_mark(QPointF(0.0, 0.0), kind="unsupported"))

    def test_history_stack_capture_static_live_descriptor_failure_aborts_and_retries(
        self,
    ) -> None:
        class FailOnceState:
            def __init__(self, source: str, history: list, redo_stack: list) -> None:
                self.source = source
                self._history = history
                self._redo_stack = redo_stack
                self.history_calls = 0
                self.redo_calls = 0

            @property
            def history(self):
                self.history_calls += 1
                if self.source == "history" and self.history_calls == 1:
                    raise AttributeError("live history descriptor failed internally")
                return self._history

            @history.setter
            def history(self, value) -> None:
                self._history = value

            @property
            def redo_stack(self):
                self.redo_calls += 1
                if self.source == "redo_stack" and self.redo_calls == 1:
                    raise AttributeError("live redo descriptor failed internally")
                return self._redo_stack

            @redo_stack.setter
            def redo_stack(self, value) -> None:
                self._redo_stack = value

        class HistoryService:
            def __init__(self, source: str, state: object) -> None:
                self.source = source
                self._state = state
                self.state_calls = 0
                self.notify_change = mock.Mock()

            @property
            def state(self):
                self.state_calls += 1
                if self.source == "state" and self.state_calls == 1:
                    raise AttributeError(
                        "live history state descriptor failed internally"
                    )
                return self._state

        for source in ("state", "history", "redo_stack"):
            with self.subTest(source=source):
                undo_marker = object()
                redo_marker = object()
                undo_stack = [undo_marker]
                redo_stack = [redo_marker]
                state = FailOnceState(source, undo_stack, redo_stack)
                history = HistoryService(source, state)
                with self.assertRaisesRegex(AttributeError, "descriptor failed"):
                    HistoryStackSnapshot.capture(history)

                self.assertEqual(undo_stack, [undo_marker])
                self.assertEqual(redo_stack, [redo_marker])
                snapshot = HistoryStackSnapshot.capture(history)
                self.assertIsNotNone(snapshot)
                assert snapshot is not None
                undo_stack.append("transient")
                redo_stack.clear()
                primary = KeyboardInterrupt("history append interrupted")
                snapshot.restore(primary, phase="descriptor retry")

                self.assertIs(state.history, undo_stack)
                self.assertIs(state.redo_stack, redo_stack)
                self.assertEqual(undo_stack, [undo_marker])
                self.assertEqual(redo_stack, [redo_marker])
                history.notify_change.assert_called_once_with()

    def test_scene_decoration_history_state_descriptor_failure_precedes_build_and_retries(
        self,
    ) -> None:
        undo_stack: list[object] = []
        redo_stack: list[object] = []
        history_state = SimpleNamespace(history=undo_stack, redo_stack=redo_stack)

        class FailOnceHistoryService:
            state_calls = 0

            def __init__(self) -> None:
                self.push = mock.Mock(side_effect=undo_stack.append)

            @property
            def state(self):
                self.state_calls += 1
                if self.state_calls == 1:
                    raise AttributeError(
                        "live decoration history state failed internally"
                    )
                return history_state

        history = FailOnceHistoryService()
        mark_items: list[QGraphicsTextItem] = []
        mark_registry = CanvasMarkRegistry()
        mark = QGraphicsTextItem("+")
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(return_value=mark),
            set_mark_center=mock.Mock(
                side_effect=lambda item, center: item.setPos(center)
            ),
        )

        def attach(item) -> None:
            mark_items.append(item)
            mark_registry.add_for_atom(7, item)

        canvas = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            scene_items_state=CanvasSceneItemsState(mark_items=mark_items),
            mark_items=mark_items,
            mark_registry=mark_registry,
            attach_scene_item=mock.Mock(side_effect=attach),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        with self.assertRaisesRegex(
            AttributeError,
            "live decoration history state failed internally",
        ):
            service.add_mark(QPointF(1.0, 2.0), atom_id=7, record=True)

        build_service.build_mark_item.assert_not_called()
        canvas.attach_scene_item.assert_not_called()
        history.push.assert_not_called()
        self.assertEqual(mark_items, [])

        created = service.add_mark(QPointF(3.0, 4.0), atom_id=7, record=True)

        self.assertIs(created, mark)
        build_service.build_mark_item.assert_called_once_with("plus")
        canvas.attach_scene_item.assert_called_once_with(mark)
        history.push.assert_called_once()
        self.assertEqual(mark_items, [mark])
        self.assertEqual(len(undo_stack), 1)

    def test_add_mark_removes_attached_item_if_centering_raises(self) -> None:
        scene = _FakeScene()
        text_mark = QGraphicsTextItem("-")
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(return_value=text_mark),
            set_mark_center=mock.Mock(side_effect=RuntimeError("center failed")),
        )
        removed = []

        def _attach(item) -> None:
            scene.addItem(item)
            canvas.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            if isinstance(atom_id, int):
                canvas.mark_registry.add_for_atom(atom_id, item)

        def _remove(item) -> None:
            removed.append(item)
            scene.removeItem(item)
            if item in canvas.mark_items:
                canvas.mark_items.remove(item)
            for atom_id, items in list(canvas.mark_registry.by_atom.items()):
                if item in items:
                    items.remove(item)
                if not items:
                    canvas.mark_registry.by_atom.pop(atom_id, None)

        canvas = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            mark_items=[],
            mark_registry=CanvasMarkRegistry(),
            attach_scene_item=mock.Mock(side_effect=_attach),
            remove_scene_item=mock.Mock(side_effect=_remove),
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(push=mock.Mock()),
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        with self.assertRaisesRegex(RuntimeError, "center failed"):
            service.add_mark(QPointF(4.0, 5.0), kind="minus", atom_id=7, record=False)

        self.assertEqual(scene.items, [])
        self.assertEqual(canvas.mark_items, [])
        self.assertEqual(canvas.mark_registry.by_atom, {})
        self.assertEqual(removed, [text_mark])
        canvas.services.history_service.push.assert_not_called()

    def test_live_item_scene_override_is_bypassed_by_qt_base_membership_port(
        self,
    ) -> None:
        primary = RuntimeError("new mark scene lookup failed")

        class FailOnceSceneMark(QGraphicsTextItem):
            scene_calls = 0

            def scene(self):
                self.scene_calls += 1
                if self.scene_calls == 1:
                    raise primary
                return super().scene()

        scene = QGraphicsScene()
        mark = FailOnceSceneMark("+")
        mark_items: list[QGraphicsTextItem] = []
        scene_items_state = CanvasSceneItemsState(mark_items=mark_items)
        mark_mapping: dict[int, list[QGraphicsTextItem]] = {}
        mark_registry = CanvasMarkRegistry(mark_mapping)
        history_marker = object()
        redo_marker = object()
        history_stack = [history_marker]
        redo_stack = [redo_marker]
        history_state = SimpleNamespace(
            history=history_stack,
            redo_stack=redo_stack,
        )
        history = SimpleNamespace(
            state=history_state,
            push=mock.Mock(),
            notify_change=mock.Mock(),
        )
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(return_value=mark),
            set_mark_center=mock.Mock(),
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
            mark_registry=mark_registry,
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_decoration_build_service=build_service,
        )
        lifecycle = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
        )
        canvas.services.scene_item_controller = lifecycle

        result = _scene_decoration_service(canvas).add_mark(
            QPointF(4.0, 5.0),
            kind="plus",
            atom_id=7,
        )

        self.assertIs(result, mark)
        self.assertEqual(mark.scene_calls, 0)
        self.assertIs(scene_items_state.mark_items, mark_items)
        self.assertEqual(mark_items, [mark])
        self.assertIs(mark_registry.by_atom, mark_mapping)
        self.assertEqual(mark_mapping, {7: [mark]})
        self.assertIn(mark, scene.items())
        self.assertIs(history_state.history, history_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(history_stack, [history_marker])
        self.assertEqual(redo_stack, [redo_marker])
        history.push.assert_called_once()
        build_service.set_mark_center.assert_called_once_with(
            mark,
            QPointF(4.0, 5.0),
        )

    def test_live_canvas_scene_failure_aborts_decoration_before_history_commit(
        self,
    ) -> None:
        scene = QGraphicsScene()
        mark = QGraphicsTextItem("+")
        scene_items_state = CanvasSceneItemsState()
        mark_registry = CanvasMarkRegistry()
        history_marker = object()
        redo_marker = object()
        history_stack = [history_marker]
        redo_stack = [redo_marker]
        history_state = SimpleNamespace(
            history=history_stack,
            redo_stack=redo_stack,
        )
        history = SimpleNamespace(
            state=history_state,
            push=mock.Mock(),
            notify_change=mock.Mock(),
        )
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(return_value=mark),
            set_mark_center=mock.Mock(),
        )

        class Canvas(SimpleNamespace):
            scene_calls = 0

            def scene(self):
                self.scene_calls += 1
                if self.scene_calls == 2:
                    raise RuntimeError("live canvas scene lookup failed")
                return scene

        canvas = Canvas(
            scene_items_state=scene_items_state,
            mark_registry=mark_registry,
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_decoration_build_service=build_service,
        )
        lifecycle = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
        )
        canvas.services.scene_item_controller = lifecycle

        with self.assertRaisesRegex(
            RuntimeError,
            "live canvas scene lookup failed",
        ):
            _scene_decoration_service(canvas).add_mark(
                QPointF(4.0, 5.0),
                kind="plus",
                atom_id=7,
            )

        self.assertEqual(scene_items_state.mark_items, [])
        self.assertEqual(mark_registry.by_atom, {})
        self.assertNotIn(mark, scene.items())
        self.assertIs(history_state.history, history_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(history_stack, [history_marker])
        self.assertEqual(redo_stack, [redo_marker])
        history.push.assert_not_called()
        build_service.set_mark_center.assert_not_called()

    def test_add_mark_keyboard_interrupt_restores_scene_registries_and_history_identity(
        self,
    ) -> None:
        scene = QGraphicsScene()
        sibling = QGraphicsTextItem("sibling")
        sibling.setData(0, "mark")
        sibling.setData(1, {"atom_id": 7})
        scene.addItem(sibling)
        mark_items = [sibling]
        scene_items_state = CanvasSceneItemsState(mark_items=mark_items)
        sibling_marks = [sibling]
        mark_mapping = {7: sibling_marks}
        mark_registry = CanvasMarkRegistry(mark_mapping)
        new_mark = QGraphicsTextItem("+")

        old_command = object()
        old_redo = object()
        undo_stack = [old_command]
        redo_stack = [old_redo]
        history_state = SimpleNamespace(history=undo_stack, redo_stack=redo_stack)

        def append_then_interrupt(command) -> None:
            history_state.history.append(command)
            history_state.redo_stack.clear()
            raise KeyboardInterrupt("history interrupted")

        history = SimpleNamespace(
            state=history_state,
            push=append_then_interrupt,
            notify_change=mock.Mock(),
        )

        def attach(item) -> None:
            scene.addItem(item)
            mark_items.append(item)
            mark_registry.add_for_atom(7, item)

        def remove(item) -> None:
            if item in mark_items:
                mark_items.remove(item)
            marks = mark_registry.by_atom.get(7)
            if marks is not None and item in marks:
                marks.remove(item)
            if item.scene() is scene:
                scene.removeItem(item)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
            mark_registry=mark_registry,
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            attach_scene_item=attach,
            remove_scene_item=remove,
        )
        canvas.services = SimpleNamespace(
            history_service=history,
            scene_decoration_build_service=SimpleNamespace(
                build_mark_item=mock.Mock(return_value=new_mark),
                set_mark_center=mock.Mock(
                    side_effect=lambda item, pos: item.setPos(pos)
                ),
            ),
            scene_item_controller=_FakeSceneItemController(canvas),
        )

        with self.assertRaisesRegex(KeyboardInterrupt, "history interrupted"):
            _scene_decoration_service(canvas).add_mark(
                QPointF(4.0, 5.0),
                kind="plus",
                atom_id=7,
            )

        self.assertIs(scene_items_state.mark_items, mark_items)
        self.assertEqual(mark_items, [sibling])
        self.assertIs(mark_registry.by_atom, mark_mapping)
        self.assertIs(mark_mapping[7], sibling_marks)
        self.assertEqual(sibling_marks, [sibling])
        self.assertNotIn(new_mark, scene.items())
        self.assertIs(history_state.history, undo_stack)
        self.assertIs(history_state.redo_stack, redo_stack)
        self.assertEqual(undo_stack, [old_command])
        self.assertEqual(redo_stack, [old_redo])

    def test_add_orbital_system_exit_after_attach_restores_scene_rect_and_registries(
        self,
    ) -> None:
        scene = QGraphicsScene()
        scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
        original_scene_rect = scene.sceneRect()
        orbital_items = []
        scene_items_state = CanvasSceneItemsState(orbital_items=orbital_items)
        attached_groups = []

        def build_orbital_items(center, _kind: str):
            child = QGraphicsTextItem("orbital")
            child.setPos(center)
            return [child]

        def attach_then_exit(group) -> None:
            attached_groups.append(group)
            scene.addItem(group)
            orbital_items.append(group)
            self.assertEqual(scene.sceneRect(), original_scene_rect)
            raise SystemExit("orbital attach terminated")

        def remove(group) -> None:
            if group in orbital_items:
                orbital_items.remove(group)
            if group.scene() is scene:
                scene.removeItem(group)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
            tool_settings_state=CanvasToolSettingsState(active_orbital_type="p"),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            attach_scene_item=mock.Mock(side_effect=attach_then_exit),
            remove_scene_item=mock.Mock(side_effect=remove),
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(
                state=SimpleNamespace(history=[], redo_stack=[]),
                push=mock.Mock(),
            ),
            scene_decoration_build_service=SimpleNamespace(
                build_orbital_items=build_orbital_items,
            ),
            scene_item_controller=_FakeSceneItemController(canvas),
        )

        with self.assertRaisesRegex(SystemExit, "orbital attach terminated"):
            _scene_decoration_service(canvas).add_orbital(QPointF(10_000.0, 0.0))

        self.assertIs(scene_items_state.orbital_items, orbital_items)
        self.assertEqual(orbital_items, [])
        self.assertEqual(len(attached_groups), 1)
        self.assertNotIn(attached_groups[0], scene.items())
        self.assertEqual(scene.sceneRect(), original_scene_rect)
        future = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 20_000.0)
        scene.removeItem(future)
        canvas.services.history_service.push.assert_not_called()

    def test_bulk_unrecorded_marks_never_scan_existing_scene_items(self) -> None:
        scene = QGraphicsScene()
        scene_items_state = CanvasSceneItemsState()
        mark_registry = CanvasMarkRegistry()

        def build_mark(_kind: str) -> QGraphicsTextItem:
            return QGraphicsTextItem("+")

        def attach(item) -> None:
            scene.addItem(item)
            scene_items_state.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int):
                mark_registry.add_for_atom(atom_id, item)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=scene_items_state,
            mark_registry=mark_registry,
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            attach_scene_item=attach,
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(
                state=SimpleNamespace(history=[], redo_stack=[]),
                push=mock.Mock(),
            ),
            scene_decoration_build_service=SimpleNamespace(
                build_mark_item=build_mark,
                set_mark_center=lambda item, pos: item.setPos(pos),
            ),
            scene_item_controller=_FakeSceneItemController(canvas),
        )

        with (
            mock.patch(
                "chemvas.ui.history_commands._scene_items_snapshot",
                side_effect=AssertionError("bulk mark add scanned the whole scene"),
            ) as scene_scan,
            mock.patch(
                "chemvas.ui.scene_decoration_service.HistoryAuthoritySnapshot.capture",
                side_effect=AssertionError("unrecorded mark copied history"),
            ) as history_scan,
        ):
            service = _scene_decoration_service(canvas)
            for atom_id in range(200):
                service.add_mark(
                    QPointF(float(atom_id), 0.0),
                    kind="plus",
                    atom_id=atom_id,
                    record=False,
                )

        scene_scan.assert_not_called()
        history_scan.assert_not_called()
        self.assertEqual(len(scene_items_state.mark_items), 200)
        self.assertEqual(len(mark_registry.by_atom), 200)

    def test_add_arrow_and_ts_bracket_register_items_and_push_history(self) -> None:
        scene = _FakeScene()
        pushed = []
        arrow_item = _FakeItem()
        arrow_item.setData(2, {"control": QPointF(2.0, 3.0)})
        ts_item = _FakeItem()
        ts_item.setData(0, "ts_bracket")
        build_service = SimpleNamespace(
            build_arrow_item=mock.Mock(return_value=arrow_item),
            build_ts_bracket_item=mock.Mock(return_value=ts_item),
        )

        def _attach(item) -> None:
            scene.addItem(item)
            kind = item.data(0)
            if kind == "ts_bracket":
                canvas.ts_bracket_items.append(item)
            else:
                canvas.arrow_items.append(item)

        canvas = SimpleNamespace(
            arrow_items=[],
            ts_bracket_items=[],
            attach_scene_item=mock.Mock(side_effect=_attach),
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(push=pushed.append),
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        arrow = service.add_arrow(QPointF(1.0, 2.0), QPointF(6.0, 7.0), "curved_double")
        ts_bracket = service.add_ts_bracket(
            QRectF(QPointF(0.0, 0.0), QPointF(4.0, 8.0))
        )

        self.assertIs(arrow, arrow_item)
        self.assertEqual(arrow.data(0), "curved_double")
        self.assertEqual(arrow.data(2)["start"], QPointF(1.0, 2.0))
        self.assertEqual(arrow.data(2)["end"], QPointF(6.0, 7.0))
        self.assertTrue(arrow.data(2)["double"])
        self.assertIs(ts_bracket, ts_item)
        self.assertEqual(canvas.arrow_items, [arrow_item])
        self.assertEqual(canvas.ts_bracket_items, [ts_item])
        self.assertEqual(scene.items, [arrow_item, ts_item])
        self.assertEqual(
            canvas.attach_scene_item.call_args_list,
            [mock.call(arrow_item), mock.call(ts_item)],
        )
        self.assertEqual(len(pushed), 2)
        self.assertTrue(
            all(isinstance(command, AddSceneItemsCommand) for command in pushed)
        )

    def test_add_orbital_builds_before_attach_and_skips_empty_builds(self) -> None:
        pushed = []
        scene = QGraphicsScene()
        orbital_items = []
        built_child = QGraphicsTextItem("orbital")
        build_orbital_items = mock.Mock(side_effect=[[], [built_child]])

        def attach(group) -> None:
            scene.addItem(group)
            orbital_items.append(group)

        canvas = SimpleNamespace(
            scene=lambda: scene,
            scene_items_state=CanvasSceneItemsState(orbital_items=orbital_items),
            tool_settings_state=CanvasToolSettingsState(active_orbital_type="p"),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            attach_scene_item=mock.Mock(side_effect=attach),
        )
        canvas.services = SimpleNamespace(
            history_service=SimpleNamespace(push=pushed.append),
            scene_decoration_build_service=SimpleNamespace(
                build_orbital_items=build_orbital_items,
            ),
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        self.assertIsNone(service.add_orbital(QPointF(1.0, 2.0)))
        result = service.add_orbital(QPointF(3.0, 4.0))

        self.assertIsNotNone(result)
        self.assertIs(result, orbital_items[0])
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], AddSceneItemsCommand)
        self.assertEqual(
            pushed[0].item_states,
            [
                {
                    "kind": "orbital",
                    "orbital_kind": "p",
                    "center": (3.0, 4.0),
                    "scale": 1.0,
                    "rotation": 0.0,
                }
            ],
        )
        self.assertEqual(
            build_orbital_items.call_args_list,
            [
                mock.call(QPointF(1.0, 2.0), "p"),
                mock.call(QPointF(3.0, 4.0), "p"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
