import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import sip
    from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItemGroup,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_scene_items_state import (
        SCENE_ITEM_COLLECTION_ATTRS,
        scene_item_collection_for,
        set_scene_item_collection_for,
    )
    from ui.handle_state import CanvasHandleState
    from ui.scene_item_attach_snapshot import (
        SceneItemAttachPorts,
        SceneItemAttachSnapshot,
    )
    from ui.scene_item_controller import SceneItemController
    from ui.scene_rect_snapshot import scene_rect_is_automatic


class _FakeCanvas:
    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(bond_length_px=20.0, bond_color="#000000"),
            ring_fill_brush=lambda: QBrush(QColor("#AA4400")),
        )
        self.bond_renderer = SimpleNamespace(
            update_bond_geometry=self.update_bond_geometry
        )
        self.model = SimpleNamespace(atoms={})
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            set_scene_item_collection_for(self, name, [])
        self.mark_registry = CanvasMarkRegistry()
        self.handle_state = CanvasHandleState()
        self.make_selectable_calls = []
        self.updated_bond_ids = []
        self.bond_lookup = {}
        self.removed_mark_items = []
        self.updated_note_boxes = []
        self.clear_handles_calls = 0
        self.applied_note_style_items = []
        self.mark_centers = {}
        self.built_mark_kinds = []
        self.built_arrow_calls = []
        self.curved_arrow_path_calls = []
        self.built_ts_bracket_rects = []
        self.built_orbital_calls = []
        self.services = SimpleNamespace(
            canvas_graph_service=SimpleNamespace(bond_id_between=self.bond_id_between),
            note_controller=SimpleNamespace(
                apply_note_style=self.record_note_style_applied
            ),
            selection_controller=SimpleNamespace(
                update_note_selection_box=self.record_note_selection_box_updated
            ),
            scene_decoration_build_service=SimpleNamespace(
                build_mark_item=self.record_build_mark_item,
                set_mark_center=self.record_set_mark_center,
                build_arrow_item=self.record_build_arrow_item,
                build_ts_bracket_item=self.record_build_ts_bracket_item,
                build_orbital_items=self.record_build_orbital_items,
                ts_bracket_path=self.record_ts_bracket_path,
            ),
            canvas_mark_scene_service=SimpleNamespace(
                remove_mark_item=self.record_remove_mark_item
            ),
            handle_overlay_service=SimpleNamespace(clear_handles=self.clear_handles),
            curved_arrow_path_service=SimpleNamespace(
                set_curved_arrow_path=self.record_set_curved_arrow_path
            ),
        )

    def scene(self):
        return self._scene

    def _scene_items(self, name: str):
        return scene_item_collection_for(self, name)

    def _set_scene_items(self, name: str, value) -> None:
        set_scene_item_collection_for(self, name, value)

    selected_notes = property(
        lambda self: self._scene_items("selected_notes"),
        lambda self, value: self._set_scene_items("selected_notes", value),
    )
    ring_items = property(
        lambda self: self._scene_items("ring_items"),
        lambda self, value: self._set_scene_items("ring_items", value),
    )
    note_items = property(
        lambda self: self._scene_items("note_items"),
        lambda self, value: self._set_scene_items("note_items", value),
    )
    mark_items = property(
        lambda self: self._scene_items("mark_items"),
        lambda self, value: self._set_scene_items("mark_items", value),
    )
    arrow_items = property(
        lambda self: self._scene_items("arrow_items"),
        lambda self, value: self._set_scene_items("arrow_items", value),
    )
    ts_bracket_items = property(
        lambda self: self._scene_items("ts_bracket_items"),
        lambda self, value: self._set_scene_items("ts_bracket_items", value),
    )
    orbital_items = property(
        lambda self: self._scene_items("orbital_items"),
        lambda self, value: self._set_scene_items("orbital_items", value),
    )

    def _make_selectable(self, item) -> None:
        self.make_selectable_calls.append(item)

    def record_note_style_applied(self, item: QGraphicsTextItem) -> None:
        item._style_applied = True
        self.applied_note_style_items.append(item)

    def record_build_mark_item(self, kind: str):
        self.built_mark_kinds.append(kind)
        if kind == "missing":
            return None
        return QGraphicsTextItem(kind)

    def record_set_mark_center(self, item, center: QPointF) -> None:
        self.mark_centers[item] = QPointF(center)
        item.setPos(center)

    def record_build_arrow_item(
        self, start: QPointF, end: QPointF, kind: str
    ) -> QGraphicsPathItem:
        item = QGraphicsPathItem(QPainterPath())
        self.built_arrow_calls.append((QPointF(start), QPointF(end), kind, item))
        return item

    def record_set_curved_arrow_path(
        self,
        item: QGraphicsPathItem,
        start: QPointF,
        end: QPointF,
        control: QPointF,
        double: bool,
    ) -> None:
        self.curved_arrow_path_calls.append(
            (item, QPointF(start), QPointF(end), QPointF(control), double)
        )

    def record_build_ts_bracket_item(self, rect) -> QGraphicsPathItem:
        item = QGraphicsPathItem(QPainterPath())
        item.setData(0, "ts_bracket")
        self.built_ts_bracket_rects.append(rect)
        return item

    def record_build_orbital_items(self, center: QPointF, kind: str):
        self.built_orbital_calls.append((QPointF(center), kind))
        if kind == "missing":
            return []
        return [QGraphicsTextItem(kind)]

    def record_ts_bracket_path(self, _rect):
        return QPainterPath()

    def bond_id_between(self, atom_a: int, atom_b: int):
        return self.bond_lookup.get((atom_a, atom_b))

    def update_bond_geometry(self, bond_id: int) -> None:
        self.updated_bond_ids.append(bond_id)

    def record_remove_mark_item(self, item) -> None:
        self.removed_mark_items.append(item)
        if item in self.mark_items:
            self.mark_items.remove(item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        if isinstance(atom_id, int):
            marks = self.mark_registry.by_atom.get(atom_id)
            if marks and item in marks:
                marks.remove(item)
        self._scene.removeItem(item)

    def record_note_selection_box_updated(self, item) -> None:
        self.updated_note_boxes.append(item)

    def clear_handles(self) -> None:
        self.clear_handles_calls += 1
        self.handle_state.target = None


class _BrokenSceneItem:
    def __init__(self, kind: str, *, data1=None) -> None:
        self._kind = kind
        self._data1 = data1

    def data(self, role: int):
        if role == 0:
            return self._kind
        if role == 1:
            return self._data1
        return None

    def scene(self):
        raise RuntimeError("item deleted")

    def setTextInteractionFlags(self, _flags) -> None:
        pass


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for scene item controller tests"
)
class SceneItemControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = _FakeCanvas()
        self.controller = SceneItemController(
            self.canvas,
            graph_service=self.canvas.services.canvas_graph_service,
        )

    def test_attach_scene_item_updates_registries_without_duplicates(self) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")

        self.controller.attach_scene_item(mark)
        self.controller.attach_scene_item(mark)
        self.controller.restore_scene_item(note)

        self.assertEqual(self.canvas.mark_items, [mark])
        self.assertEqual(self.canvas.mark_registry.by_atom, {7: [mark]})
        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(
            note.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction
        )
        self.assertTrue(mark.flags() & mark.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(note.flags() & note.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(mark.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())

    def test_non_ring_attach_uses_constant_size_snapshot(self) -> None:
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")

        with patch(
            "ui.scene_item_lifecycle_service._scene_runtime_snapshot",
            side_effect=AssertionError("non-ring attach scanned the scene"),
        ):
            self.controller.attach_scene_item(note)

        self.assertEqual(self.canvas.note_items, [note])
        self.assertIs(note.scene(), self.canvas.scene())

    def test_builtin_attach_sequence_keeps_item_local_snapshot_path(self) -> None:
        scene = self.canvas.scene()
        collection = scene_item_collection_for(self.canvas, "shape_items")

        with patch(
            "ui.scene_item_attach_snapshot._scene_runtime_snapshot",
            side_effect=AssertionError("builtin attach captured full scene runtime"),
        ):
            for _index in range(200):
                item = QGraphicsPathItem()
                item.setData(0, "shape")
                ports = SceneItemAttachPorts.capture(scene, item)
                snapshot = SceneItemAttachSnapshot.capture(
                    self.canvas,
                    item,
                    scene=scene,
                    attach_ports=ports,
                )

                self.assertFalse(snapshot.full_graph_snapshot)
                self.assertEqual(snapshot.collection_contents, ())
                self.assertEqual(snapshot.mark_entries, ())
                collection.append(item)
                ports.add_item(item)
                snapshot.release()

        self.assertEqual(len(collection), 200)
        self.assertTrue(all(item.scene() is scene for item in collection))

    def test_attach_static_live_collection_descriptor_failure_precedes_mutation_and_retries(
        self,
    ) -> None:
        note_items: list[QGraphicsTextItem] = []

        class FailOnceSceneItemsState:
            calls = 0

            @property
            def note_items(self):
                self.calls += 1
                if self.calls == 1:
                    raise AttributeError(
                        "live note collection descriptor failed internally"
                    )
                return note_items

        state = FailOnceSceneItemsState()
        self.canvas.scene_items_state = state
        scene = self.canvas.scene()
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")

        with self.assertRaisesRegex(
            AttributeError,
            "live note collection descriptor failed internally",
        ):
            self.controller.attach_scene_item(note)

        self.assertFalse(bool(note.flags() & note.GraphicsItemFlag.ItemIsSelectable))
        self.assertEqual(note_items, [])
        self.assertIsNone(note.scene())
        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)

        self.controller.attach_scene_item(note)

        self.assertTrue(bool(note.flags() & note.GraphicsItemFlag.ItemIsSelectable))
        self.assertEqual(note_items, [note])
        self.assertIs(note.scene(), scene)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

    def test_ring_runtime_capture_exit_precedes_auto_scene_rect_guard(self) -> None:
        scene = self.canvas.scene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        ring = QGraphicsPolygonItem(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(4.0, 0.0),
                    QPointF(2.0, 3.0),
                ]
            )
        )
        ring.setData(0, "ring")

        with patch(
            "ui.scene_item_lifecycle_service._scene_runtime_snapshot",
            side_effect=SystemExit("ring runtime capture terminated"),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "ring runtime capture terminated",
            ):
                self.controller.attach_scene_item(ring)

        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)
        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())
        future = scene.addRect(20_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 20_000.0)
        scene.removeItem(future)

    def test_attach_scene_item_rolls_back_mark_registry_when_scene_add_fails(
        self,
    ) -> None:
        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})

        with patch(
            "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                self.controller.attach_scene_item(mark)

        self.assertEqual(self.canvas.mark_items, [])
        self.assertEqual(self.canvas.mark_registry.by_atom, {})
        self.assertIsNone(mark.scene())

    def test_attach_scene_item_keyboard_interrupt_restores_exact_mark_state_after_cleanup_failure(
        self,
    ) -> None:
        sibling = QGraphicsTextItem("sibling")
        sibling.setData(0, "mark")
        sibling.setData(1, {"atom_id": 7})
        self.canvas.scene().addItem(sibling)
        self.canvas.mark_items.append(sibling)
        sibling_marks = [sibling]
        mark_mapping = {7: sibling_marks}
        self.canvas.mark_registry.by_atom = mark_mapping

        mark = QGraphicsTextItem("+")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})
        mark.setFlag(mark.GraphicsItemFlag.ItemIsMovable, True)
        original_flags = mark.flags()
        mark_items = self.canvas.mark_items

        def add_then_interrupt(attach_ports, item) -> None:
            assert attach_ports.scene is not None
            attach_ports.scene.addItem(item)
            raise KeyboardInterrupt("attach interrupted")

        lifecycle = self.controller.lifecycle_service
        with (
            patch(
                "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                side_effect=add_then_interrupt,
            ),
            patch.object(
                lifecycle,
                "_remove_scene_item_registration",
                side_effect=SystemExit("cleanup interrupted"),
            ),
            self.assertRaisesRegex(KeyboardInterrupt, "attach interrupted") as caught,
        ):
            self.controller.attach_scene_item(mark)

        self.assertIs(self.canvas.mark_items, mark_items)
        self.assertEqual(mark_items, [sibling])
        self.assertIs(self.canvas.mark_registry.by_atom, mark_mapping)
        self.assertIs(mark_mapping[7], sibling_marks)
        self.assertEqual(sibling_marks, [sibling])
        self.assertEqual(mark.flags(), original_flags)
        self.assertIsNone(mark.scene())
        self.assertTrue(
            any(
                "SystemExit" in note
                for note in getattr(caught.exception, "__notes__", ())
            )
        )

    def test_attach_rejects_foreign_scene_item_without_touching_either_scene(
        self,
    ) -> None:
        target_scene = self.canvas.scene()
        foreign_scene = QGraphicsScene()
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        foreign_scene.addItem(shape)
        original_flags = shape.flags()
        foreign_items = list(foreign_scene.items())
        target_items = list(target_scene.items())
        shape_items = scene_item_collection_for(self.canvas, "shape_items")

        with self.assertRaisesRegex(RuntimeError, "different scene"):
            self.controller.attach_scene_item(shape)

        self.assertIs(shape.scene(), foreign_scene)
        self.assertEqual(foreign_scene.items(), foreign_items)
        self.assertEqual(target_scene.items(), target_items)
        self.assertIs(
            scene_item_collection_for(self.canvas, "shape_items"),
            shape_items,
        )
        self.assertEqual(shape_items, [])
        self.assertEqual(shape.flags(), original_flags)
        tracker = getattr(target_scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)

    def test_attach_callback_restores_full_collection_and_scene_runtime(self) -> None:
        scene = self.canvas.scene()
        first = QGraphicsPathItem()
        second = QGraphicsPathItem()
        replacement = QGraphicsPathItem()
        for item in (first, second, replacement):
            item.setData(0, "shape")
        first.setFlag(first.GraphicsItemFlag.ItemIsSelectable, True)
        first.setSelected(True)
        second.setFlag(second.GraphicsItemFlag.ItemIsFocusable, True)
        replacement.setFlag(replacement.GraphicsItemFlag.ItemIsFocusable, True)
        scene.addItem(first)
        scene.addItem(second)
        scene.setFocusItem(second)
        collection = scene_item_collection_for(self.canvas, "shape_items")
        collection[:] = [first, second]
        scene_items_before = list(scene.items())

        class CorruptingShape(QGraphicsPathItem):
            armed = False

            def itemChange(self, change, value):
                if self.armed and change == self.GraphicsItemChange.ItemFlagsChange:
                    self.armed = False
                    collection.clear()
                    scene.removeItem(first)
                    scene.addItem(replacement)
                    scene.setFocusItem(replacement)
                    # Reject the requested flag value after corrupting other
                    # authorities. The bound setter's postcondition then
                    # raises in Python without throwing through a Qt virtual.
                    return QGraphicsPathItem.flags(self)
                return QGraphicsPathItem.itemChange(self, change, value)

        shape = CorruptingShape()
        shape.setData(0, "shape")
        shape.armed = True

        with self.assertRaisesRegex(
            RuntimeError,
            "not made selectable",
        ):
            self.controller.attach_scene_item(shape)

        self.assertIs(
            scene_item_collection_for(self.canvas, "shape_items"),
            collection,
        )
        self.assertEqual(collection, [first, second])
        self.assertEqual(scene.items(), scene_items_before)
        self.assertIs(first.scene(), scene)
        self.assertIs(second.scene(), scene)
        self.assertIsNone(replacement.scene())
        self.assertIsNone(shape.scene())
        self.assertTrue(first.isSelected())
        self.assertIs(scene.focusItem(), second)

    def test_mark_attach_callback_restores_entire_mapping_and_mark_lists(
        self,
    ) -> None:
        scene = self.canvas.scene()
        first = QGraphicsTextItem("first")
        second = QGraphicsTextItem("second")
        replacement = QGraphicsTextItem("replacement")
        for atom_id, item in ((7, first), (8, second), (99, replacement)):
            item.setData(0, "mark")
            item.setData(1, {"atom_id": atom_id})
        scene.addItem(first)
        scene.addItem(second)
        collection = self.canvas.mark_items
        collection[:] = [first, second]
        first_marks = [first]
        second_marks = [second]
        mapping = {7: first_marks, 8: second_marks}
        self.canvas.mark_registry.by_atom = mapping
        scene_items_before = list(scene.items())

        class CorruptingMark(QGraphicsTextItem):
            armed = True

            def itemChange(self, change, value):
                if self.armed and change == self.GraphicsItemChange.ItemFlagsChange:
                    self.armed = False
                    collection[:] = [replacement]
                    first_marks[:] = [replacement]
                    second_marks.clear()
                    mapping.clear()
                    mapping[99] = [replacement]
                    self_canvas.mark_registry.by_atom = {100: [replacement]}
                    scene.removeItem(first)
                    scene.addItem(replacement)
                    return QGraphicsTextItem.flags(self)
                return QGraphicsTextItem.itemChange(self, change, value)

        self_canvas = self.canvas
        mark = CorruptingMark("new")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 7})

        with self.assertRaisesRegex(
            RuntimeError,
            "not made selectable",
        ):
            self.controller.attach_scene_item(mark)

        self.assertIs(self.canvas.mark_items, collection)
        self.assertEqual(collection, [first, second])
        self.assertIs(self.canvas.mark_registry.by_atom, mapping)
        self.assertEqual(list(mapping), [7, 8])
        self.assertIs(mapping[7], first_marks)
        self.assertIs(mapping[8], second_marks)
        self.assertEqual(first_marks, [first])
        self.assertEqual(second_marks, [second])
        self.assertEqual(scene.items(), scene_items_before)
        self.assertIsNone(replacement.scene())
        self.assertIsNone(mark.scene())

    def test_attach_rollback_detects_container_no_op_and_fail_after(self) -> None:
        def damage_operation(
            current_mode,
            current_state,
            current_replacement_collection,
            current_original,
            current_replacement,
            current_primary,
        ):
            def damage_container_then_interrupt(attach_ports, item) -> None:
                attach_ports.add_item(item)
                if current_mode.startswith("identity"):
                    current_state._shape_items = current_replacement_collection
                    current_state.failure_mode = current_mode
                else:
                    list.__setitem__(
                        current_original,
                        slice(None),
                        [current_replacement],
                    )
                    current_original.failure_mode = current_mode
                raise current_primary

            return damage_container_then_interrupt

        for mode in (
            "identity_no_op",
            "identity_fail_after",
            "contents_no_op",
            "contents_fail_after",
        ):
            with self.subTest(mode=mode):
                canvas = _FakeCanvas()
                controller = SceneItemController(
                    canvas,
                    graph_service=canvas.services.canvas_graph_service,
                )
                scene = canvas.scene()
                existing = QGraphicsPathItem()
                existing.setData(0, "shape")
                replacement = QGraphicsPathItem()
                replacement.setData(0, "shape")
                scene.addItem(existing)

                class ControlledList(list):
                    failure_mode: str | None = None
                    slice_calls = 0

                    def __setitem__(self, key, value) -> None:
                        if isinstance(key, slice) and self.failure_mode is not None:
                            self.slice_calls += 1
                            if self.failure_mode == "contents_no_op":
                                return
                            if self.failure_mode == "contents_fail_after":
                                list.__setitem__(self, key, value)
                                raise SystemExit("container contents fail-after")
                        list.__setitem__(self, key, value)

                original = ControlledList([existing])
                replacement_collection = [replacement]

                class ControlledState:
                    def __init__(self, initial_items) -> None:
                        self._shape_items = initial_items
                        self.failure_mode: str | None = None
                        self.setter_calls = 0

                    @property
                    def shape_items(self):
                        return self._shape_items

                    @shape_items.setter
                    def shape_items(self, value) -> None:
                        if self.failure_mode is not None:
                            self.setter_calls += 1
                            if self.failure_mode == "identity_no_op":
                                return
                            if self.failure_mode == "identity_fail_after":
                                self._shape_items = value
                                raise SystemExit("container identity fail-after")
                        self._shape_items = value

                state = ControlledState(original)
                canvas.scene_items_state = state
                shape = QGraphicsPathItem()
                shape.setData(0, "shape")
                primary = KeyboardInterrupt("attach interrupted after container damage")

                with (
                    patch(
                        "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                        side_effect=damage_operation(
                            mode,
                            state,
                            replacement_collection,
                            original,
                            replacement,
                            primary,
                        ),
                    ),
                    self.assertRaises(KeyboardInterrupt) as caught,
                ):
                    controller.attach_scene_item(shape)

                self.assertIs(caught.exception, primary)
                self.assertIsNone(shape.scene())
                notes = getattr(primary, "__notes__", ())
                if mode == "identity_no_op":
                    self.assertIs(state.shape_items, replacement_collection)
                    self.assertEqual(state.setter_calls, 2)
                    self.assertTrue(
                        any("collection identity changed" in note for note in notes)
                    )
                elif mode == "identity_fail_after":
                    self.assertIs(state.shape_items, original)
                    self.assertEqual(state.setter_calls, 1)
                    self.assertTrue(
                        any("container identity fail-after" in note for note in notes)
                    )
                elif mode == "contents_no_op":
                    self.assertIs(state.shape_items, original)
                    self.assertEqual(original, [replacement])
                    self.assertEqual(original.slice_calls, 2)
                    self.assertTrue(
                        any("collection contents" in note for note in notes)
                    )
                else:
                    self.assertIs(state.shape_items, original)
                    self.assertEqual(original, [existing])
                    self.assertEqual(original.slice_calls, 1)
                    self.assertTrue(
                        any("container contents fail-after" in note for note in notes)
                    )

    def test_attach_note_system_exit_restores_interaction_and_selectability_flags(
        self,
    ) -> None:
        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        note.setFlag(note.GraphicsItemFlag.ItemIsMovable, True)
        original_flags = note.flags()
        original_interaction = note.textInteractionFlags()

        def add_then_exit(attach_ports, item) -> None:
            assert attach_ports.scene is not None
            attach_ports.scene.addItem(item)
            raise SystemExit("terminate attach")

        with patch(
            "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
            side_effect=add_then_exit,
        ):
            with self.assertRaisesRegex(SystemExit, "terminate attach"):
                self.controller.attach_scene_item(note)

        self.assertEqual(self.canvas.note_items, [])
        self.assertEqual(note.flags(), original_flags)
        self.assertEqual(note.textInteractionFlags(), original_interaction)
        self.assertIsNone(note.scene())

    def test_actual_qt_attach_failure_restores_existing_parent_and_z_topology(
        self,
    ) -> None:
        class CallbackShape(QGraphicsPathItem):
            def itemChange(self, change, value):
                return super().itemChange(change, value)

        scene = self.canvas.scene()
        parent = QGraphicsPathItem()
        child = QGraphicsPathItem()
        peer = QGraphicsPathItem()
        for item in (parent, child, peer):
            scene.addItem(item)
        child.setParentItem(parent)
        parent.setZValue(2.0)
        child.setZValue(3.0)
        peer.setZValue(2.0)
        expected_order = list(scene.items())
        shape = CallbackShape()
        shape.setData(0, "shape")
        primary = KeyboardInterrupt("attach damaged existing topology")

        def add_after_corrupting_topology(attach_ports, item) -> None:
            child.setParentItem(peer)
            parent.setZValue(9.0)
            child.setZValue(-4.0)
            peer.setZValue(-2.0)
            attach_ports.add_item(item)
            raise primary

        with (
            patch(
                "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                side_effect=add_after_corrupting_topology,
            ),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            self.controller.attach_scene_item(shape)

        self.assertIs(caught.exception, primary)
        self.assertIsNone(shape.scene())
        self.assertIs(child.parentItem(), parent)
        self.assertEqual(parent.zValue(), 2.0)
        self.assertEqual(child.zValue(), 3.0)
        self.assertEqual(peer.zValue(), 2.0)
        self.assertEqual(list(scene.items()), expected_order)

    def test_attach_failure_restores_existing_stacking_flags_and_order(self) -> None:
        scene = self.canvas.scene()
        parent = QGraphicsPathItem()
        child = QGraphicsPathItem(parent)
        scene.addItem(parent)
        expected_flags = child.flags()
        expected_order = list(scene.items())

        class CorruptingShape(QGraphicsPathItem):
            armed = True

            def itemChange(self, change, value):
                if self.armed and change == self.GraphicsItemChange.ItemFlagsChange:
                    self.armed = False
                    child.setFlag(
                        child.GraphicsItemFlag.ItemStacksBehindParent,
                        True,
                    )
                    return QGraphicsPathItem.flags(self)
                return QGraphicsPathItem.itemChange(self, change, value)

        shape = CorruptingShape()
        shape.setData(0, "shape")

        with self.assertRaisesRegex(RuntimeError, "not made selectable"):
            self.controller.attach_scene_item(shape)

        self.assertEqual(child.flags(), expected_flags)
        self.assertEqual(list(scene.items()), expected_order)
        self.assertIsNone(shape.scene())

    def test_callable_descriptor_item_change_promotes_before_first_callback(
        self,
    ) -> None:
        note_items = scene_item_collection_for(self.canvas, "note_items")
        sentinel = object()

        class ItemChangeDescriptor:
            def __get__(self, item, owner):
                if item is None:
                    return self

                def apply(change, value):
                    if item.armed and change == item.GraphicsItemChange.ItemFlagsChange:
                        item.armed = False
                        note_items.append(sentinel)
                        return QGraphicsPathItem.flags(item)
                    return QGraphicsPathItem.itemChange(item, change, value)

                return apply

        class DescriptorShape(QGraphicsPathItem):
            itemChange = ItemChangeDescriptor()

            def __init__(self) -> None:
                super().__init__()
                self.armed = True

        shape = DescriptorShape()
        shape.setData(0, "shape")

        with self.assertRaisesRegex(RuntimeError, "not made selectable"):
            self.controller.attach_scene_item(shape)

        self.assertEqual(note_items, [])
        self.assertIsNone(shape.scene())

    def test_actual_qt_data_override_is_not_a_preflight_callback(self) -> None:
        peer = QGraphicsPathItem()
        peer.setPos(QPointF(4.0, 5.0))
        self.canvas.scene().addItem(peer)

        class SideEffectDataShape(QGraphicsPathItem):
            reads = 0

            def data(self, key):
                self.reads += 1
                peer.setPos(QPointF(24.0, -4.0))
                raise RuntimeError("custom data getter ran")

        shape = SideEffectDataShape()
        QGraphicsPathItem.setData(shape, 0, "shape")

        self.controller.attach_scene_item(shape)

        self.assertEqual(shape.reads, 0)
        self.assertEqual(peer.pos(), QPointF(4.0, 5.0))
        self.assertIs(shape.scene(), self.canvas.scene())

    def test_actual_qt_focus_override_is_not_an_attach_preflight_callback(
        self,
    ) -> None:
        primary = KeyboardInterrupt("custom focus getter interrupted")

        class PoisonFocusScene(QGraphicsScene):
            def __init__(self) -> None:
                super().__init__()
                self.focus_reads = 0
                self.armed = False
                self.peer = QGraphicsLineItem()
                self.peer.setPos(QPointF(4.0, 5.0))
                self.addItem(self.peer)

            def focusItem(self):
                self.focus_reads += 1
                if self.armed:
                    self.peer.setPos(QPointF(90.0, -30.0))
                    raise primary
                return QGraphicsScene.focusItem(self)

        scene = PoisonFocusScene()
        item = QGraphicsPathItem()
        item.setData(0, "shape")
        scene.armed = True

        ports = SceneItemAttachPorts.capture(scene, item)

        self.assertEqual(scene.focus_reads, 0)
        self.assertEqual(scene.peer.pos(), QPointF(4.0, 5.0))
        self.assertIsNone(ports.focus_item)

    def test_preselected_or_prefocused_attach_isolates_first_qt_callback(
        self,
    ) -> None:
        scene = self.canvas.scene()
        note_items = scene_item_collection_for(self.canvas, "note_items")

        for mode in ("selected", "focused"):
            with self.subTest(mode=mode):
                rogue = object()
                callback_calls = 0
                focus_view = None
                shape = QGraphicsPathItem()
                shape.setData(0, "shape")
                if mode == "selected":
                    shape.setFlag(
                        shape.GraphicsItemFlag.ItemIsSelectable,
                        True,
                    )
                    shape.setSelected(True)
                    signal = scene.selectionChanged
                else:
                    focus_view = QGraphicsView(scene)
                    focus_view.show()
                    focus_view.setFocus()
                    self.app.processEvents()
                    scene.setFocus()
                    shape.setFlag(
                        shape.GraphicsItemFlag.ItemIsFocusable,
                        True,
                    )
                    shape.setFocus()
                    signal = scene.focusItemChanged

                def corrupt_unrelated_runtime(*_args, _rogue=rogue) -> None:
                    nonlocal callback_calls
                    callback_calls += 1
                    note_items.append(_rogue)

                signal.connect(corrupt_unrelated_runtime)
                try:
                    with (
                        patch(
                            "ui.scene_item_attach_snapshot.SceneRectSnapshot.release",
                            side_effect=RuntimeError("attach rect release failed"),
                        ),
                        self.assertRaisesRegex(
                            RuntimeError,
                            "attach rect release failed",
                        ),
                    ):
                        self.controller.attach_scene_item(shape)
                finally:
                    signal.disconnect(corrupt_unrelated_runtime)
                    if focus_view is not None:
                        focus_view.close()

                self.assertGreater(callback_calls, 0)
                self.assertEqual(note_items, [])
                self.assertIsNone(shape.scene())

    def test_attach_rollback_persistent_collection_lookup_keeps_later_restore_exact_and_retries(
        self,
    ) -> None:
        class BrokenKeyboardInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name: str):
                if name == "add_note":
                    raise SystemExit("broken diagnostic lookup")
                return super().__getattribute__(name)

        note_items = self.canvas.note_items

        class FailingSceneItemsState:
            def __init__(self) -> None:
                self.items = note_items
                self.fail_lookup = False

            @property
            def note_items(self):
                if self.fail_lookup:
                    raise SystemExit("persistent collection lookup failure")
                return self.items

            @note_items.setter
            def note_items(self, value) -> None:
                self.items = value

        state = FailingSceneItemsState()
        self.canvas.scene_items_state = state
        scene = self.canvas.scene()
        prior_focus = QGraphicsTextItem("prior focus")
        prior_focus.setFlag(prior_focus.GraphicsItemFlag.ItemIsFocusable, True)
        scene.addItem(prior_focus)
        scene.setFocusItem(prior_focus)

        note = QGraphicsTextItem("Mechanism")
        note.setData(0, "note")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        note.setFlag(note.GraphicsItemFlag.ItemIsMovable, True)
        note.setFlag(note.GraphicsItemFlag.ItemIsFocusable, True)
        original_flags = note.flags()
        original_interaction = note.textInteractionFlags()
        primary_error = BrokenKeyboardInterrupt("attach interrupted")

        def add_focus_then_interrupt(attach_ports, item) -> None:
            assert attach_ports.scene is not None
            attach_ports.scene.addItem(item)
            attach_ports.focus_item_setter(item)
            state.fail_lookup = True
            raise primary_error

        with patch(
            "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
            side_effect=add_focus_then_interrupt,
        ):
            with self.assertRaises(BrokenKeyboardInterrupt) as caught:
                self.controller.attach_scene_item(note)

        self.assertIs(caught.exception, primary_error)
        self.assertIs(state.items, note_items)
        self.assertEqual(note_items, [])
        self.assertIsNone(note.scene())
        self.assertEqual(note.flags(), original_flags)
        self.assertEqual(note.textInteractionFlags(), original_interaction)
        self.assertIs(scene.focusItem(), prior_focus)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

        state.fail_lookup = False
        self.controller.attach_scene_item(note)

        self.assertEqual(state.note_items, [note])
        self.assertIs(note.scene(), scene)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

    def test_attach_scene_item_removes_scene_item_when_ring_refresh_fails(self) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {(1, 2): 17}

        def fail_update(_bond_id: int) -> None:
            raise RuntimeError("refresh failed")

        self.canvas.bond_renderer.update_bond_geometry = fail_update

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            self.controller.attach_scene_item(ring)

        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())

    def test_attach_scene_item_refreshes_ring_bonds_after_partial_refresh_failure(
        self,
    ) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {(1, 2): 17, (2, 3): 18, (3, 1): 19}
        calls = []

        def fail_second_update(bond_id: int) -> None:
            calls.append(
                (
                    bond_id,
                    ring in self.canvas.ring_items,
                    ring.scene() is self.canvas.scene(),
                )
            )
            if len(calls) == 2:
                raise RuntimeError("refresh failed")

        self.canvas.bond_renderer.update_bond_geometry = fail_second_update

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            self.controller.attach_scene_item(ring)

        post_rollback_calls = [
            bond_id
            for bond_id, registered, in_scene in calls
            if not registered and not in_scene
        ]
        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())
        self.assertCountEqual(post_rollback_calls, [17, 18, 19])

    def test_ring_attach_system_exit_restores_raw_bond_primitive_after_persistent_refresh_failure(
        self,
    ) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF(
                [
                    QPointF(0.0, 0.0),
                    QPointF(4.0, 0.0),
                    QPointF(2.0, 3.0),
                ]
            )
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2])
        self.canvas.bond_lookup = {(1, 2): 17, (2, 1): 17}
        primitive = QGraphicsLineItem(QLineF(0.0, 0.0, 10.0, 0.0))
        self.canvas.scene().addItem(primitive)
        original_line = primitive.line()
        original_scene_rect = self.canvas.scene().sceneRect()
        self.canvas.bond_graphics_state = SimpleNamespace(bond_items={17: [primitive]})

        def mutate_then_exit(_bond_id: int) -> None:
            primitive.setLine(QLineF(0.0, 0.0, 999.0, 0.0))
            # An eager view/observer read must not cache the transient raw
            # primitive extent, and scene-rect release must happen after raw
            # primitive restoration.
            self.assertEqual(self.canvas.scene().sceneRect(), original_scene_rect)
            raise SystemExit("ring refresh terminated")

        self.canvas.bond_renderer.update_bond_geometry = mutate_then_exit

        with self.assertRaisesRegex(SystemExit, "ring refresh terminated"):
            self.controller.attach_scene_item(ring)

        self.assertEqual(self.canvas.ring_items, [])
        self.assertIsNone(ring.scene())
        self.assertEqual(primitive.line(), original_line)
        self.assertEqual(self.canvas.scene().sceneRect(), original_scene_rect)
        future = self.canvas.scene().addRect(2_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(self.canvas.scene().sceneRect().right(), 2_000.0)
        self.canvas.scene().removeItem(future)

    def test_restore_scene_item_skips_already_attached_or_deleted_items(self) -> None:
        note = QGraphicsTextItem("Attached")
        note.setData(0, "note")
        self.canvas.scene().addItem(note)
        self.canvas.note_items.append(note)
        deleted = QGraphicsTextItem("Deleted")
        deleted.setData(0, "note")
        sip.delete(deleted)

        self.controller.restore_scene_item(note)
        self.controller.restore_scene_item(deleted)

        self.assertEqual(self.canvas.note_items, [note])

    def test_restore_scene_item_propagates_live_scene_getter_runtime_error(
        self,
    ) -> None:
        broken = _BrokenSceneItem("note")

        with self.assertRaisesRegex(RuntimeError, "item deleted"):
            self.controller.restore_scene_item(broken)

        self.assertEqual(self.canvas.note_items, [])

    def test_attach_requires_bound_add_and_remove_ports_before_mutation(
        self,
    ) -> None:
        class MissingRemoveScene:
            add_calls = 0

            def addItem(self, _item) -> None:
                self.add_calls += 1

        scene = MissingRemoveScene()
        self.canvas._scene = scene
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")

        with self.assertRaisesRegex(RuntimeError, "item-remove port"):
            self.controller.attach_scene_item(shape)

        self.assertEqual(scene.add_calls, 0)
        self.assertEqual(
            scene_item_collection_for(self.canvas, "shape_items"),
            [],
        )
        self.assertIsNone(shape.scene())

    def test_attach_requires_callable_membership_getter_before_mutation(
        self,
    ) -> None:
        class MissingMembershipItem:
            def __init__(self, scene_port=...) -> None:
                self._flags = QGraphicsPathItem.GraphicsItemFlag(0)
                if scene_port is not ...:
                    self.scene = scene_port

            def data(self, role: int):
                return "shape" if role == 0 else None

            def flags(self):
                return self._flags

            def setFlags(self, flags) -> None:
                self._flags = flags

        for scene_port in (..., object()):
            with self.subTest(scene_port=scene_port):
                item = MissingMembershipItem(scene_port)
                with self.assertRaisesRegex(
                    RuntimeError,
                    "membership getter",
                ):
                    self.controller.attach_scene_item(item)

                self.assertEqual(
                    scene_item_collection_for(self.canvas, "shape_items"),
                    [],
                )

    def test_attach_add_no_op_is_detected_by_bound_membership_getter(self) -> None:
        class NoOpAddScene(QGraphicsScene):
            add_calls = 0

            @property
            def addItem(self):
                return self._ignore_add

            def _ignore_add(self, _item) -> None:
                self.add_calls += 1

        scene = NoOpAddScene()
        self.canvas._scene = scene
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")

        with self.assertRaisesRegex(RuntimeError, "did not attach"):
            self.controller.attach_scene_item(shape)

        self.assertEqual(scene.add_calls, 1)
        self.assertIsNone(shape.scene())
        self.assertEqual(
            scene_item_collection_for(self.canvas, "shape_items"),
            [],
        )

    def test_attach_remove_no_op_is_detected_during_rollback(self) -> None:
        class NoOpRemoveScene(QGraphicsScene):
            remove_calls = 0

            @property
            def removeItem(self):
                return self._ignore_remove

            def _ignore_remove(self, _item) -> None:
                self.remove_calls += 1

        scene = NoOpRemoveScene()
        self.canvas._scene = scene
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        primary = SystemExit("attach interrupted after add")

        def add_then_interrupt(attach_ports, item) -> None:
            attach_ports.add_item(item)
            raise primary

        with (
            patch(
                "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                side_effect=add_then_interrupt,
            ),
            self.assertRaises(SystemExit) as caught,
        ):
            self.controller.attach_scene_item(shape)

        self.assertIs(caught.exception, primary)
        self.assertIs(shape.scene(), scene)
        self.assertGreaterEqual(scene.remove_calls, 2)
        self.assertTrue(
            any("did not detach" in note for note in getattr(primary, "__notes__", []))
        )
        QGraphicsScene.removeItem(scene, shape)

    def test_attach_forward_state_uses_qt_base_setters(self) -> None:
        foreign_scene = QGraphicsScene()

        class SwitchingFlagsShape(QGraphicsPathItem):
            setter_reads = 0

            @property
            def setFlags(self):
                self.setter_reads += 1
                if self.setter_reads == 1:
                    return self._safe_set_flags
                return self._malicious_set_flags

            def _safe_set_flags(self, flags) -> None:
                QGraphicsPathItem.setFlags(self, flags)

            def _malicious_set_flags(self, _flags) -> None:
                foreign_scene.addItem(self)
                raise SystemExit("replacement flags setter ran")

        class SwitchingTextNote(QGraphicsTextItem):
            setter_reads = 0

            @property
            def setTextInteractionFlags(self):
                self.setter_reads += 1
                if self.setter_reads == 1:
                    return self._safe_set_text_flags
                return self._malicious_set_text_flags

            def _safe_set_text_flags(self, flags) -> None:
                QGraphicsTextItem.setTextInteractionFlags(self, flags)

            def _malicious_set_text_flags(self, _flags) -> None:
                foreign_scene.addItem(self)
                raise KeyboardInterrupt("replacement text setter ran")

        shape = SwitchingFlagsShape()
        shape.setData(0, "shape")
        note = SwitchingTextNote("Mechanism")
        note.setData(0, "note")
        QGraphicsTextItem.setTextInteractionFlags(
            note,
            Qt.TextInteractionFlag.TextEditorInteraction,
        )

        self.controller.attach_scene_item(shape)
        self.controller.attach_scene_item(note)

        self.assertEqual(shape.setter_reads, 0)
        self.assertEqual(note.setter_reads, 0)
        self.assertIs(shape.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())
        self.assertNotIn(shape, foreign_scene.items())
        self.assertNotIn(note, foreign_scene.items())

    def test_attach_bypasses_a_no_op_selectability_override(self) -> None:
        class NoOpFlagsShape(QGraphicsPathItem):
            def setFlags(self, _flags) -> None:
                return None

        shape = NoOpFlagsShape()
        shape.setData(0, "shape")

        self.controller.attach_scene_item(shape)

        self.assertEqual(
            scene_item_collection_for(self.canvas, "shape_items"),
            [shape],
        )
        self.assertTrue(shape.flags() & shape.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(shape.scene(), self.canvas.scene())

    def test_attach_bypasses_no_op_note_interaction_override(self) -> None:
        class NoOpInteractionNote(QGraphicsTextItem):
            ignore_mutation = False

            def setTextInteractionFlags(self, flags) -> None:
                if self.ignore_mutation:
                    return
                QGraphicsTextItem.setTextInteractionFlags(self, flags)

        note = NoOpInteractionNote("Mechanism")
        note.setData(0, "note")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        original_flags = note.textInteractionFlags()
        note.ignore_mutation = True

        self.controller.attach_scene_item(note)

        self.assertEqual(self.canvas.note_items, [note])
        self.assertNotEqual(note.textInteractionFlags(), original_flags)
        self.assertEqual(
            note.textInteractionFlags(),
            Qt.TextInteractionFlag.NoTextInteraction,
        )
        self.assertIs(note.scene(), self.canvas.scene())

    def test_mark_attach_uses_qt_base_kind_and_metadata_getter(self) -> None:
        class ChangingDataMark(QGraphicsTextItem):
            kind_reads = 0
            metadata_reads = 0

            def data(self, role: int):
                if role == 0:
                    self.kind_reads += 1
                    return "mark"
                if role == 1:
                    self.metadata_reads += 1
                    return {"atom_id": 6 + self.metadata_reads}
                return QGraphicsTextItem.data(self, role)

            def setFlags(self, _flags) -> None:
                raise KeyboardInterrupt("selectability interrupted")

        mark = ChangingDataMark("+")
        QGraphicsTextItem.setData(mark, 0, "mark")
        QGraphicsTextItem.setData(mark, 1, {"atom_id": 7})

        self.controller.attach_scene_item(mark)

        self.assertEqual(mark.kind_reads, 0)
        self.assertEqual(mark.metadata_reads, 0)
        self.assertEqual(self.canvas.mark_items, [mark])
        self.assertEqual(self.canvas.mark_registry.by_atom, {7: [mark]})
        self.assertIs(mark.scene(), self.canvas.scene())
        self.assertEqual(self.canvas.make_selectable_calls, [])

    def test_attach_rollback_does_not_publish_internal_rect_probes(
        self,
    ) -> None:
        scene = self.canvas.scene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        baseline = QRectF(scene.sceneRect())
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        original_flags = shape.flags()
        shape_items = scene_item_collection_for(self.canvas, "shape_items")
        armed = False
        observed_rect_transitions = 0

        def corrupt_restored_state(_rect) -> None:
            nonlocal observed_rect_transitions
            if not armed:
                return
            observed_rect_transitions += 1
            shape_items.append(shape)
            QGraphicsPathItem.setFlags(
                shape,
                original_flags | shape.GraphicsItemFlag.ItemIsMovable,
            )

        scene.sceneRectChanged.connect(corrupt_restored_state)

        def add_then_fail(attach_ports, item) -> None:
            nonlocal armed
            attach_ports.add_item(item)
            armed = True
            raise RuntimeError("attach failed before release")

        with (
            patch(
                "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                side_effect=add_then_fail,
            ),
            self.assertRaisesRegex(
                RuntimeError,
                "attach failed before release",
            ),
        ):
            self.controller.attach_scene_item(shape)

        self.assertEqual(observed_rect_transitions, 0)
        self.assertEqual(shape_items, [])
        self.assertEqual(shape.flags(), original_flags)
        self.assertIsNone(shape.scene())
        self.assertTrue(scene_rect_is_automatic(scene))
        self.assertEqual(scene.sceneRect(), baseline)
        scene.sceneRectChanged.disconnect(corrupt_restored_state)

    def test_attach_rollback_reports_transient_scene_rect_recovery(self) -> None:
        class FailOnceRestoreScene(QGraphicsScene):
            armed = False
            failed = False

            def setSceneRect(self, rect) -> None:
                if self.armed and not self.failed:
                    self.failed = True
                    raise SystemExit("scene rect restore interrupted once")
                QGraphicsScene.setSceneRect(self, rect)

        scene = FailOnceRestoreScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        self.canvas._scene = scene
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        primary = RuntimeError("attach failed before rect restore")

        def add_then_fail(attach_ports, item) -> None:
            attach_ports.add_item(item)
            scene.armed = True
            raise primary

        with (
            patch(
                "ui.scene_item_lifecycle_service._add_item_with_attach_ports",
                side_effect=add_then_fail,
            ),
            self.assertRaises(RuntimeError) as caught,
        ):
            self.controller.attach_scene_item(shape)

        self.assertIs(caught.exception, primary)
        self.assertTrue(scene.failed)
        self.assertIsNone(shape.scene())
        self.assertTrue(
            any(
                "scene rect restore interrupted once" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

    def test_restore_scene_item_registers_arrow_ts_bracket_and_orbital_items(
        self,
    ) -> None:
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_double")
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")

        self.controller.restore_scene_item(curved)
        self.controller.restore_scene_item(ts_bracket)
        self.controller.restore_scene_item(orbital)

        self.assertEqual(self.canvas.arrow_items, [curved])
        self.assertEqual(self.canvas.ts_bracket_items, [ts_bracket])
        self.assertEqual(self.canvas.orbital_items, [orbital])
        self.assertTrue(curved.flags() & curved.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(
            ts_bracket.flags() & ts_bracket.GraphicsItemFlag.ItemIsSelectable
        )
        self.assertTrue(orbital.flags() & orbital.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(curved.scene(), self.canvas.scene())
        self.assertIs(ts_bracket.scene(), self.canvas.scene())
        self.assertIs(orbital.scene(), self.canvas.scene())

    def test_restore_scene_item_reuses_existing_registries_for_offscene_items_without_duplicates(
        self,
    ) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        note = QGraphicsTextItem("Detached")
        note.setData(0, "note")
        free_mark = QGraphicsTextItem("free")
        free_mark.setData(0, "mark")
        free_mark.setData(1, {"atom_id": None})
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")

        self.canvas.ring_items.append(ring)
        self.canvas.note_items.append(note)
        self.canvas.mark_items.append(free_mark)
        self.canvas.arrow_items.append(curved)
        self.canvas.ts_bracket_items.append(ts_bracket)
        self.canvas.orbital_items.append(orbital)

        for item in (ring, note, free_mark, curved, ts_bracket, orbital):
            self.controller.restore_scene_item(item)

        self.assertEqual(self.canvas.ring_items, [ring])
        self.assertEqual(self.canvas.note_items, [note])
        self.assertEqual(self.canvas.mark_items, [free_mark])
        self.assertEqual(self.canvas.arrow_items, [curved])
        self.assertEqual(self.canvas.ts_bracket_items, [ts_bracket])
        self.assertEqual(self.canvas.orbital_items, [orbital])
        self.assertEqual(self.canvas.mark_registry.by_atom, {})
        for item in (ring, note, free_mark, curved, ts_bracket, orbital):
            self.assertTrue(item.flags() & item.GraphicsItemFlag.ItemIsSelectable)
        self.assertIs(ring.scene(), self.canvas.scene())
        self.assertIs(note.scene(), self.canvas.scene())
        self.assertIs(free_mark.scene(), self.canvas.scene())
        self.assertIs(curved.scene(), self.canvas.scene())
        self.assertIs(ts_bracket.scene(), self.canvas.scene())
        self.assertIs(orbital.scene(), self.canvas.scene())

    def test_restore_helper_methods_create_and_register_supported_items(self) -> None:
        self.canvas.model.atoms[7] = SimpleNamespace(x=10.0, y=20.0)

        ring = self.controller.restore_ring_from_state(
            {"points": [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)], "atom_ids": [1, 2, 3]}
        )
        note = self.controller.restore_note_from_state(
            {"text": "Mechanism", "x": 3.0, "y": -4.0}
        )
        mark = self.controller.restore_mark_from_state(
            {"mark_kind": "plus", "atom_id": 7, "dx": 5.0, "dy": -2.0, "text": "m"}
        )
        arrow = self.controller.restore_arrow_from_state(
            {
                "kind": "curved_double",
                "start": (1.0, 2.0),
                "end": (7.0, 8.0),
                "control": (4.0, 9.0),
                "double": True,
            }
        )
        ts_bracket = self.controller.restore_ts_bracket_from_state(
            {"left": -5.0, "top": -2.0, "right": 8.0, "bottom": 6.0}
        )
        orbital = self.controller.restore_orbital_from_state(
            {
                "orbital_kind": "sp2",
                "center": (2.0, 3.0),
                "scale": 1.2,
                "rotation": 15.0,
            }
        )

        self.assertIsNotNone(ring)
        self.assertIn(ring, self.canvas.ring_items)
        self.assertIsNotNone(note)
        self.assertIn(note, self.canvas.note_items)
        self.assertIn(note, self.canvas.applied_note_style_items)
        self.assertEqual(note.toPlainText(), "Mechanism")
        self.assertIsNotNone(mark)
        self.assertIn(mark, self.canvas.mark_items)
        self.assertIn(mark, self.canvas.mark_registry.by_atom[7])
        self.assertEqual(self.canvas.built_mark_kinds, ["plus"])
        self.assertAlmostEqual(self.canvas.mark_centers[mark].x(), 15.0)
        self.assertAlmostEqual(self.canvas.mark_centers[mark].y(), 18.0)
        self.assertIsNotNone(arrow)
        self.assertIn(arrow, self.canvas.arrow_items)
        self.assertEqual(len(self.canvas.built_arrow_calls), 1)
        self.assertEqual(len(self.canvas.curved_arrow_path_calls), 1)
        self.assertIsNotNone(ts_bracket)
        self.assertIn(ts_bracket, self.canvas.ts_bracket_items)
        self.assertEqual(len(self.canvas.built_ts_bracket_rects), 1)
        self.assertIsNotNone(orbital)
        self.assertIn(orbital, self.canvas.orbital_items)
        self.assertEqual(self.canvas.built_orbital_calls[0][1], "sp2")

    def test_restore_helper_methods_return_none_for_invalid_state(self) -> None:
        self.assertIsNone(
            self.controller.restore_ring_from_state(
                {"points": [(0.0, 0.0), (1.0, 1.0)]}
            )
        )
        self.assertIsNone(
            self.controller.restore_mark_from_state(
                {"mark_kind": "plus", "atom_id": 99, "dx": 1.0, "dy": 2.0}
            )
        )
        self.assertIsNone(
            self.controller.restore_arrow_from_state(
                {"kind": "curved_double", "start": (1.0, 2.0)}
            )
        )
        self.assertIsNone(
            self.controller.restore_ts_bracket_from_state({"left": 1.0, "top": 2.0})
        )
        self.assertIsNone(
            self.controller.restore_orbital_from_state({"orbital_kind": "p"})
        )
        self.assertEqual(self.canvas.make_selectable_calls, [])
        self.assertEqual(self.canvas.ring_items, [])
        self.assertEqual(self.canvas.mark_items, [])
        self.assertEqual(self.canvas.arrow_items, [])
        self.assertEqual(self.canvas.ts_bracket_items, [])
        self.assertEqual(self.canvas.orbital_items, [])

    def test_create_scene_item_from_state_registers_supported_item_and_skips_invalid_inputs(
        self,
    ) -> None:
        self.canvas.model.atoms[3] = SimpleNamespace(x=4.0, y=5.0)

        note = self.controller.create_scene_item_from_state(
            {"kind": "note", "text": "A", "x": 1.0, "y": 2.0}
        )
        mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": "plus", "atom_id": 3, "dx": 2.0, "dy": -1.0}
        )
        default_mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": None, "atom_id": None, "x": 6.0, "y": 7.0}
        )
        unknown = self.controller.create_scene_item_from_state({"kind": "mystery"})
        invalid_ring = self.controller.create_scene_item_from_state(
            {"kind": "ring", "points": [(0.0, 0.0), (1.0, 1.0)]}
        )
        invalid_arrow = self.controller.create_scene_item_from_state(
            {"kind": "arrow", "start": (0.0, 0.0)}
        )
        invalid_mark = self.controller.create_scene_item_from_state(
            {"kind": "mark", "mark_kind": "missing", "atom_id": 3, "dx": 2.0, "dy": 1.0}
        )
        invalid_orbital = self.controller.create_scene_item_from_state(
            {"kind": "orbital", "orbital_kind": "missing"}
        )

        self.assertIsNotNone(note)
        self.assertIn(note, self.canvas.note_items)
        self.assertIsNotNone(mark)
        self.assertIn(mark, self.canvas.mark_items)
        self.assertIsNotNone(default_mark)
        self.assertIn(default_mark, self.canvas.mark_items)
        self.assertEqual(self.canvas.built_mark_kinds[:2], ["plus", "plus"])
        self.assertIsNone(unknown)
        self.assertIsNone(invalid_ring)
        self.assertIsNone(invalid_arrow)
        self.assertIsNone(invalid_mark)
        self.assertIsNone(invalid_orbital)

    def test_bond_ids_for_ring_item_returns_empty_for_short_or_invalid_sequences(
        self,
    ) -> None:
        short_ring = QGraphicsPolygonItem()
        short_ring.setData(2, "bad")
        mixed_ring = QGraphicsPolygonItem()
        mixed_ring.setData(2, [1, "bad", 2])
        self.canvas.bond_lookup = {(2, 1): 17}

        self.assertEqual(self.controller.bond_ids_for_ring_item(short_ring), set())
        self.assertEqual(self.controller.bond_ids_for_ring_item(mixed_ring), {17})

    def test_remove_scene_item_cleans_note_selection_and_handle_targets(self) -> None:
        note = QGraphicsTextItem("Label")
        note.setData(0, "note")
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")

        self.canvas.scene().addItem(note)
        self.canvas.note_items.append(note)
        self.canvas.selected_notes.append(note)
        self.canvas.scene().addItem(curved)
        self.canvas.arrow_items.append(curved)
        self.canvas.handle_state.target = curved

        self.controller.remove_scene_item(note)
        self.controller.remove_scene_item(curved)

        self.assertNotIn(note, self.canvas.selected_notes)
        self.assertEqual(self.canvas.updated_note_boxes, [note])
        self.assertNotIn(note, self.canvas.note_items)
        self.assertIsNone(note.scene())
        self.assertNotIn(curved, self.canvas.arrow_items)
        self.assertIsNone(curved.scene())
        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertIsNone(self.canvas.handle_state.target)

    def test_remove_scene_item_cleans_registries_even_if_scene_lookup_raises(
        self,
    ) -> None:
        broken_note = _BrokenSceneItem("note")
        self.canvas.note_items.append(broken_note)
        self.canvas.selected_notes.append(broken_note)

        self.controller.remove_scene_item(broken_note)

        self.assertNotIn(broken_note, self.canvas.note_items)
        self.assertNotIn(broken_note, self.canvas.selected_notes)
        self.assertEqual(self.canvas.updated_note_boxes, [broken_note])

    def test_remove_scene_item_handles_none_and_off_registry_variants(self) -> None:
        self.controller.remove_scene_item(None)

        note = QGraphicsTextItem("Loose")
        note.setData(0, "note")
        self.canvas.scene().addItem(note)
        curved = QGraphicsPathItem(QPainterPath())
        curved.setData(0, "curved_single")
        self.canvas.scene().addItem(curved)
        ts_bracket = QGraphicsPathItem(QPainterPath())
        ts_bracket.setData(0, "ts_bracket")
        self.canvas.scene().addItem(ts_bracket)
        self.canvas.ts_bracket_items.append(ts_bracket)
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")
        self.canvas.scene().addItem(orbital)
        self.canvas.handle_state.target = orbital

        self.controller.remove_scene_item(note)
        self.controller.remove_scene_item(curved)
        self.controller.remove_scene_item(ts_bracket)
        self.controller.remove_scene_item(orbital)

        self.assertEqual(self.canvas.updated_note_boxes, [note])
        self.assertIsNone(note.scene())
        self.assertIsNone(curved.scene())
        self.assertIsNone(ts_bracket.scene())
        self.assertNotIn(ts_bracket, self.canvas.ts_bracket_items)
        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertIsNone(orbital.scene())

    def test_remove_scene_item_cleans_mark_registry_after_helper_removal(self) -> None:
        mark = QGraphicsTextItem("-")
        mark.setData(0, "mark")
        mark.setData(1, {"atom_id": 11})
        self.canvas.scene().addItem(mark)
        self.canvas.mark_items.append(mark)
        self.canvas.mark_registry.by_atom[11] = [mark]

        self.controller.remove_scene_item(mark)

        self.assertEqual(self.canvas.removed_mark_items, [mark])
        self.assertNotIn(mark, self.canvas.mark_items)
        self.assertNotIn(11, self.canvas.mark_registry.by_atom)
        self.assertIsNone(mark.scene())

    def test_remove_scene_item_keeps_atom_mark_registry_when_sibling_remains_and_refreshes_detached_ring(
        self,
    ) -> None:
        first_mark = QGraphicsTextItem("-")
        first_mark.setData(0, "mark")
        first_mark.setData(1, {"atom_id": 11})
        second_mark = QGraphicsTextItem("+")
        second_mark.setData(0, "mark")
        second_mark.setData(1, {"atom_id": 11})
        self.canvas.scene().addItem(first_mark)
        self.canvas.mark_items.extend([first_mark, second_mark])
        self.canvas.mark_registry.by_atom[11] = [first_mark, second_mark]

        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {
            (1, 2): 101,
            (2, 3): 102,
            (3, 1): 103,
        }

        self.controller.remove_scene_item(first_mark)
        self.controller.remove_scene_item(ring)

        self.assertEqual(self.canvas.mark_registry.by_atom[11], [second_mark])
        self.assertEqual(self.canvas.removed_mark_items, [first_mark])
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

    def test_ring_restore_and_removal_refresh_each_bond_geometry(self) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(4.0, 0.0), QPointF(2.0, 3.0)])
        )
        ring.setData(0, "ring")
        ring.setData(2, [1, 2, 3])
        self.canvas.bond_lookup = {
            (1, 2): 101,
            (2, 3): 102,
            (3, 1): 103,
        }

        self.controller.restore_scene_item(ring)

        self.assertEqual(self.canvas.ring_items, [ring])
        self.assertIs(ring.scene(), self.canvas.scene())
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

        self.canvas.updated_bond_ids.clear()

        self.controller.remove_scene_item(ring)

        self.assertNotIn(ring, self.canvas.ring_items)
        self.assertIsNone(ring.scene())
        self.assertCountEqual(self.canvas.updated_bond_ids, [101, 102, 103])

    def test_remove_scene_item_clears_orbital_handle_target(self) -> None:
        orbital = QGraphicsItemGroup()
        orbital.setData(0, "orbital")
        self.canvas.scene().addItem(orbital)
        self.canvas.orbital_items.append(orbital)
        self.canvas.handle_state.target = orbital

        self.controller.remove_scene_item(orbital)

        self.assertEqual(self.canvas.clear_handles_calls, 1)
        self.assertNotIn(orbital, self.canvas.orbital_items)
        self.assertIsNone(orbital.scene())


if __name__ == "__main__":
    unittest.main()
