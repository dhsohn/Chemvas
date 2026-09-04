import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsTextItem

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


class SceneDecorationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_add_mark_tracks_registry_and_optional_history(self) -> None:
        scene = _FakeScene()
        pushed = []
        text_mark = QGraphicsTextItem("-")
        scene_items_state = CanvasSceneItemsState()
        mark_registry = CanvasMarkRegistry()
        set_mark_center = mock.Mock(
            side_effect=lambda item, center: item.setPos(center)
        )
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(side_effect=[text_mark, None]),
            set_mark_center=set_mark_center,
            # Inverse of this double's set_mark_center, so serializing the new
            # mark reads back the centre add_mark was given.
            mark_center=lambda item: item.pos(),
        )

        def _attach(item) -> None:
            scene.addItem(item)
            scene_items_state.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            if isinstance(atom_id, int):
                mark_registry.add_for_atom(atom_id, item)

        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: object()}, atom_annotations={}),
            runtime_state=canvas_runtime_state(
                tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
                scene_items_state=scene_items_state,
                mark_registry=mark_registry,
            ),
            attach_scene_item=mock.Mock(side_effect=_attach),
        )
        canvas.services = canvas_runtime_services(
            history_service=SimpleNamespace(push=pushed.append),
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        with mock.patch(
            "chemvas.ui.scene_decoration_service.emit_selection_info_for"
        ) as emit_info:
            item = service.add_mark(
                QPointF(4.0, 5.0),
                kind="minus",
                atom_id=7,
                offset=QPointF(1.5, -2.5),
                record=True,
            )
        # An atom-bound mark changes the selection formula readout; the add
        # must refresh it in place.
        emit_info.assert_called_once_with(canvas)

        self.assertIs(item, text_mark)
        self.assertEqual(item.data(0), "mark")
        self.assertEqual(
            item.data(1),
            {"kind": "minus", "atom_id": 7, "dx": 1.5, "dy": -2.5, "text": "-"},
        )
        self.assertEqual(scene_items_state.mark_items, [item])
        self.assertEqual(mark_registry.by_atom, {7: [item]})
        self.assertEqual(scene.items, [item])
        canvas.attach_scene_item.assert_called_once_with(item)
        build_service.set_mark_center.assert_called_once_with(item, QPointF(4.0, 5.0))
        self.assertEqual(canvas.model.atom_annotations, {7: {"formal_charge": -1}})
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

    def test_add_mark_removes_attached_item_if_centering_raises(self) -> None:
        scene = _FakeScene()
        text_mark = QGraphicsTextItem("-")
        scene_items_state = CanvasSceneItemsState()
        mark_registry = CanvasMarkRegistry()
        build_service = SimpleNamespace(
            build_mark_item=mock.Mock(return_value=text_mark),
            set_mark_center=mock.Mock(side_effect=RuntimeError("center failed")),
        )
        removed = []

        def _attach(item) -> None:
            scene.addItem(item)
            scene_items_state.mark_items.append(item)
            data = item.data(1) or {}
            atom_id = data.get("atom_id") if isinstance(data, dict) else None
            if isinstance(atom_id, int):
                mark_registry.add_for_atom(atom_id, item)

        def _remove(item) -> None:
            removed.append(item)
            scene.removeItem(item)
            if item in scene_items_state.mark_items:
                scene_items_state.mark_items.remove(item)
            for atom_id, items in list(mark_registry.by_atom.items()):
                if item in items:
                    items.remove(item)
                if not items:
                    mark_registry.by_atom.pop(atom_id, None)

        canvas = SimpleNamespace(
            runtime_state=canvas_runtime_state(
                tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
                scene_items_state=scene_items_state,
                mark_registry=mark_registry,
            ),
            attach_scene_item=mock.Mock(side_effect=_attach),
            remove_scene_item=mock.Mock(side_effect=_remove),
        )
        canvas.services = canvas_runtime_services(
            history_service=SimpleNamespace(push=mock.Mock()),
            scene_decoration_build_service=build_service,
            scene_item_controller=_FakeSceneItemController(canvas),
        )
        service = _scene_decoration_service(canvas)

        with self.assertRaisesRegex(RuntimeError, "center failed"):
            service.add_mark(QPointF(4.0, 5.0), kind="minus", atom_id=7, record=False)

        self.assertEqual(scene.items, [])
        self.assertEqual(scene_items_state.mark_items, [])
        self.assertEqual(mark_registry.by_atom, {})
        self.assertEqual(removed, [text_mark])
        canvas.services.history_service.push.assert_not_called()

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
            runtime_state=canvas_runtime_state(
                scene_items_state=scene_items_state,
                mark_registry=mark_registry,
                tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            ),
        )
        canvas.services = canvas_runtime_services(
            history_service=history,
            scene_decoration_build_service=build_service,
        )
        lifecycle = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
        )
        canvas.services.scene_view.scene_item_controller = lifecycle

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
            runtime_state=canvas_runtime_state(
                scene_items_state=scene_items_state,
                mark_registry=mark_registry,
                tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
            ),
            attach_scene_item=attach,
        )
        canvas.services = canvas_runtime_services(
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
                "chemvas.ui.transactions.scene_runtime._scene_items_snapshot",
                side_effect=AssertionError("bulk mark add scanned the whole scene"),
            ) as scene_scan,
            mock.patch("chemvas.ui.scene_decoration_service.emit_selection_info_for"),
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

        scene_items_state = CanvasSceneItemsState()

        def _attach(item) -> None:
            scene.addItem(item)
            kind = item.data(0)
            if kind == "ts_bracket":
                scene_items_state.ts_bracket_items.append(item)
            else:
                scene_items_state.arrow_items.append(item)

        canvas = SimpleNamespace(
            runtime_state=canvas_runtime_state(
                scene_items_state=scene_items_state,
                tool_settings_state=CanvasToolSettingsState(),
            ),
            attach_scene_item=mock.Mock(side_effect=_attach),
        )
        canvas.services = canvas_runtime_services(
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
        self.assertEqual(scene_items_state.arrow_items, [arrow_item])
        self.assertEqual(scene_items_state.ts_bracket_items, [ts_item])
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
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState(orbital_items=orbital_items),
                tool_settings_state=CanvasToolSettingsState(active_orbital_type="p"),
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            attach_scene_item=mock.Mock(side_effect=attach),
        )
        canvas.services = canvas_runtime_services(
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
