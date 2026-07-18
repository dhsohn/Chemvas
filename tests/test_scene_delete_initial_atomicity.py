import gc
import os
import unittest
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPen, QTransform
    from PyQt6.QtWidgets import QApplication, QGraphicsRectItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.core.history import (
        CompositeCommand,
        HistoryTransactionRestoreResult,
        SetSmilesInputCommand,
    )
    from chemvas.domain.document import Atom, Bond, MoleculeModel
    from chemvas.ui.atom_coords_access import atom_coords_3d_for
    from chemvas.ui.bond_graphics_access import add_bond_graphics_for
    from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
    from chemvas.ui.canvas_callback_state import callback_state_for
    from chemvas.ui.canvas_delete_transaction import (
        CanvasDeleteTransactionSnapshot,
        canvas_delete_transaction,
    )
    from chemvas.ui.canvas_group_state import (
        group_state_for,
        register_group_for,
        remove_group_for,
    )
    from chemvas.ui.canvas_mark_registry import mark_registry_for
    from chemvas.ui.canvas_scene_items_state import note_items_for, ring_items_for
    from chemvas.ui.canvas_smiles_input_state import (
        last_smiles_input_for,
        set_last_smiles_input_for,
    )
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.edit_tools import DeleteTool
    from chemvas.ui.history_commands import UngroupSceneItemsCommand
    from chemvas.ui.scene_delete_controller import (
        SceneDeleteController,
        SceneDeleteTransactionSession,
    )
    from chemvas.ui.scene_item_state import (
        atom_state_dict_for,
        bond_state_dict,
        mark_state_dict_for,
    )
    from chemvas.ui.selection_info_state import selection_info_state_for
    from chemvas.ui.structure_mutation_access import add_benzene_ring_for

    from tests.test_scene_ops_controller import (
        _FakeCanvas,
        _make_model_ring_item,
        _make_note_item,
        _make_rect_item,
        _make_ring_item,
        scene_delete_controller_for,
    )

    class _DeleteGestureEvent:
        def __init__(
            self,
            *,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        ) -> None:
            self._button = button
            self._buttons = buttons

        def button(self):
            return self._button

        def buttons(self):
            return self._buttons

    class _FailingCallbackPorts:
        def __init__(self, group_callback, outline_callback) -> None:
            self._group_callback = group_callback
            self._outline_callback = outline_callback
            self.group_getter_failures = 0
            self.group_setter_failures = 0
            self.group_restore_setter_failures = 0
            self.group_getter_reads = 0
            self.outline_getter_reads = 0
            self.group_setter_calls = 0
            self.outline_setter_calls = 0
            self.getter_error = AttributeError("group callback getter failed")
            self.setter_error = AttributeError("group callback setter failed")

        @property
        def scene_selection_group(self):
            self.group_getter_reads += 1
            if self.group_getter_failures:
                self.group_getter_failures -= 1
                raise self.getter_error
            return self._group_callback

        @scene_selection_group.setter
        def scene_selection_group(self, callback) -> None:
            self.group_setter_calls += 1
            if callback is not None and self.group_restore_setter_failures:
                self.group_restore_setter_failures -= 1
                raise self.setter_error
            self._group_callback = callback
            if self.group_setter_failures:
                self.group_setter_failures -= 1
                raise self.setter_error

        @property
        def scene_selection_outline(self):
            self.outline_getter_reads += 1
            return self._outline_callback

        @scene_selection_outline.setter
        def scene_selection_outline(self, callback) -> None:
            self.outline_setter_calls += 1
            self._outline_callback = callback


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for delete atomicity tests"
)
class SceneDeleteInitialAtomicityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._real_canvases: list[CanvasView] = []

    def tearDown(self) -> None:
        for canvas in self._real_canvases:
            scene = canvas.scene()
            if scene is not None:
                scene.blockSignals(True)
            canvas.deleteLater()
        self.app.processEvents()

    def _new_canvas(self) -> CanvasView:
        canvas = CanvasView()
        self._real_canvases.append(canvas)
        return canvas

    def test_delete_capture_data_failure_restores_unrelated_qt_item(self) -> None:
        canvas = self._new_canvas()
        unrelated = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        unrelated.setPos(QPointF(3.0, 4.0))
        canvas.scene().addItem(unrelated)
        before = QPointF(unrelated.pos())
        primary = SystemExit("delete capture data getter terminated")

        class PoisoningDataItem(QGraphicsRectItem):
            armed = False

            def data(self, role):
                if self.armed:
                    unrelated.moveBy(20.0, -9.0)
                    raise primary
                return super().data(role)

        item = PoisoningDataItem(0.0, 0.0, 2.0, 2.0)
        canvas.scene().addItem(item)
        item.armed = True

        with self.assertRaises(SystemExit) as caught:
            CanvasDeleteTransactionSnapshot.capture(
                canvas,
                history_service=canvas.services.history_service,
            )

        self.assertIs(caught.exception, primary)
        self.assertEqual(unrelated.pos(), before)
        item.armed = False

    def test_delete_model_field_capture_failure_unwinds_prior_getter_mutation(
        self,
    ) -> None:
        primary = KeyboardInterrupt("delete bond field capture terminated")

        class PoisoningModel:
            def __init__(self) -> None:
                self._atoms = {}
                self._bonds = []
                self.next_atom_id = 7
                self.atom_annotations = {}
                self.armed = True

            @property
            def atoms(self):
                if self.armed:
                    self.next_atom_id = 999
                return self._atoms

            @atoms.setter
            def atoms(self, value) -> None:
                self._atoms = value

            @property
            def bonds(self):
                if self.armed:
                    raise primary
                return self._bonds

            @bonds.setter
            def bonds(self, value) -> None:
                self._bonds = value

        model = PoisoningModel()
        canvas = type("DeleteCaptureCanvas", (), {})()
        canvas.model = model

        with self.assertRaises(KeyboardInterrupt) as caught:
            CanvasDeleteTransactionSnapshot.capture(canvas)

        self.assertIs(caught.exception, primary)
        self.assertEqual(model.next_atom_id, 7)

    def test_delete_canvas_model_getter_failure_restores_raw_model_graph(self) -> None:
        primary = KeyboardInterrupt("canvas model getter terminated")
        model = MoleculeModel(atoms={0: Atom("N", 1.0, 2.0)})
        atom = model.atoms[0]

        class PoisoningCanvas:
            def __init__(self) -> None:
                self._model = model
                self.armed = True

            @property
            def model(self):
                if self.armed:
                    self._model.atoms.clear()
                    raise primary
                return self._model

            @model.setter
            def model(self, value) -> None:
                self._model = value

        canvas = PoisoningCanvas()

        with self.assertRaises(KeyboardInterrupt) as caught:
            CanvasDeleteTransactionSnapshot.capture(canvas)

        self.assertIs(caught.exception, primary)
        self.assertIs(canvas._model, model)
        self.assertIs(model.atoms[0], atom)

    def test_direct_atom_failure_before_or_after_mutation_restores_marks_and_graphics_once(
        self,
    ) -> None:
        for fail_after_mutation in (False, True):
            with self.subTest(fail_after_mutation=fail_after_mutation):
                canvas = self._new_canvas()
                mutation_service = canvas.services.canvas_atom_mutation_service
                atom_id = mutation_service.add_atom("N", 10.0, 20.0)
                mark = canvas.services.canvas_mark_scene_service.add_mark_for_atom(
                    atom_id,
                    QPointF(22.0, 20.0),
                    kind="plus",
                    record=False,
                )
                self.assertIsNotNone(mark)
                assert mark is not None
                set_last_smiles_input_for(canvas, "N")
                atom_coords = atom_coords_3d_for(canvas)
                atom_coords[atom_id] = (10.0, 20.0, 3.0)
                canvas.model.atom_annotations[atom_id] = {"formal_charge": 1}

                history_state = canvas.services.history_service.state
                history_item = SetSmilesInputCommand("old", "current")
                redo_item = SetSmilesInputCommand("current", "future")
                history_state.history.append(history_item)
                history_state.redo_stack.append(redo_item)

                atom_before = atom_state_dict_for(canvas, atom_id)
                mark_before = mark_state_dict_for(canvas, mark)
                atom_object_before = canvas.model.atoms[atom_id]
                atom_item_before = atom_items_for(canvas)[atom_id]
                scene_order_before = list(canvas.scene().items())
                atom_coords_object = atom_coords
                atom_coords_before = dict(atom_coords)
                annotations_object = canvas.model.atom_annotations
                annotations_before = dict(canvas.model.atom_annotations)
                graph = canvas.runtime_state.graph_state
                neighbors_object = graph.atom_neighbors
                atom_neighbor_set = graph.atom_neighbors[atom_id]
                history_object = history_state.history
                redo_object = history_state.redo_stack
                original_remove = mutation_service.remove_atom_only
                call_count = 0

                def fail_persistently(
                    atom_id_to_remove: int,
                    remove_marks: bool = True,
                    *,
                    _fail_after_mutation: bool = fail_after_mutation,
                    _original_remove=original_remove,
                ) -> None:
                    nonlocal call_count
                    call_count += 1
                    if not _fail_after_mutation:
                        raise RuntimeError("atom-before")
                    _original_remove(atom_id_to_remove, remove_marks=remove_marks)
                    raise RuntimeError("atom-after")

                mutation_service.remove_atom_only = fail_persistently

                with self.assertRaisesRegex(RuntimeError, "atom-(before|after)"):
                    canvas.services.scene_delete_controller.delete_atom(
                        atom_id, record=True
                    )

                self.assertEqual(call_count, 1)
                self.assertEqual(atom_state_dict_for(canvas, atom_id), atom_before)
                self.assertIs(canvas.model.atoms[atom_id], atom_object_before)
                restored_marks = mark_registry_for(canvas).by_atom.get(atom_id, [])
                self.assertEqual(restored_marks, [mark])
                self.assertEqual(mark_state_dict_for(canvas, mark), mark_before)
                self.assertIs(mark.scene(), canvas.scene())
                self.assertIn(atom_id, atom_items_for(canvas))
                self.assertIs(atom_items_for(canvas)[atom_id], atom_item_before)
                self.assertIs(atom_item_before.scene(), canvas.scene())
                self.assertIs(atom_coords_3d_for(canvas), atom_coords_object)
                self.assertEqual(atom_coords_3d_for(canvas), atom_coords_before)
                self.assertIs(canvas.model.atom_annotations, annotations_object)
                self.assertEqual(canvas.model.atom_annotations, annotations_before)
                self.assertIs(graph.atom_neighbors, neighbors_object)
                self.assertIs(graph.atom_neighbors[atom_id], atom_neighbor_set)
                self.assertEqual(list(canvas.scene().items()), scene_order_before)
                self.assertEqual(last_smiles_input_for(canvas), "N")
                self.assertIs(history_state.history, history_object)
                self.assertIs(history_state.redo_stack, redo_object)
                self.assertEqual(history_state.history, [history_item])
                self.assertEqual(history_state.redo_stack, [redo_item])

    def test_direct_bond_failure_before_after_or_during_redraw_restores_graphics(
        self,
    ) -> None:
        for failure_stage in ("before_remove", "after_remove", "redraw"):
            with self.subTest(failure_stage=failure_stage):
                canvas = self._new_canvas()
                atom_service = canvas.services.canvas_atom_mutation_service
                bond_service = canvas.services.canvas_bond_mutation_service
                atom_a = atom_service.add_atom("N", 0.0, 0.0)
                atom_b = atom_service.add_atom("O", 40.0, 0.0)
                bond_id = bond_service.add_bond(atom_a, atom_b, 2)
                add_bond_graphics_for(canvas, bond_id)
                set_last_smiles_input_for(canvas, "N=O")

                bond_before = bond_state_dict(canvas.model.bonds[bond_id])
                graphics_before = list(bond_items_for_id(canvas, bond_id))
                self.assertTrue(graphics_before)
                graphics_mapping = canvas.runtime_state.bond_graphics_state.bond_items
                scene_order_before = list(canvas.scene().items())
                original_remove = bond_service.remove_bond_by_id
                original_redraw = canvas.services.move_controller.redraw_connected_bonds
                remove_calls = 0
                redraw_calls = 0

                def fail_remove_once(
                    bond_id_to_remove: int,
                    *,
                    _failure_stage: str = failure_stage,
                    _original_remove=original_remove,
                ) -> None:
                    nonlocal remove_calls
                    remove_calls += 1
                    if _failure_stage == "before_remove":
                        raise RuntimeError("bond-before")
                    _original_remove(bond_id_to_remove)
                    if _failure_stage == "after_remove":
                        raise RuntimeError("bond-after")

                def fail_redraw_once(
                    atom_id: int,
                    *,
                    skip_bond_id=None,
                    _failure_stage: str = failure_stage,
                    _original_redraw=original_redraw,
                ) -> None:
                    nonlocal redraw_calls
                    redraw_calls += 1
                    _original_redraw(atom_id, skip_bond_id=skip_bond_id)
                    if _failure_stage == "redraw":
                        raise RuntimeError("bond-redraw")

                bond_service.remove_bond_by_id = fail_remove_once
                canvas.services.move_controller.redraw_connected_bonds = (
                    fail_redraw_once
                )

                with self.assertRaisesRegex(RuntimeError, "bond-(before|after|redraw)"):
                    canvas.services.scene_delete_controller.delete_bond(
                        bond_id, record=True
                    )

                restored_bond = canvas.model.bonds[bond_id]
                self.assertIsNotNone(restored_bond)
                assert restored_bond is not None
                self.assertEqual(bond_state_dict(restored_bond), bond_before)
                restored_graphics = bond_items_for_id(canvas, bond_id)
                self.assertIs(
                    canvas.runtime_state.bond_graphics_state.bond_items,
                    graphics_mapping,
                )
                self.assertEqual(restored_graphics, graphics_before)
                self.assertTrue(
                    all(item.scene() is canvas.scene() for item in restored_graphics)
                )
                self.assertEqual(list(canvas.scene().items()), scene_order_before)
                self.assertEqual(last_smiles_input_for(canvas), "N=O")
                self.assertEqual(canvas.services.history_service.state.history, [])
                self.assertEqual(remove_calls, 1)
                self.assertLessEqual(redraw_calls, 1)

    def test_persistent_ring_refresh_failure_restores_every_original_bond_primitive_exactly(
        self,
    ) -> None:
        canvas = self._new_canvas()
        ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        self.assertIsNotNone(ring)
        assert ring is not None

        # Exercise each geometry-bearing bond primitive used by the renderer:
        # dotted creates a path, bold/wedge create polygons, and the remaining
        # benzene bonds retain line primitives.
        style_by_bond = {1: "dotted", 2: "bold", 3: "wedge"}
        for bond_id, style in style_by_bond.items():
            bond = canvas.model.bonds[bond_id]
            self.assertIsNotNone(bond)
            assert bond is not None
            bond.style = style
            self.assertTrue(canvas.bond_renderer.redraw_bond(bond_id))

        history_state = canvas.services.history_service.state
        history_state.history.clear()
        history_state.redo_stack.clear()
        graphics_mapping = canvas.runtime_state.bond_graphics_state.bond_items
        lists_before = dict(graphics_mapping)
        items_before = {
            bond_id: list(items) for bond_id, items in graphics_mapping.items()
        }
        scene_before = list(canvas.scene().items())

        property_names = (
            "transformOriginPoint",
            "transform",
            "rotation",
            "scale",
            "pos",
            "line",
            "path",
            "polygon",
            "rect",
            "pen",
            "brush",
        )

        def raw_state(item) -> tuple[tuple[str, object], ...]:
            values: list[tuple[str, object]] = []
            for name in property_names:
                getter = getattr(item, name, None)
                if callable(getter):
                    values.append((name, getter()))
            return tuple(values)

        states_before = {
            id(item): raw_state(item)
            for items in items_before.values()
            for item in items
        }
        primitive_getters = {
            name
            for items in items_before.values()
            for item in items
            for name in ("line", "path", "polygon")
            if callable(getattr(item, name, None))
        }
        self.assertEqual(primitive_getters, {"line", "path", "polygon"})

        refresh_calls: list[int] = []

        def mutate_then_fail_persistently(bond_id: int) -> None:
            refresh_calls.append(bond_id)
            for index, item in enumerate(graphics_mapping.get(bond_id, ())):
                delta = 9000.0 + len(refresh_calls) * 10.0 + index
                item.setPos(delta, delta + 1.0)
                transform = QTransform()
                transform.translate(delta + 2.0, delta + 3.0)
                transform.rotate(17.0)
                item.setTransform(transform)
                item.setTransformOriginPoint(delta + 4.0, delta + 5.0)
                item.setRotation(23.0)
                item.setScale(1.75)

                line_getter = getattr(item, "line", None)
                if callable(line_getter):
                    item.setLine(delta, delta + 1.0, delta + 2.0, delta + 3.0)
                path_getter = getattr(item, "path", None)
                if callable(path_getter):
                    path = path_getter()
                    path.translate(delta, delta + 1.0)
                    item.setPath(path)
                polygon_getter = getattr(item, "polygon", None)
                if callable(polygon_getter):
                    polygon = polygon_getter()
                    polygon.translate(delta, delta + 1.0)
                    item.setPolygon(polygon)
                rect_getter = getattr(item, "rect", None)
                if callable(rect_getter):
                    rect = rect_getter()
                    rect.translate(delta, delta + 1.0)
                    item.setRect(rect)
                pen_getter = getattr(item, "pen", None)
                if callable(pen_getter):
                    pen = QPen(pen_getter())
                    pen.setColor(QColor("#dc143c"))
                    pen.setWidthF(pen.widthF() + 3.0)
                    item.setPen(pen)
                brush_getter = getattr(item, "brush", None)
                if callable(brush_getter):
                    item.setBrush(QBrush(QColor("#00ced1")))
            raise RuntimeError("persistent geometry refresh")

        canvas.bond_renderer.update_bond_geometry = mutate_then_fail_persistently

        with self.assertRaisesRegex(RuntimeError, "persistent geometry refresh"):
            canvas.services.scene_delete_controller.delete_bond(0, record=False)

        self.assertGreaterEqual(len(refresh_calls), len(canvas.model.bonds))
        self.assertIs(
            canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping
        )
        for bond_id, original_list in lists_before.items():
            self.assertIs(graphics_mapping[bond_id], original_list)
            self.assertEqual(graphics_mapping[bond_id], items_before[bond_id])
            for item in graphics_mapping[bond_id]:
                self.assertEqual(raw_state(item), states_before[id(item)])
                self.assertIs(item.scene(), canvas.scene())
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertIn(ring, ring_items_for(canvas))
        self.assertIs(ring.scene(), canvas.scene())
        self.assertIsNotNone(canvas.model.bonds[0])
        self.assertEqual(history_state.history, [])
        self.assertEqual(history_state.redo_stack, [])

    def test_ring_history_undo_and_redo_persistent_refresh_failure_restore_raw_graphics(
        self,
    ) -> None:
        property_names = (
            "transformOriginPoint",
            "transform",
            "rotation",
            "scale",
            "pos",
            "line",
            "path",
            "polygon",
            "rect",
            "pen",
            "brush",
        )

        def raw_state(item) -> tuple[tuple[str, object], ...]:
            return tuple(
                (name, getter())
                for name in property_names
                if callable(getter := getattr(item, name, None))
            )

        for history_operation in ("undo", "redo"):
            with self.subTest(history_operation=history_operation):
                canvas = self._new_canvas()
                ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
                self.assertIsNotNone(ring)
                assert ring is not None
                for bond_id, style in {1: "dotted", 2: "bold", 3: "wedge"}.items():
                    bond = canvas.model.bonds[bond_id]
                    self.assertIsNotNone(bond)
                    assert bond is not None
                    bond.style = style
                    self.assertTrue(canvas.bond_renderer.redraw_bond(bond_id))

                history = canvas.services.history_service
                history.clear()
                canvas.services.scene_delete_controller.delete_ring(ring, record=True)
                if history_operation == "redo":
                    history.undo()

                ring_was_attached = ring.scene() is canvas.scene()
                ring_registry_before = list(ring_items_for(canvas))
                graphics_mapping = canvas.runtime_state.bond_graphics_state.bond_items
                lists_before = dict(graphics_mapping)
                items_before = {
                    bond_id: list(items) for bond_id, items in graphics_mapping.items()
                }
                states_before = {
                    id(item): raw_state(item)
                    for items in items_before.values()
                    for item in items
                }
                refresh_calls: list[int] = []

                def mutate_then_fail_persistently(
                    bond_id: int,
                    *,
                    _refresh_calls=refresh_calls,
                    _graphics_mapping=graphics_mapping,
                    _history_operation=history_operation,
                ) -> None:
                    _refresh_calls.append(bond_id)
                    delta = 7000.0 + len(_refresh_calls) * 10.0
                    for item in _graphics_mapping.get(bond_id, ()):
                        item.setPos(delta, delta + 1.0)
                        line_getter = getattr(item, "line", None)
                        if callable(line_getter):
                            item.setLine(delta, delta + 1.0, delta + 2.0, delta + 3.0)
                        path_getter = getattr(item, "path", None)
                        if callable(path_getter):
                            path = path_getter()
                            path.translate(delta, delta + 1.0)
                            item.setPath(path)
                        polygon_getter = getattr(item, "polygon", None)
                        if callable(polygon_getter):
                            polygon = polygon_getter()
                            polygon.translate(delta, delta + 1.0)
                            item.setPolygon(polygon)
                        pen_getter = getattr(item, "pen", None)
                        if callable(pen_getter):
                            pen = QPen(pen_getter())
                            pen.setColor(QColor("#ff1493"))
                            item.setPen(pen)
                        brush_getter = getattr(item, "brush", None)
                        if callable(brush_getter):
                            item.setBrush(QBrush(QColor("#7fff00")))
                    raise RuntimeError(
                        f"persistent history {_history_operation} refresh"
                    )

                canvas.bond_renderer.update_bond_geometry = (
                    mutate_then_fail_persistently
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    f"persistent history {history_operation} refresh",
                ):
                    getattr(history, history_operation)()

                self.assertTrue(refresh_calls)
                self.assertEqual(ring.scene() is canvas.scene(), ring_was_attached)
                self.assertEqual(ring_items_for(canvas), ring_registry_before)
                self.assertIs(
                    canvas.runtime_state.bond_graphics_state.bond_items,
                    graphics_mapping,
                )
                for bond_id, original_list in lists_before.items():
                    self.assertIs(graphics_mapping[bond_id], original_list)
                    self.assertEqual(graphics_mapping[bond_id], items_before[bond_id])
                    for item in graphics_mapping[bond_id]:
                        self.assertEqual(raw_state(item), states_before[id(item)])
                        self.assertIs(item.scene(), canvas.scene())
                self.assertEqual(history.state.history, [])
                self.assertEqual(history.state.redo_stack, [])

    def test_direct_ring_failure_after_mutation_restores_single_registration(
        self,
    ) -> None:
        canvas = self._new_canvas()
        ring = _make_ring_item()
        scene_item_controller = canvas.services.scene_item_controller
        scene_item_controller.attach_scene_item(ring)
        original_remove = scene_item_controller.remove_scene_item
        call_count = 0

        def fail_persistently(item) -> None:
            nonlocal call_count
            call_count += 1
            original_remove(item)
            raise RuntimeError("ring-after")

        scene_item_controller.remove_scene_item = fail_persistently

        with self.assertRaisesRegex(RuntimeError, "ring-after"):
            canvas.services.scene_delete_controller.delete_ring(ring, record=True)

        self.assertEqual(call_count, 1)
        self.assertIs(ring.scene(), canvas.scene())
        self.assertEqual(ring_items_for(canvas).count(ring), 1)
        self.assertEqual(canvas.services.history_service.state.history, [])

    def test_direct_bond_initial_failure_does_not_double_compensate_ring_cleanup(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
            },
            bonds=[Bond(0, 1), Bond(1, 2), Bond(2, 0)],
            next_atom_id=3,
        )
        ring = _make_model_ring_item(
            canvas.model,
            [0, 1, 2],
            color="#336699",
            alpha=0.4,
        )
        canvas.ring_items.append(ring)
        canvas.add_item(ring)
        original_remove = canvas._remove_bond_by_id
        call_count = 0

        def fail_once(bond_id: int) -> None:
            nonlocal call_count
            call_count += 1
            original_remove(bond_id)
            if call_count == 1:
                raise RuntimeError("bond-before-ring-cleanup")

        canvas.services.canvas_bond_mutation_service.remove_bond_by_id = fail_once

        with self.assertRaisesRegex(RuntimeError, "bond-before-ring-cleanup"):
            scene_delete_controller_for(canvas).delete_bond(0, record=True)

        self.assertIsNotNone(canvas.model.bonds[0])
        self.assertEqual(canvas.ring_items.count(ring), 1)
        self.assertIs(ring.scene(), canvas.scene())
        self.assertEqual(canvas.removed_scene_items, [])
        self.assertEqual(canvas.pushed_commands, [])

    def test_multi_bond_redraw_failure_restores_all_completed_and_current_bonds(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
                3: Atom("C", 40.0, 0.0),
            },
            bonds=[Bond(1, 2, 1), Bond(2, 3, 2)],
            next_atom_id=4,
        )
        bonds_before = [
            bond_state_dict(bond) for bond in canvas.model.bonds if bond is not None
        ]
        for bond_id in (0, 1):
            canvas.add_item(_make_rect_item("bond", data1=bond_id), selected=True)
        set_last_smiles_input_for(canvas, "CCC")
        original_redraw = canvas.redraw_connected_bonds
        redraw_count = 0

        def fail_on_third_redraw(atom_id: int, skip_bond_id=None) -> None:
            nonlocal redraw_count
            redraw_count += 1
            original_redraw(atom_id, skip_bond_id=skip_bond_id)
            if redraw_count == 3:
                raise RuntimeError("multi-bond-redraw")

        canvas.services.move_controller.redraw_connected_bonds = fail_on_third_redraw

        with self.assertRaisesRegex(RuntimeError, "multi-bond-redraw"):
            scene_delete_controller_for(canvas).delete_selected_items()

        self.assertEqual(
            [bond_state_dict(bond) for bond in canvas.model.bonds if bond is not None],
            bonds_before,
        )
        self.assertEqual(last_smiles_input_for(canvas), "CCC")
        self.assertEqual(canvas.pushed_commands, [])

    def test_multi_atom_second_failure_restores_attempted_atoms_without_touching_future_atom(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
                3: Atom("N", 40.0, 0.0),
            },
            bonds=[],
            next_atom_id=4,
        )
        atoms_before = {
            atom_id: atom_state_dict_for(canvas, atom_id)
            for atom_id in canvas.model.atoms
        }
        for atom_id in (1, 2, 3):
            canvas.add_item(_make_rect_item("atom", data1=atom_id), selected=True)
        set_last_smiles_input_for(canvas, "CON")
        original_remove = canvas._remove_atom_only
        initially_attempted: list[int] = []
        failed = False

        def fail_on_second_atom(atom_id: int, remove_marks: bool = True) -> None:
            nonlocal failed
            if not failed:
                initially_attempted.append(atom_id)
            original_remove(atom_id, remove_marks=remove_marks)
            if not failed and len(initially_attempted) == 2:
                failed = True
                raise RuntimeError("multi-atom-second")

        canvas.services.canvas_atom_mutation_service.remove_atom_only = (
            fail_on_second_atom
        )

        with self.assertRaisesRegex(RuntimeError, "multi-atom-second"):
            scene_delete_controller_for(canvas).delete_selected_items()

        self.assertEqual(initially_attempted, [1, 2])
        self.assertFalse(any(atom_id == 3 for atom_id, _ in canvas.remove_atom_calls))
        self.assertEqual(
            {
                atom_id: atom_state_dict_for(canvas, atom_id)
                for atom_id in canvas.model.atoms
            },
            atoms_before,
        )
        self.assertEqual(canvas.model.next_atom_id, 4)
        self.assertEqual(last_smiles_input_for(canvas), "CON")
        self.assertEqual(canvas.pushed_commands, [])

    def test_multi_scene_second_failure_restores_attempted_items_and_skips_future_item(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        notes = [
            _make_note_item("one", 10.0, 10.0),
            _make_note_item("two", 20.0, 20.0),
            _make_note_item("three", 30.0, 30.0),
        ]
        for note in notes:
            canvas.add_item(note, selected=True)
        scene_item_controller = canvas.services.scene_item_controller
        original_remove = scene_item_controller.remove_scene_item
        initially_attempted: list[object] = []
        failed = False

        def fail_on_second_item(item) -> None:
            nonlocal failed
            if not failed:
                initially_attempted.append(item)
            original_remove(item)
            if not failed and len(initially_attempted) == 2:
                failed = True
                raise RuntimeError("multi-scene-second")

        scene_item_controller.remove_scene_item = fail_on_second_item

        with self.assertRaisesRegex(RuntimeError, "multi-scene-second"):
            scene_delete_controller_for(canvas).delete_selected_items()

        self.assertEqual(len(initially_attempted), 2)
        untouched_items = [item for item in notes if item not in initially_attempted]
        self.assertEqual(len(untouched_items), 1)
        self.assertNotIn(untouched_items[0], canvas.removed_scene_items)
        self.assertTrue(all(item.scene() is canvas.scene() for item in notes))
        self.assertEqual(canvas.pushed_commands, [])

    def test_selection_delete_preserves_body_error_and_runs_both_cleanup_phases(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_service = canvas.services.canvas_atom_mutation_service
        bond_service = canvas.services.canvas_bond_mutation_service
        atom_a = atom_service.add_atom("C", 0.0, 0.0)
        atom_b = atom_service.add_atom("C", 40.0, 0.0)
        bond_id = bond_service.add_bond(atom_a, atom_b)
        add_bond_graphics_for(canvas, bond_id)
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        bond_item.setSelected(True)

        scene_before = list(canvas.scene().items())
        graphics_before = list(bond_items_for_id(canvas, bond_id))
        cleanup_calls: list[tuple[str, bool | None]] = []
        original_suspend = canvas.services.style_controller.suspend_selection_outline

        def fail_body(_bond_id: int) -> None:
            raise ValueError("original delete failure")

        def fail_resume(suspend: bool) -> None:
            cleanup_calls.append(("suspend", suspend))
            if not suspend:
                raise RuntimeError("resume cleanup failure")
            original_suspend(suspend)

        def fail_refresh() -> None:
            cleanup_calls.append(("refresh", None))
            raise LookupError("refresh cleanup failure")

        bond_service.remove_bond_by_id = fail_body
        canvas.services.style_controller.suspend_selection_outline = fail_resume
        canvas.services.selection_controller.update_selection_outline = fail_refresh

        with self.assertRaisesRegex(ValueError, "original delete failure") as caught:
            canvas.services.scene_delete_controller.delete_selected_items()

        notes = getattr(caught.exception, "__notes__", [])
        self.assertTrue(any("resume cleanup failure" in note for note in notes))
        self.assertTrue(any("refresh cleanup failure" in note for note in notes))
        self.assertEqual(
            cleanup_calls,
            [("suspend", True), ("suspend", False), ("refresh", None)],
        )
        self.assertIsNotNone(canvas.model.bonds[bond_id])
        self.assertEqual(bond_items_for_id(canvas, bond_id), graphics_before)
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertFalse(canvas.runtime_state.selection_style_state.suspend_outline)
        self.assertEqual(canvas.services.history_service.state.history, [])

    def test_selection_delete_success_cleanup_failure_rolls_back_and_raises_first_cleanup_error(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_service = canvas.services.canvas_atom_mutation_service
        bond_service = canvas.services.canvas_bond_mutation_service
        atom_a = atom_service.add_atom("C", 0.0, 0.0)
        atom_b = atom_service.add_atom("C", 40.0, 0.0)
        bond_id = bond_service.add_bond(atom_a, atom_b)
        add_bond_graphics_for(canvas, bond_id)
        bond_item = bond_items_for_id(canvas, bond_id)[0]
        bond_item.setSelected(True)

        scene_before = list(canvas.scene().items())
        graphics_mapping = canvas.runtime_state.bond_graphics_state.bond_items
        graphics_list = graphics_mapping[bond_id]
        graphics_before = list(graphics_list)
        history = canvas.services.history_service
        history_observations: list[bool] = []
        history.set_change_callback(
            lambda: history_observations.append(history.can_undo())
        )
        cleanup_calls: list[tuple[str, bool | None]] = []
        original_suspend = canvas.services.style_controller.suspend_selection_outline

        def fail_resume(suspend: bool) -> None:
            cleanup_calls.append(("suspend", suspend))
            if not suspend:
                raise RuntimeError("first cleanup failure")
            original_suspend(suspend)

        def fail_refresh() -> None:
            cleanup_calls.append(("refresh", None))
            raise LookupError("second cleanup failure")

        canvas.services.style_controller.suspend_selection_outline = fail_resume
        canvas.services.selection_controller.update_selection_outline = fail_refresh

        with self.assertRaisesRegex(RuntimeError, "first cleanup failure") as caught:
            canvas.services.scene_delete_controller.delete_selected_items()

        notes = getattr(caught.exception, "__notes__", [])
        self.assertTrue(any("second cleanup failure" in note for note in notes))
        self.assertEqual(
            cleanup_calls,
            [("suspend", True), ("suspend", False), ("refresh", None)],
        )
        self.assertIsNotNone(canvas.model.bonds[bond_id])
        self.assertIs(
            canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping
        )
        self.assertIs(graphics_mapping[bond_id], graphics_list)
        self.assertEqual(graphics_mapping[bond_id], graphics_before)
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertFalse(canvas.runtime_state.selection_style_state.suspend_outline)
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [])
        self.assertEqual(history_observations, [True, False])

    def test_selected_group_delete_undo_redo_preserves_group_identity_and_releases_evicted_items(
        self,
    ) -> None:
        canvas = self._new_canvas()
        item_controller = canvas.services.scene_item_controller
        items = [_make_rect_item("shape") for _ in range(2)]
        items[1].setPos(30.0, 0.0)
        for item in items:
            item_controller.attach_scene_item(item)
            item.setSelected(True)

        group_state = group_state_for(canvas)
        groups_object = group_state.groups
        group_id = register_group_for(canvas, set(), items)
        group_object = group_state.groups[group_id]
        member_set = group_object.atom_ids
        member_list = group_object.items
        item_refs = [weakref.ref(item) for item in items]

        self.assertTrue(canvas.services.scene_delete_controller.delete_selected_items())

        command = canvas.services.history_service.state.history[-1]
        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], UngroupSceneItemsCommand)
        self.assertNotIn(group_id, group_state.groups)
        self.assertTrue(all(item.scene() is None for item in items))

        canvas.services.history_service.undo()

        self.assertIs(group_state.groups, groups_object)
        self.assertIs(group_state.groups[group_id], group_object)
        self.assertIs(group_state.groups[group_id].atom_ids, member_set)
        self.assertIs(group_state.groups[group_id].items, member_list)
        self.assertTrue(all(item.scene() is canvas.scene() for item in items))

        canvas.services.history_service.redo()

        self.assertNotIn(group_id, group_state.groups)
        self.assertTrue(all(item.scene() is None for item in items))

        canvas.services.history_service.clear()
        del command
        del group_object
        del member_set
        del member_list
        del item
        del items
        gc.collect()
        self.app.processEvents()
        gc.collect()
        self.assertTrue(all(item_ref() is None for item_ref in item_refs))

    def test_direct_atom_delete_removes_overlapping_group_and_undo_restores_exact_group(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 10.0, 20.0)
        group_state = group_state_for(canvas)
        groups_object = group_state.groups
        group_id = register_group_for(canvas, {atom_id}, [])
        group_object = group_state.groups[group_id]
        atom_ids_object = group_object.atom_ids
        items_object = group_object.items

        command = canvas.services.scene_delete_controller.delete_atom(
            atom_id, record=True
        )

        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], UngroupSceneItemsCommand)
        self.assertNotIn(group_id, group_state.groups)
        self.assertNotIn(atom_id, canvas.model.atoms)

        canvas.services.history_service.undo()

        self.assertIn(atom_id, canvas.model.atoms)
        self.assertIs(group_state.groups, groups_object)
        self.assertIs(group_state.groups[group_id], group_object)
        self.assertIs(group_state.groups[group_id].atom_ids, atom_ids_object)
        self.assertIs(group_state.groups[group_id].items, items_object)

        canvas.services.history_service.redo()

        self.assertNotIn(atom_id, canvas.model.atoms)
        self.assertNotIn(group_id, group_state.groups)

    def test_direct_ring_and_broken_ring_cleanup_remove_overlapping_groups_in_history_order(
        self,
    ) -> None:
        direct_canvas = self._new_canvas()
        direct_ring = _make_ring_item()
        direct_canvas.services.scene_item_controller.attach_scene_item(direct_ring)
        direct_group_state = group_state_for(direct_canvas)
        direct_group_id = register_group_for(direct_canvas, set(), [direct_ring])
        direct_group = direct_group_state.groups[direct_group_id]

        direct_command = direct_canvas.services.scene_delete_controller.delete_ring(
            direct_ring,
            record=True,
        )

        self.assertIsInstance(direct_command, CompositeCommand)
        assert isinstance(direct_command, CompositeCommand)
        self.assertIsInstance(direct_command.commands[0], UngroupSceneItemsCommand)
        self.assertNotIn(direct_group_id, direct_group_state.groups)
        direct_canvas.services.history_service.undo()
        self.assertIs(direct_group_state.groups[direct_group_id], direct_group)
        self.assertIs(direct_ring.scene(), direct_canvas.scene())
        direct_canvas.services.history_service.redo()
        self.assertNotIn(direct_group_id, direct_group_state.groups)
        self.assertIsNone(direct_ring.scene())

        broken_canvas = self._new_canvas()
        broken_ring = add_benzene_ring_for(broken_canvas, QPointF(0.0, 0.0))
        self.assertIsNotNone(broken_ring)
        assert broken_ring is not None
        broken_canvas.services.history_service.clear()
        broken_group_state = group_state_for(broken_canvas)
        broken_group_id = register_group_for(broken_canvas, set(), [broken_ring])
        broken_group = broken_group_state.groups[broken_group_id]

        broken_command = broken_canvas.services.scene_delete_controller.delete_bond(
            0,
            record=True,
        )

        self.assertIsInstance(broken_command, CompositeCommand)
        assert isinstance(broken_command, CompositeCommand)
        self.assertIsInstance(broken_command.commands[0], UngroupSceneItemsCommand)
        self.assertNotIn(broken_group_id, broken_group_state.groups)
        self.assertIsNone(broken_ring.scene())
        broken_canvas.services.history_service.undo()
        self.assertIs(broken_group_state.groups[broken_group_id], broken_group)
        self.assertIs(broken_ring.scene(), broken_canvas.scene())
        self.assertIsNotNone(broken_canvas.model.bonds[0])
        broken_canvas.services.history_service.redo()
        self.assertNotIn(broken_group_id, broken_group_state.groups)
        self.assertIsNone(broken_ring.scene())
        self.assertIsNone(broken_canvas.model.bonds[0])

    def test_group_remove_and_cleanup_refresh_failures_restore_nested_group_state_exactly(
        self,
    ) -> None:
        for failure_stage in ("group_remove", "cleanup_refresh"):
            with self.subTest(failure_stage=failure_stage):
                canvas = self._new_canvas()
                item_controller = canvas.services.scene_item_controller
                items = [_make_rect_item("shape") for _ in range(2)]
                items[1].setPos(30.0, 0.0)
                for item in items:
                    item_controller.attach_scene_item(item)
                    item.setSelected(True)

                group_state = group_state_for(canvas)
                groups_object = group_state.groups
                group_id = register_group_for(canvas, {101, 102}, items)
                next_group_id = group_state.next_group_id
                group_object = group_state.groups[group_id]
                atom_ids_object = group_object.atom_ids
                atom_ids_before = set(atom_ids_object)
                items_object = group_object.items
                items_before = list(items_object)
                scene_before = list(canvas.scene().items())

                if failure_stage == "group_remove":

                    def mutate_group_then_fail(
                        canvas_arg,
                        group_id_to_remove: int,
                        *,
                        _canvas=canvas,
                        _group_object=group_object,
                    ):
                        self.assertIs(canvas_arg, _canvas)
                        removed = remove_group_for(canvas_arg, group_id_to_remove)
                        self.assertIs(removed, _group_object)
                        _group_object.atom_ids = set()
                        _group_object.items = []
                        raise RuntimeError("persistent group removal failure")

                    patcher = mock.patch(
                        "chemvas.ui.scene_delete_controller.remove_group_for",
                        side_effect=mutate_group_then_fail,
                    )
                else:

                    def mutate_every_group_layer_then_fail(
                        *,
                        _atom_ids_object=atom_ids_object,
                        _items_object=items_object,
                        _group_object=group_object,
                        _group_state=group_state,
                    ) -> None:
                        _atom_ids_object.clear()
                        _items_object.clear()
                        _group_object.atom_ids = set()
                        _group_object.items = []
                        _group_state.groups = {}
                        _group_state.next_group_id = 999
                        _group_state.expanding = True
                        raise RuntimeError("persistent group refresh failure")

                    patcher = mock.patch.object(
                        canvas.services.selection_controller,
                        "update_selection_outline",
                        side_effect=mutate_every_group_layer_then_fail,
                    )

                with patcher:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        f"persistent group {'removal' if failure_stage == 'group_remove' else 'refresh'} failure",
                    ):
                        canvas.services.scene_delete_controller.delete_selected_items()

                self.assertIs(group_state.groups, groups_object)
                self.assertEqual(list(group_state.groups), [group_id])
                self.assertIs(group_state.groups[group_id], group_object)
                self.assertIs(group_object.atom_ids, atom_ids_object)
                self.assertEqual(group_object.atom_ids, atom_ids_before)
                self.assertIs(group_object.items, items_object)
                self.assertEqual(group_object.items, items_before)
                self.assertEqual(group_state.next_group_id, next_group_id)
                self.assertFalse(group_state.expanding)
                self.assertTrue(all(item.scene() is canvas.scene() for item in items))
                self.assertTrue(all(item.isSelected() for item in items))
                self.assertEqual(list(canvas.scene().items()), scene_before)
                self.assertEqual(canvas.services.history_service.state.history, [])
                self.assertEqual(canvas.services.history_service.state.redo_stack, [])

    def test_interleaved_scene_item_failure_restores_registry_and_stacking_exactly(
        self,
    ) -> None:
        canvas = self._new_canvas()
        controller = canvas.services.scene_delete_controller
        item_controller = canvas.services.scene_item_controller
        notes = [
            _make_note_item("zero", 10.0, 10.0),
            _make_note_item("one", 20.0, 20.0),
            _make_note_item("two", 30.0, 30.0),
        ]
        for note in notes:
            item_controller.attach_scene_item(note)
        notes[0].setSelected(True)
        notes[2].setSelected(True)

        registry = note_items_for(canvas)
        registry_before = list(registry)
        scene_before = list(canvas.scene().items())
        original_remove = item_controller.remove_scene_item
        remove_calls = 0

        def fail_after_second_remove(item) -> None:
            nonlocal remove_calls
            remove_calls += 1
            original_remove(item)
            if remove_calls == 2:
                raise RuntimeError("interleaved-scene")

        item_controller.remove_scene_item = fail_after_second_remove

        with self.assertRaisesRegex(RuntimeError, "interleaved-scene"):
            controller.delete_selected_items()

        self.assertEqual(remove_calls, 2)
        self.assertIs(note_items_for(canvas), registry)
        self.assertEqual(note_items_for(canvas), registry_before)
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertTrue(notes[0].isSelected())
        self.assertFalse(notes[1].isSelected())
        self.assertTrue(notes[2].isSelected())
        self.assertEqual(canvas.services.history_service.state.history, [])

    def test_interleaved_broken_ring_failure_restores_registry_and_stacking_exactly(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
                3: Atom("C", 40.0, 0.0),
                4: Atom("C", 60.0, 0.0),
                5: Atom("C", 50.0, 16.0),
            },
            bonds=[
                Bond(0, 1),
                Bond(1, 2),
                Bond(2, 0),
                Bond(3, 4),
                Bond(4, 5),
                Bond(5, 3),
            ],
            next_atom_id=6,
        )
        broken_first = _make_model_ring_item(
            canvas.model,
            [0, 1, 2],
            color="#aa0000",
            alpha=0.2,
        )
        valid_middle = _make_model_ring_item(
            canvas.model,
            [3, 4, 5],
            color="#00aa00",
            alpha=0.2,
        )
        broken_last = _make_model_ring_item(
            canvas.model,
            [0, 1, 2],
            color="#0000aa",
            alpha=0.2,
        )
        for ring in (broken_first, valid_middle, broken_last):
            canvas.ring_items.append(ring)
            canvas.add_item(ring)

        controller = scene_delete_controller_for(canvas)
        registry = canvas.ring_items
        registry_before = list(registry)
        scene_before = list(canvas.scene().items())
        original_remove = controller._remove_scene_item
        remove_calls = 0

        def fail_after_second_remove(item) -> None:
            nonlocal remove_calls
            remove_calls += 1
            original_remove(item)
            if remove_calls == 2:
                raise RuntimeError("interleaved-ring")

        controller._remove_scene_item = fail_after_second_remove

        with self.assertRaisesRegex(RuntimeError, "interleaved-ring"):
            controller.delete_bond(0, record=False)

        self.assertEqual(remove_calls, 2)
        self.assertIs(canvas.ring_items, registry)
        self.assertEqual(canvas.ring_items, registry_before)
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertIsNotNone(canvas.model.bonds[0])
        self.assertEqual(canvas.pushed_commands, [])

    def test_history_mutate_then_raise_restores_stack_and_deleted_item(self) -> None:
        canvas = self._new_canvas()
        ring = _make_ring_item()
        canvas.services.scene_item_controller.attach_scene_item(ring)
        history = canvas.services.history_service
        history_item = SetSmilesInputCommand("old", "current")
        redo_item = SetSmilesInputCommand("current", "future")
        history.state.history.append(history_item)
        history.state.redo_stack.append(redo_item)
        history_object = history.state.history
        redo_object = history.state.redo_stack
        scene_before = list(canvas.scene().items())

        def mutate_then_fail(command) -> None:
            history.state.history.append(command)
            history.state.redo_stack.clear()
            raise RuntimeError("history-after")

        history.push = mutate_then_fail

        with self.assertRaisesRegex(RuntimeError, "history-after"):
            canvas.services.scene_delete_controller.delete_ring(ring, record=True)

        self.assertIs(history.state.history, history_object)
        self.assertIs(history.state.redo_stack, redo_object)
        self.assertEqual(history.state.history, [history_item])
        self.assertEqual(history.state.redo_stack, [redo_item])
        self.assertEqual(ring_items_for(canvas), [ring])
        self.assertIs(ring.scene(), canvas.scene())
        self.assertEqual(list(canvas.scene().items()), scene_before)

    def test_rollback_failure_does_not_mask_original_delete_error(self) -> None:
        canvas = self._new_canvas()
        with mock.patch.object(
            CanvasDeleteTransactionSnapshot,
            "restore",
            side_effect=RuntimeError("rollback-error"),
        ):
            with self.assertRaisesRegex(ValueError, "original-error") as caught:
                with canvas_delete_transaction(canvas):
                    raise ValueError("original-error")

        self.assertTrue(
            any(
                "rollback-error" in note
                for note in getattr(caught.exception, "__notes__", [])
            )
        )

    def test_delete_tool_push_failures_restore_the_exact_pre_gesture_state(
        self,
    ) -> None:
        for failure_stage in ("before_append", "after_append"):
            with self.subTest(failure_stage=failure_stage):
                canvas = self._new_canvas()
                atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
                    "N",
                    10.0,
                    20.0,
                )
                atom = canvas.model.atoms[atom_id]
                atom_registry = atom_items_for(canvas)
                atom_item = atom_registry[atom_id]
                atom_item.setSelected(True)
                set_last_smiles_input_for(canvas, "N")

                history = canvas.services.history_service
                history_item = SetSmilesInputCommand("old", "current")
                redo_item = SetSmilesInputCommand("current", "future")
                history.state.history.append(history_item)
                history.state.redo_stack.append(redo_item)
                history_object = history.state.history
                redo_object = history.state.redo_stack
                atoms_object = canvas.model.atoms
                scene_before = list(canvas.scene().items())

                tool = DeleteTool(canvas, context=canvas.services.tools.context)
                with mock.patch.object(
                    canvas.services.hit_testing_service,
                    "item_at_event",
                    return_value=atom_item,
                ):
                    self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
                self.assertNotIn(atom_id, canvas.model.atoms)

                def fail_push(
                    command,
                    *,
                    _failure_stage=failure_stage,
                    _history=history,
                ) -> None:
                    if _failure_stage == "after_append":
                        _history.state.history.append(command)
                        _history.state.redo_stack.clear()
                    raise RuntimeError(f"push-{_failure_stage}")

                with mock.patch.object(history, "push", side_effect=fail_push):
                    with self.assertRaisesRegex(RuntimeError, f"push-{failure_stage}"):
                        tool.on_mouse_release(_DeleteGestureEvent())

                self.assertIs(canvas.model.atoms, atoms_object)
                self.assertIs(canvas.model.atoms[atom_id], atom)
                self.assertIs(atom_items_for(canvas), atom_registry)
                self.assertIs(atom_items_for(canvas)[atom_id], atom_item)
                self.assertIs(atom_item.scene(), canvas.scene())
                self.assertTrue(atom_item.isSelected())
                self.assertEqual(list(canvas.scene().items()), scene_before)
                self.assertEqual(last_smiles_input_for(canvas), "N")
                self.assertIs(history.state.history, history_object)
                self.assertIs(history.state.redo_stack, redo_object)
                self.assertEqual(history.state.history, [history_item])
                self.assertEqual(history.state.redo_stack, [redo_item])
                self.assertFalse(tool._erasing)
                self.assertFalse(tool._changed)
                self.assertEqual(tool._commands, [])
                self.assertIsNone(tool._before_smiles_input)
                self.assertIsNone(tool._delete_session)

    def test_delete_tool_deactivate_rolls_back_structure_and_scene_item_gesture(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        atom_item = atom_items_for(canvas)[atom_id]
        shape_item = _make_rect_item("shape")
        canvas.services.scene_item_controller.attach_scene_item(shape_item)
        atom_item.setSelected(True)
        shape_item.setSelected(True)
        scene_before = list(canvas.scene().items())
        history_before = list(canvas.services.history_service.state.history)

        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with mock.patch.object(
            canvas.services.hit_testing_service,
            "item_at_event",
            side_effect=[atom_item, shape_item],
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
            self.assertTrue(tool.on_mouse_move(_DeleteGestureEvent()))

        self.assertNotIn(atom_id, canvas.model.atoms)
        self.assertIsNone(shape_item.scene())

        tool.deactivate()

        self.assertIn(atom_id, canvas.model.atoms)
        self.assertIs(atom_item.scene(), canvas.scene())
        self.assertIs(shape_item.scene(), canvas.scene())
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(shape_item.isSelected())
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertEqual(canvas.services.history_service.state.history, history_before)
        self.assertFalse(tool._erasing)
        self.assertFalse(tool._changed)
        self.assertEqual(tool._commands, [])
        self.assertIsNone(tool._delete_session)

    def test_delete_session_coalesces_large_selection_observers_to_one_commit(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_ids = [
            canvas.services.canvas_atom_mutation_service.add_atom(
                "N",
                float(index * 20),
                0.0,
            )
            for index in range(64)
        ]
        for atom_id in atom_ids:
            atom_items_for(canvas)[atom_id].setSelected(True)

        callbacks = callback_state_for(canvas)
        original_outline_callback = callbacks.scene_selection_outline
        outline_calls = 0

        def counted_outline_callback() -> None:
            nonlocal outline_calls
            outline_calls += 1
            assert original_outline_callback is not None
            original_outline_callback()

        callbacks.scene_selection_outline = counted_outline_callback
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        commands = [session.delete_atom(atom_id) for atom_id in atom_ids]

        self.assertEqual(outline_calls, 0)
        self.assertTrue(all(command is not None for command in commands))
        session.commit(CompositeCommand([command for command in commands if command]))

        self.assertEqual(outline_calls, 1)
        self.assertIs(
            callback_state_for(canvas).scene_selection_outline,
            counted_outline_callback,
        )

    def test_empty_delete_session_restores_observer_ports_without_rebuilding_scene(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom_dots_for(canvas)[atom_id].setSelected(True)
        scene_before = list(canvas.scene().items())
        callbacks = callback_state_for(canvas)
        original_outline_callback = callbacks.scene_selection_outline
        outline_calls = 0

        def counted_outline_callback() -> None:
            nonlocal outline_calls
            outline_calls += 1
            assert original_outline_callback is not None
            original_outline_callback()

        callbacks.scene_selection_outline = counted_outline_callback
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()

        session.commit()

        self.assertEqual(outline_calls, 0)
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertIs(callbacks.scene_selection_outline, counted_outline_callback)

    def test_delete_session_callback_getter_failure_precedes_guard_and_retries(
        self,
    ) -> None:
        canvas = self._new_canvas()
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        ports.group_getter_failures = 1
        canvas.runtime_state.callback_state = ports
        controller = canvas.services.scene_delete_controller
        scene = canvas.scene()

        with (
            mock.patch.object(
                CanvasDeleteTransactionSnapshot,
                "capture",
                wraps=CanvasDeleteTransactionSnapshot.capture,
            ) as capture,
            self.assertRaises(AttributeError) as raised,
        ):
            controller.begin_delete_tool_session()

        self.assertIs(raised.exception, ports.getter_error)
        capture.assert_not_called()
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
        self.assertTrue(tracker is None or tracker.depth == 0)

        session = controller.begin_delete_tool_session()

        # Successful suspension now verifies each captured setter through the
        # matching captured getter, in addition to the one savepoint read.
        self.assertEqual(ports.group_getter_reads, 3)
        self.assertEqual(ports.outline_getter_reads, 2)
        self.assertEqual(session.rollback(), [])
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)

    def test_delete_session_suspend_failure_restores_guard_callbacks_then_retries(
        self,
    ) -> None:
        canvas = self._new_canvas()
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        ports.setter_error = SystemExit("group callback suspension terminated")
        ports.group_setter_failures = 1
        canvas.runtime_state.callback_state = ports
        controller = canvas.services.scene_delete_controller
        scene = canvas.scene()
        scene_before = list(scene.items())

        with self.assertRaises(SystemExit) as raised:
            controller.begin_delete_tool_session()

        self.assertIs(raised.exception, ports.setter_error)
        self.assertEqual(list(scene.items()), scene_before)
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

        session = controller.begin_delete_tool_session()

        self.assertEqual(session.rollback(), [])
        self.assertFalse(session.active)
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        self.assertEqual(scene._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_session_observer_no_op_setters_fail_closed(self) -> None:
        canvas = self._new_canvas()
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline

        class NoOpCallbackPorts:
            def __init__(self) -> None:
                self._group = group_callback
                self._outline = outline_callback
                self.no_op_suspend = True
                self.no_op_restore = False

            @property
            def scene_selection_group(self):
                return self._group

            @scene_selection_group.setter
            def scene_selection_group(self, callback) -> None:
                if callback is None and self.no_op_suspend:
                    return
                if callback is not None and self.no_op_restore:
                    return
                self._group = callback

            @property
            def scene_selection_outline(self):
                return self._outline

            @scene_selection_outline.setter
            def scene_selection_outline(self, callback) -> None:
                self._outline = callback

        ports = NoOpCallbackPorts()
        canvas.runtime_state.callback_state = ports
        controller = canvas.services.scene_delete_controller

        with self.assertRaisesRegex(RuntimeError, "no-op"):
            controller.begin_delete_tool_session()

        self.assertIs(ports._group, group_callback)
        self.assertIs(ports._outline, outline_callback)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

        ports.no_op_suspend = False
        session = controller.begin_delete_tool_session()
        ports.no_op_restore = True
        with self.assertRaisesRegex(RuntimeError, "no-op"):
            session.commit()
        self.assertTrue(session.active)
        self.assertIsNone(ports._group)

        errors = session.rollback()
        self.assertTrue(any("no-op" in str(error) for error in errors))
        self.assertTrue(session.active)
        ports.no_op_restore = False
        self.assertEqual(session.rollback(), [])
        self.assertFalse(session.active)
        self.assertIs(ports._group, group_callback)
        self.assertIs(ports._outline, outline_callback)

    def test_delete_session_rollback_collects_suspend_failure_but_restores_absolute_state(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        canvas.runtime_state.callback_state = ports
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        self.assertIsNotNone(session.delete_atom(atom_id))
        ports.setter_error = KeyboardInterrupt(
            "group callback rollback suspension interrupted"
        )
        ports.group_setter_failures = 1
        original_restore = CanvasDeleteTransactionSnapshot.restore_with_result
        restore_calls = 0

        def counted_restore(snapshot) -> HistoryTransactionRestoreResult:
            nonlocal restore_calls
            restore_calls += 1
            return original_restore(snapshot)

        with mock.patch.object(
            CanvasDeleteTransactionSnapshot,
            "restore_with_result",
            new=counted_restore,
        ):
            errors = session.rollback()

        self.assertEqual(restore_calls, 1)
        self.assertTrue(any(error is ports.setter_error for error in errors))
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertFalse(session.active)
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_session_commit_propagates_fail_once_observer_restore_then_rolls_back(
        self,
    ) -> None:
        canvas = self._new_canvas()
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        canvas.runtime_state.callback_state = ports
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        primary_error = KeyboardInterrupt("group callback commit restore interrupted")
        ports.setter_error = primary_error
        ports.group_restore_setter_failures = 1

        with self.assertRaises(KeyboardInterrupt) as raised:
            session.commit()

        self.assertIs(raised.exception, primary_error)
        self.assertTrue(session.active)
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)

        self.assertEqual(session.rollback(), [])
        self.assertFalse(session.active)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_session_persistent_observer_restore_keeps_session_retryable(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        canvas.runtime_state.callback_state = ports
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        self.assertIsNotNone(session.delete_atom(atom_id))
        restore_error = SystemExit("group callback restore stayed unavailable")
        ports.setter_error = restore_error
        ports.group_restore_setter_failures = 2

        errors = session.rollback()

        self.assertTrue(any(error is restore_error for error in errors))
        self.assertTrue(session.active)
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertIsNone(ports._group_callback)
        self.assertIs(ports._outline_callback, outline_callback)

        self.assertEqual(session.rollback(), [])
        self.assertFalse(session.active)
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_tool_context_retries_active_session_after_observer_restore_failure(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        atom_item = atom_items_for(canvas)[atom_id]
        original_callbacks = callback_state_for(canvas)
        group_callback = original_callbacks.scene_selection_group
        outline_callback = original_callbacks.scene_selection_outline
        ports = _FailingCallbackPorts(group_callback, outline_callback)
        canvas.runtime_state.callback_state = ports
        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with mock.patch.object(
            canvas.services.hit_testing_service,
            "item_at_event",
            return_value=atom_item,
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))

        session = tool._delete_session
        self.assertIsNotNone(session)
        restore_error = SystemExit("observer restore failed for first rollback")
        ports.setter_error = restore_error
        ports.group_restore_setter_failures = 2

        with self.assertRaises(SystemExit) as raised:
            tool.deactivate()

        self.assertIs(raised.exception, restore_error)
        self.assertIsNotNone(session)
        self.assertFalse(session.active)
        self.assertIsNone(tool._delete_session)
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertIs(atom_item.scene(), canvas.scene())
        self.assertIs(ports._group_callback, group_callback)
        self.assertIs(ports._outline_callback, outline_callback)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_session_rollback_retries_nonauthoritative_snapshot_before_publish(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        selection_info = selection_info_state_for(canvas)
        selection_info.cache = ("C", "12.01")
        published: list[tuple[str, str]] = []
        selection_info.callback = lambda formula, mass: published.append(
            (formula, mass)
        )
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        self.assertIsNotNone(session.delete_atom(atom_id))
        transient_error = RuntimeError("absolute delete restore incomplete once")
        original_restore = CanvasDeleteTransactionSnapshot.restore_with_result
        restore_calls = 0

        def fail_once_then_restore(snapshot) -> HistoryTransactionRestoreResult:
            nonlocal restore_calls
            restore_calls += 1
            if restore_calls == 1:
                return HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(transient_error,),
                )
            self.assertTrue(session.active)
            self.assertEqual(published, [])
            return original_restore(snapshot)

        with mock.patch.object(
            CanvasDeleteTransactionSnapshot,
            "restore_with_result",
            new=fail_once_then_restore,
        ):
            errors = session.rollback()

        self.assertEqual(restore_calls, 2)
        self.assertIn(transient_error, errors)
        # Rollback republishes the exact cache captured before the gesture;
        # it does not recompute or replace that external publication payload.
        self.assertEqual(published, [("C", "12.01")])
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertFalse(session.active)
        self.assertEqual(canvas.scene()._chemvas_scene_rect_tracker.depth, 0)

    def test_delete_session_rollback_publishes_restored_selection_once_without_replacing_outlines(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom_item = atom_dots_for(canvas)[atom_id]
        atom_item.setSelected(True)
        scene_before = list(canvas.scene().items())
        history = canvas.services.history_service.state.history
        history_before = list(history)
        selection_info = selection_info_state_for(canvas)
        selection_info.signature = (frozenset({atom_id}), frozenset())
        selection_info.cache = ("C", "12.01")
        published_values: list[tuple[str, str]] = []
        ghost_items = []

        def corrupt_after_publication(formula: str, mass: str) -> None:
            published_values.append((formula, mass))
            canvas.model.atoms.clear()
            history.append(object())
            canvas.scene().removeItem(atom_item)
            ghost_items.append(canvas.scene().addRect(100.0, 100.0, 5.0, 5.0))

        selection_info.callback = corrupt_after_publication

        session = canvas.services.scene_delete_controller.begin_delete_tool_session()
        self.assertIsNotNone(session.delete_atom(atom_id))
        self.assertEqual(published_values, [])

        self.assertEqual(session.rollback(), [])

        self.assertEqual(published_values, [("C", "12.01")])
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertIs(atom_item.scene(), canvas.scene())
        self.assertTrue(atom_item.isSelected())
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertEqual(history, history_before)
        self.assertEqual(len(ghost_items), 1)
        self.assertIsNone(ghost_items[0].scene())

    def test_delete_session_label_html_rollback_is_exact_and_publishes_once(
        self,
    ) -> None:
        def publication_recorder(destination: list[tuple[str, str]]):
            def publish(formula: str, mass: str) -> None:
                destination.append((formula, mass))

            return publish

        for element in ("N", "O", "F", "Cl"):
            with self.subTest(element=element):
                canvas = self._new_canvas()
                atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
                    element,
                    0.0,
                    0.0,
                )
                atom_item = atom_items_for(canvas)[atom_id]
                atom_item.setSelected(True)
                html_before = atom_item.toHtml()
                scene_before = list(canvas.scene().items())
                selection_info = selection_info_state_for(canvas)
                cached_publication = (element, f"{element}-mass")
                selection_info.cache = cached_publication
                published_values: list[tuple[str, str]] = []
                selection_info.callback = publication_recorder(
                    published_values,
                )

                session = (
                    canvas.services.scene_delete_controller.begin_delete_tool_session()
                )
                self.assertIsNotNone(session.delete_atom(atom_id))

                self.assertEqual(session.rollback(), [])

                self.assertFalse(session.active)
                self.assertEqual(published_values, [cached_publication])
                self.assertEqual(atom_item.toHtml(), html_before)
                self.assertEqual(list(canvas.scene().items()), scene_before)
                self.assertIs(atom_item.scene(), canvas.scene())
                self.assertTrue(atom_item.isSelected())
                self.assertIn(atom_id, canvas.model.atoms)

    def test_delete_commit_observer_failure_rolls_back_and_republishes_prestate_once(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom_item = atom_dots_for(canvas)[atom_id]
        atom_item.setSelected(True)
        scene_before = list(canvas.scene().items())
        history_before = list(canvas.services.history_service.state.history)
        callbacks = callback_state_for(canvas)
        group_callback = callbacks.scene_selection_group
        outline_callback = callbacks.scene_selection_outline
        selection_info = selection_info_state_for(canvas)
        selection_info.signature = (frozenset({atom_id}), frozenset())
        selection_info.cache = ("C", "12.01")
        visible_cache = {"value": ("C", "12.01")}
        published_values: list[tuple[str, str]] = []
        observer_error = KeyboardInterrupt("selection observer failed after mutation")
        rollback_observer_error = SystemExit(
            "restored selection observer failed after mutation"
        )

        def mutate_then_maybe_fail(formula: str, mass: str) -> None:
            value = (formula, mass)
            visible_cache["value"] = value
            published_values.append(value)
            if value == ("", ""):
                raise observer_error
            raise rollback_observer_error

        selection_info.callback = mutate_then_maybe_fail
        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with mock.patch.object(
            canvas.services.hit_testing_service,
            "item_at_event",
            return_value=atom_item,
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))

        with self.assertRaises(KeyboardInterrupt) as raised:
            tool.on_mouse_release(_DeleteGestureEvent())

        self.assertIs(raised.exception, observer_error)
        self.assertEqual(published_values, [("", ""), ("C", "12.01")])
        self.assertEqual(visible_cache["value"], ("C", "12.01"))
        self.assertTrue(
            any(
                "restored selection observer failed after mutation" in note
                for note in getattr(observer_error, "__notes__", [])
            )
        )
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertIs(atom_item.scene(), canvas.scene())
        self.assertTrue(atom_item.isSelected())
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertEqual(
            canvas.services.history_service.state.history,
            history_before,
        )
        self.assertIs(callbacks.scene_selection_group, group_callback)
        self.assertIs(callbacks.scene_selection_outline, outline_callback)
        self.assertFalse(tool._erasing)
        self.assertFalse(tool._changed)
        self.assertEqual(tool._commands, [])
        self.assertIsNone(tool._delete_session)
        selection_info.callback = None

    def test_delete_commit_failure_retries_rollback_port_lookup_before_dropping_session(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        atom_item = atom_items_for(canvas)[atom_id]
        atom_item.setSelected(True)
        scene = canvas.scene()
        scene_items_before = list(scene.items())
        scene_rect_before = scene.sceneRect()
        callbacks = callback_state_for(canvas)
        group_callback = callbacks.scene_selection_group
        outline_callback = callbacks.scene_selection_outline
        history = canvas.services.history_service
        primary_error = KeyboardInterrupt("history push failed")
        rollback_lookup_error = SystemExit("rollback lookup failed once")
        original_rollback = SceneDeleteTransactionSession.rollback
        captured_sessions: list[SceneDeleteTransactionSession] = []

        class FailOnSecondRollbackLookup:
            def __init__(self) -> None:
                self.lookups = 0

            def __get__(self, instance, owner):
                if instance is None:
                    return self
                self.lookups += 1
                if self.lookups == 2:
                    raise rollback_lookup_error
                return original_rollback.__get__(instance, owner)

        rollback_descriptor = FailOnSecondRollbackLookup()
        controller = canvas.services.scene_delete_controller
        original_begin = controller.begin_delete_tool_session

        def capture_session() -> SceneDeleteTransactionSession:
            session = original_begin()
            captured_sessions.append(session)
            return session

        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with (
            mock.patch.object(
                controller,
                "begin_delete_tool_session",
                side_effect=capture_session,
            ),
            mock.patch.object(
                SceneDeleteTransactionSession,
                "rollback",
                rollback_descriptor,
            ),
            mock.patch.object(
                canvas.services.hit_testing_service,
                "item_at_event",
                return_value=atom_item,
            ),
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
            self.assertNotIn(atom_id, canvas.model.atoms)
            with mock.patch.object(history, "push", side_effect=primary_error):
                with self.assertRaises(KeyboardInterrupt) as raised:
                    tool.on_mouse_release(_DeleteGestureEvent())

        self.assertIs(raised.exception, primary_error)
        self.assertEqual(rollback_descriptor.lookups, 3)
        self.assertEqual(len(captured_sessions), 1)
        self.assertFalse(captured_sessions[0].active)
        tracker = scene._chemvas_scene_rect_tracker
        self.assertEqual(tracker.depth, 0)
        self.assertEqual(scene.sceneRect(), scene_rect_before)
        self.assertEqual(list(scene.items()), scene_items_before)
        self.assertIn(atom_id, canvas.model.atoms)
        self.assertIs(atom_item.scene(), scene)
        self.assertTrue(atom_item.isSelected())
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [])
        self.assertIs(callbacks.scene_selection_group, group_callback)
        self.assertIs(callbacks.scene_selection_outline, outline_callback)
        self.assertTrue(
            any(
                "rollback lookup failed once" in note
                for note in getattr(primary_error, "__notes__", [])
            )
        )
        self.assertFalse(tool._erasing)
        self.assertFalse(tool._changed)
        self.assertEqual(tool._commands, [])
        self.assertIsNone(tool._before_smiles_input)
        self.assertIsNone(tool._delete_session)

    def test_delete_tool_success_commits_one_restorable_history_step(self) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        atom_item = atom_items_for(canvas)[atom_id]
        shape_item = _make_rect_item("shape")
        canvas.services.scene_item_controller.attach_scene_item(shape_item)
        context = canvas.services.tools.context
        actual_history = canvas.services.history_service
        unrelated_history = mock.Mock()
        context.history_service = unrelated_history
        self.addCleanup(setattr, context, "history_service", actual_history)
        tool = DeleteTool(canvas, context=context)
        with mock.patch.object(
            canvas.services.hit_testing_service,
            "item_at_event",
            side_effect=[atom_item, shape_item],
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
            self.assertTrue(tool.on_mouse_move(_DeleteGestureEvent()))
        self.assertTrue(tool.on_mouse_release(_DeleteGestureEvent()))

        history = canvas.services.history_service
        self.assertEqual(len(history.state.history), 1)
        unrelated_history.push.assert_not_called()
        self.assertNotIn(atom_id, canvas.model.atoms)
        self.assertIsNone(shape_item.scene())
        self.assertIsNone(tool._delete_session)

        history.undo()
        self.assertIn(atom_id, canvas.model.atoms)
        restored_atom_item = atom_items_for(canvas)[atom_id]
        self.assertIs(restored_atom_item.scene(), canvas.scene())
        self.assertEqual(canvas.model.atoms[atom_id].element, "N")
        self.assertIs(shape_item.scene(), canvas.scene())

        history.redo()
        self.assertNotIn(atom_id, canvas.model.atoms)
        self.assertIsNone(shape_item.scene())

    def test_delete_tool_session_builds_bond_candidates_from_authoritative_model(
        self,
    ) -> None:
        canvas = self._new_canvas()
        atom_a = canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        atom_b = canvas.services.canvas_atom_mutation_service.add_atom("O", 20.0, 0.0)
        bond_id = canvas.services.canvas_bond_mutation_service.add_bond(atom_a, atom_b)
        add_bond_graphics_for(canvas, bond_id)
        graph = canvas.runtime_state.graph_state
        graph.atom_bond_ids[atom_a] = {999}

        session = canvas.services.scene_delete_controller.begin_delete_tool_session()

        self.assertEqual(session.atom_bond_ids[atom_a], {bond_id})
        self.assertIsNotNone(session.delete_atom(atom_a))
        self.assertIsNone(canvas.model.bonds[bond_id])

        self.assertEqual(session.rollback(), [])
        self.assertIsNotNone(canvas.model.bonds[bond_id])
        self.assertEqual(graph.atom_bond_ids[atom_a], {999})

    def test_delete_tool_live_ring_read_failure_prevents_mutation_then_retry_commits(
        self,
    ) -> None:
        canvas = self._new_canvas()
        ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        self.assertIsNotNone(ring)
        assert ring is not None
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            200.0,
            0.0,
        )
        atom_item = atom_items_for(canvas)[atom_id]
        atom_before = canvas.model.atoms[atom_id]
        bonds_before = list(canvas.model.bonds)
        scene_before = list(canvas.scene().items())
        history = canvas.services.history_service
        history.clear()
        callbacks = callback_state_for(canvas)
        group_callback = callbacks.scene_selection_group
        outline_callback = callbacks.scene_selection_outline
        read_error = RuntimeError("live ring dependency read failed")
        original_data = ring.data
        failed = False

        def fail_once(role: int):
            nonlocal failed
            if role == 2 and not failed:
                failed = True
                raise read_error
            return original_data(role)

        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with (
            mock.patch.object(ring, "data", side_effect=fail_once),
            mock.patch.object(
                canvas.services.hit_testing_service,
                "item_at_event",
                return_value=atom_item,
            ),
        ):
            with self.assertRaises(RuntimeError) as raised:
                tool.on_mouse_press(_DeleteGestureEvent())

            self.assertIs(raised.exception, read_error)
            self.assertIs(canvas.model.atoms[atom_id], atom_before)
            self.assertEqual(len(canvas.model.bonds), len(bonds_before))
            for restored, before in zip(
                canvas.model.bonds,
                bonds_before,
                strict=True,
            ):
                self.assertIs(restored, before)
            self.assertEqual(list(canvas.scene().items()), scene_before)
            self.assertEqual(ring_items_for(canvas), [ring])
            self.assertEqual(history.state.history, [])
            self.assertIs(callbacks.scene_selection_group, group_callback)
            self.assertIs(callbacks.scene_selection_outline, outline_callback)
            self.assertFalse(tool._erasing)
            self.assertFalse(tool._changed)
            self.assertEqual(tool._commands, [])
            self.assertIsNone(tool._delete_session)

            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
            self.assertTrue(tool.on_mouse_release(_DeleteGestureEvent()))

            self.assertNotIn(atom_id, canvas.model.atoms)
            self.assertEqual(ring_items_for(canvas), [ring])
            self.assertIs(ring.scene(), canvas.scene())
            self.assertEqual(len(history.state.history), 1)

            history.undo()
            self.assertIn(atom_id, canvas.model.atoms)
            self.assertEqual(ring_items_for(canvas), [ring])
            self.assertIs(ring.scene(), canvas.scene())

            history.redo()
            self.assertNotIn(atom_id, canvas.model.atoms)
            self.assertEqual(ring_items_for(canvas), [ring])
            self.assertIs(ring.scene(), canvas.scene())

    def test_direct_bond_live_ring_read_failure_rolls_back_then_retry_replays_cleanup(
        self,
    ) -> None:
        canvas = self._new_canvas()
        ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        self.assertIsNotNone(ring)
        assert ring is not None
        history = canvas.services.history_service
        history.clear()
        bond_id = 0
        bond_before = canvas.model.bonds[bond_id]
        scene_before = list(canvas.scene().items())
        read_error = RuntimeError("live ring cleanup read failed")
        original_data = ring.data
        role_two_reads = 0

        def fail_second_dependency_read(role: int):
            nonlocal role_two_reads
            if role == 2:
                role_two_reads += 1
                if role_two_reads == 2:
                    raise read_error
            return original_data(role)

        with mock.patch.object(
            ring,
            "data",
            side_effect=fail_second_dependency_read,
        ):
            with self.assertRaises(RuntimeError) as raised:
                canvas.services.scene_delete_controller.delete_bond(
                    bond_id,
                    record=True,
                )

            self.assertIs(raised.exception, read_error)
            self.assertIs(canvas.model.bonds[bond_id], bond_before)
            self.assertEqual(list(canvas.scene().items()), scene_before)
            self.assertEqual(ring_items_for(canvas), [ring])
            self.assertEqual(history.state.history, [])

            command = canvas.services.scene_delete_controller.delete_bond(
                bond_id,
                record=True,
            )
            self.assertIsNotNone(command)
            self.assertIsNone(canvas.model.bonds[bond_id])
            self.assertNotIn(ring, ring_items_for(canvas))
            self.assertIsNone(ring.scene())
            self.assertEqual(len(history.state.history), 1)

            history.undo()
            self.assertEqual(canvas.model.bonds[bond_id], bond_before)
            self.assertIn(ring, ring_items_for(canvas))
            self.assertIs(ring.scene(), canvas.scene())

            history.redo()
            self.assertIsNone(canvas.model.bonds[bond_id])
            self.assertNotIn(ring, ring_items_for(canvas))
            self.assertIsNone(ring.scene())

    def test_delete_tool_session_reuses_precomputed_ring_model_sets(self) -> None:
        canvas = self._new_canvas()
        add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        ring = ring_items_for(canvas)[0]
        isolated_atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            200.0,
            0.0,
        )
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()

        with (
            mock.patch(
                "chemvas.ui.scene_delete_controller.model_bond_pairs",
                side_effect=AssertionError("gesture delete rescanned the full model"),
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.ring_items_for",
                side_effect=AssertionError("gesture delete rescanned every ring"),
            ),
        ):
            self.assertIsNotNone(session.delete_atom(isolated_atom_id))

        self.assertEqual(ring_items_for(canvas), [ring])
        session.commit()

    def test_delete_tool_scene_item_commit_removes_and_replays_overlapping_group(
        self,
    ) -> None:
        canvas = self._new_canvas()
        shape_item = _make_rect_item("shape")
        canvas.services.scene_item_controller.attach_scene_item(shape_item)
        group_id = register_group_for(canvas, set(), [shape_item])
        group = group_state_for(canvas).groups[group_id]

        tool = DeleteTool(canvas, context=canvas.services.tools.context)
        with (
            mock.patch.object(
                canvas.services.hit_testing_service,
                "item_at_event",
                return_value=shape_item,
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.group_ids_for_members_for",
                side_effect=AssertionError("gesture delete rescanned every group"),
            ),
        ):
            self.assertTrue(tool.on_mouse_press(_DeleteGestureEvent()))
            self.assertTrue(tool.on_mouse_release(_DeleteGestureEvent()))

        history = canvas.services.history_service
        self.assertIsNone(shape_item.scene())
        self.assertNotIn(group_id, group_state_for(canvas).groups)

        history.undo()
        self.assertIs(shape_item.scene(), canvas.scene())
        self.assertIs(group_state_for(canvas).groups[group_id], group)
        self.assertEqual(group.items, [shape_item])

        history.redo()
        self.assertIsNone(shape_item.scene())
        self.assertNotIn(group_id, group_state_for(canvas).groups)

    def test_delete_tool_session_indexes_only_ring_dependencies_affected_by_atom(
        self,
    ) -> None:
        canvas = self._new_canvas()
        first_ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        second_ring = add_benzene_ring_for(canvas, QPointF(300.0, 0.0))
        self.assertIsNotNone(first_ring)
        self.assertIsNotNone(second_ring)
        assert first_ring is not None
        assert second_ring is not None
        original_rings = list(ring_items_for(canvas))
        first_atom_ids = first_ring.data(2)
        self.assertIsInstance(first_atom_ids, list)
        atom_id = first_atom_ids[0]
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()

        with (
            mock.patch(
                "chemvas.ui.scene_delete_controller.model_bond_pairs",
                side_effect=AssertionError("gesture delete rescanned the full model"),
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.ring_items_for",
                side_effect=AssertionError("gesture delete rescanned every ring"),
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.group_ids_for_members_for",
                side_effect=AssertionError("gesture delete rescanned every group"),
            ),
        ):
            self.assertIsNotNone(session.delete_atom(atom_id))

        self.assertNotIn(first_ring, ring_items_for(canvas))
        self.assertIn(second_ring, ring_items_for(canvas))
        self.assertEqual(session.rollback(), [])
        self.assertEqual(ring_items_for(canvas), original_rings)

    def test_delete_tool_session_cleans_preexisting_invalid_ring_without_rescanning(
        self,
    ) -> None:
        canvas = self._new_canvas()
        ring = add_benzene_ring_for(canvas, QPointF(0.0, 0.0))
        self.assertIsNotNone(ring)
        assert ring is not None
        ring.setData(2, [999, 1000, 1001])
        isolated_atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            200.0,
            0.0,
        )
        session = canvas.services.scene_delete_controller.begin_delete_tool_session()

        with (
            mock.patch(
                "chemvas.ui.scene_delete_controller.model_bond_pairs",
                side_effect=AssertionError("gesture delete rescanned the full model"),
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.ring_items_for",
                side_effect=AssertionError("gesture delete rescanned every ring"),
            ),
            mock.patch(
                "chemvas.ui.scene_delete_controller.group_ids_for_members_for",
                side_effect=AssertionError("gesture delete rescanned every group"),
            ),
        ):
            self.assertIsNotNone(session.delete_atom(isolated_atom_id))

        self.assertNotIn(ring, ring_items_for(canvas))
        self.assertEqual(session.rollback(), [])
        self.assertIn(ring, ring_items_for(canvas))

    def test_broken_delete_diagnostic_hook_preserves_control_flow_primary_identity(
        self,
    ) -> None:
        class BrokenKeyboardInterrupt(KeyboardInterrupt):
            def add_note(self, _note: str) -> None:
                raise SystemExit("broken KeyboardInterrupt diagnostic hook")

        class BrokenSystemExit(SystemExit):
            def add_note(self, _note: str) -> None:
                raise KeyboardInterrupt("broken SystemExit diagnostic hook")

        helpers_and_errors = (
            (
                DeleteTool._add_rollback_error_notes,
                [RuntimeError("delete tool rollback failed")],
            ),
            (
                SceneDeleteTransactionSession._add_observer_error_notes,
                [("observer sync", RuntimeError("observer failed"))],
            ),
            (
                SceneDeleteController._add_cleanup_error_notes,
                [("selection cleanup", RuntimeError("cleanup failed"))],
            ),
        )
        for primary in (
            BrokenKeyboardInterrupt("primary keyboard interruption"),
            BrokenSystemExit("primary system exit"),
        ):
            for helper, secondary_errors in helpers_and_errors:
                with self.subTest(
                    primary_type=type(primary).__name__,
                    helper=helper.__name__,
                ):
                    with self.assertRaises(type(primary)) as raised:
                        try:
                            raise primary
                        except BaseException as original_error:
                            helper(original_error, secondary_errors)
                            raise
                    self.assertIs(raised.exception, primary)


if __name__ == "__main__":
    unittest.main()
