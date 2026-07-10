import gc
import os
import unittest
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QBrush, QColor, QPen, QTransform
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import CompositeCommand, SetSmilesInputCommand
    from core.model import Atom, Bond, MoleculeModel
    from ui.atom_coords_access import atom_coords_3d_for
    from ui.bond_graphics_access import add_bond_graphics_for
    from ui.canvas_atom_graphics_state import atom_items_for
    from ui.canvas_bond_graphics_state import bond_items_for_id
    from ui.canvas_delete_transaction import (
        CanvasDeleteTransactionSnapshot,
        canvas_delete_transaction,
    )
    from ui.canvas_group_state import (
        group_state_for,
        register_group_for,
        remove_group_for,
    )
    from ui.canvas_mark_registry import mark_registry_for
    from ui.canvas_scene_items_state import note_items_for, ring_items_for
    from ui.canvas_smiles_input_state import (
        last_smiles_input_for,
        set_last_smiles_input_for,
    )
    from ui.canvas_view import CanvasView
    from ui.history_commands import UngroupSceneItemsCommand
    from ui.scene_item_state import (
        atom_state_dict_for,
        bond_state_dict,
        mark_state_dict_for,
    )
    from ui.structure_mutation_access import add_benzene_ring_for

    from tests.test_scene_ops_controller import (
        _FakeCanvas,
        _make_model_ring_item,
        _make_note_item,
        _make_rect_item,
        _make_ring_item,
        scene_delete_controller_for,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for delete atomicity tests")
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

    def test_direct_atom_failure_before_or_after_mutation_restores_marks_and_graphics_once(self) -> None:
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
                    canvas.services.scene_delete_controller.delete_atom(atom_id, record=True)

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

    def test_direct_bond_failure_before_after_or_during_redraw_restores_graphics(self) -> None:
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
                canvas.services.move_controller.redraw_connected_bonds = fail_redraw_once

                with self.assertRaisesRegex(RuntimeError, "bond-(before|after|redraw)"):
                    canvas.services.scene_delete_controller.delete_bond(bond_id, record=True)

                restored_bond = canvas.model.bonds[bond_id]
                self.assertIsNotNone(restored_bond)
                assert restored_bond is not None
                self.assertEqual(bond_state_dict(restored_bond), bond_before)
                restored_graphics = bond_items_for_id(canvas, bond_id)
                self.assertIs(canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping)
                self.assertEqual(restored_graphics, graphics_before)
                self.assertTrue(all(item.scene() is canvas.scene() for item in restored_graphics))
                self.assertEqual(list(canvas.scene().items()), scene_order_before)
                self.assertEqual(last_smiles_input_for(canvas), "N=O")
                self.assertEqual(canvas.services.history_service.state.history, [])
                self.assertEqual(remove_calls, 1)
                self.assertLessEqual(redraw_calls, 1)

    def test_persistent_ring_refresh_failure_restores_every_original_bond_primitive_exactly(self) -> None:
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
            bond_id: list(items)
            for bond_id, items in graphics_mapping.items()
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
        self.assertIs(canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping)
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

    def test_ring_history_undo_and_redo_persistent_refresh_failure_restore_raw_graphics(self) -> None:
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
                    bond_id: list(items)
                    for bond_id, items in graphics_mapping.items()
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
                    raise RuntimeError(f"persistent history {_history_operation} refresh")

                canvas.bond_renderer.update_bond_geometry = mutate_then_fail_persistently

                with self.assertRaisesRegex(
                    RuntimeError,
                    f"persistent history {history_operation} refresh",
                ):
                    getattr(history, history_operation)()

                self.assertTrue(refresh_calls)
                self.assertEqual(ring.scene() is canvas.scene(), ring_was_attached)
                self.assertEqual(ring_items_for(canvas), ring_registry_before)
                self.assertIs(canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping)
                for bond_id, original_list in lists_before.items():
                    self.assertIs(graphics_mapping[bond_id], original_list)
                    self.assertEqual(graphics_mapping[bond_id], items_before[bond_id])
                    for item in graphics_mapping[bond_id]:
                        self.assertEqual(raw_state(item), states_before[id(item)])
                        self.assertIs(item.scene(), canvas.scene())
                self.assertEqual(history.state.history, [])
                self.assertEqual(history.state.redo_stack, [])

    def test_direct_ring_failure_after_mutation_restores_single_registration(self) -> None:
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

    def test_direct_bond_initial_failure_does_not_double_compensate_ring_cleanup(self) -> None:
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

    def test_multi_bond_redraw_failure_restores_all_completed_and_current_bonds(self) -> None:
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
        bonds_before = [bond_state_dict(bond) for bond in canvas.model.bonds if bond is not None]
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

    def test_multi_atom_second_failure_restores_attempted_atoms_without_touching_future_atom(self) -> None:
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

        canvas.services.canvas_atom_mutation_service.remove_atom_only = fail_on_second_atom

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

    def test_multi_scene_second_failure_restores_attempted_items_and_skips_future_item(self) -> None:
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

    def test_selection_delete_preserves_body_error_and_runs_both_cleanup_phases(self) -> None:
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

    def test_selection_delete_success_cleanup_failure_rolls_back_and_raises_first_cleanup_error(self) -> None:
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
        self.assertIs(canvas.runtime_state.bond_graphics_state.bond_items, graphics_mapping)
        self.assertIs(graphics_mapping[bond_id], graphics_list)
        self.assertEqual(graphics_mapping[bond_id], graphics_before)
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(list(canvas.scene().items()), scene_before)
        self.assertFalse(canvas.runtime_state.selection_style_state.suspend_outline)
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [])
        self.assertEqual(history_observations, [True, False])

    def test_selected_group_delete_undo_redo_preserves_group_identity_and_releases_evicted_items(self) -> None:
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

    def test_direct_atom_delete_removes_overlapping_group_and_undo_restores_exact_group(self) -> None:
        canvas = self._new_canvas()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom("N", 10.0, 20.0)
        group_state = group_state_for(canvas)
        groups_object = group_state.groups
        group_id = register_group_for(canvas, {atom_id}, [])
        group_object = group_state.groups[group_id]
        atom_ids_object = group_object.atom_ids
        items_object = group_object.items

        command = canvas.services.scene_delete_controller.delete_atom(atom_id, record=True)

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

    def test_direct_ring_and_broken_ring_cleanup_remove_overlapping_groups_in_history_order(self) -> None:
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

    def test_group_remove_and_cleanup_refresh_failures_restore_nested_group_state_exactly(self) -> None:
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
                        "ui.scene_delete_controller.remove_group_for",
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

    def test_interleaved_scene_item_failure_restores_registry_and_stacking_exactly(self) -> None:
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

    def test_interleaved_broken_ring_failure_restores_registry_and_stacking_exactly(self) -> None:
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
            any("rollback-error" in note for note in getattr(caught.exception, "__notes__", []))
        )


if __name__ == "__main__":
    unittest.main()
