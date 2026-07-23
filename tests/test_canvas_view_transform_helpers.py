import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.canvas_atom_graphics_state import (
        set_atom_dots_for,
        set_atom_items_for,
    )
    from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_graph_state import CanvasGraphState
    from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
    from chemvas.ui.canvas_ring_fill_scene_access import update_ring_fills_for_atoms_for
    from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
    from chemvas.ui.canvas_scene_items_state import set_scene_item_collection_for
    from chemvas.ui.input_view_access import rotate_view_for
    from chemvas.ui.input_view_state import InputViewState
    from chemvas.ui.selection_rotation_access import rotate_selection_for
    from chemvas.ui.selection_style_access import restore_selection_from_ids_for


class _FakeSelectableItem:
    def __init__(self, kind, data1=None, data2=None) -> None:
        self._kind = kind
        self._data1 = data1
        self._data2 = data2
        self._selected = False

    def data(self, key):
        if key == 0:
            return self._kind
        if key == 1:
            return self._data1
        if key == 2:
            return self._data2
        return None

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected


class _FakeScene:
    def __init__(self, selected_items=None) -> None:
        self.clearSelection = mock.Mock()
        self._selected_items = list(selected_items or [])

    def selectedItems(self):
        return list(self._selected_items)


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids
        self.setPolygon = mock.Mock()

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None


class _FakePositionedItem:
    def __init__(self, data1=None) -> None:
        self._data1 = data1
        self.positions: list[QPointF] = []

    def data(self, key):
        if key == 1:
            return self._data1
        return None

    def setData(self, key, value) -> None:
        if key == 1:
            self._data1 = value

    def setPos(self, x, y=None) -> None:
        if isinstance(x, QPointF):
            self.positions.append(QPointF(x))
            return
        self.positions.append(QPointF(float(x), float(y)))


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewTransformHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_rotate_view_updates_base_transform_and_skips_zero_angle(self) -> None:
        view = SimpleNamespace(
            runtime_state=SimpleNamespace(input_view_state=InputViewState()),
            setTransform=mock.Mock(),
        )

        rotate_view_for(view, 45.0)

        self.assertFalse(
            view.runtime_state.input_view_state.base_transform.isIdentity()
        )
        view.setTransform.assert_called_once()

        idle_view = SimpleNamespace(
            runtime_state=SimpleNamespace(input_view_state=InputViewState()),
            setTransform=mock.Mock(),
        )
        rotate_view_for(idle_view, 0.0)
        self.assertTrue(
            idle_view.runtime_state.input_view_state.base_transform.isIdentity()
        )
        idle_view.setTransform.assert_not_called()

    def test_rotate_selection_rotates_atoms_and_updates_dependent_items(self) -> None:
        label_1 = object()
        label_2 = object()
        atom_1 = Atom("C", 1.0, 0.0)
        atom_2 = Atom("O", 0.0, 1.0)
        dot_1 = _FakePositionedItem()
        mark_with_offset = _FakePositionedItem({"dx": 2.0, "dy": -3.0})
        mark_without_offset = _FakePositionedItem({})
        mark_centers: list[QPointF] = []
        atom_label_service = SimpleNamespace(position_label=mock.Mock())
        move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        ring_fill_service = SimpleNamespace(rotate_ring_fills=mock.Mock())
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: atom_1, 2: atom_2},
                bonds=[Bond(1, 2, 1), None],
            ),
            scene=lambda: _FakeScene(
                [
                    _FakeSelectableItem("bond", 0),
                    _FakeSelectableItem("bond", 1),
                    _FakeSelectableItem("bond", 99),
                ]
            ),
            services=canvas_runtime_services(
                atom_label_service=atom_label_service,
                canvas_ring_fill_scene_service=ring_fill_service,
                move_controller=move_controller,
                selection_controller=selection_controller,
                scene_decoration_build_service=SimpleNamespace(
                    set_mark_center=lambda _mark, center: mark_centers.append(
                        QPointF(center)
                    )
                ),
            ),
            mark_registry=CanvasMarkRegistry(
                {1: [mark_with_offset, mark_without_offset]}
            ),
        )
        set_atom_items_for(view, {1: label_1, 2: label_2})
        set_atom_dots_for(view, {1: dot_1})

        rotate_selection_for(view, 90.0)

        self.assertAlmostEqual(atom_1.x, 1.0)
        self.assertAlmostEqual(atom_1.y, 1.0)
        self.assertAlmostEqual(atom_2.x, 0.0)
        self.assertAlmostEqual(atom_2.y, 0.0)
        rotate_call = ring_fill_service.rotate_ring_fills.call_args
        self.assertEqual(rotate_call.args[0], {1, 2})
        self.assertEqual(rotate_call.args[1], QPointF(0.5, 0.5))
        self.assertAlmostEqual(rotate_call.args[2], math.pi / 2.0)
        self.assertEqual(
            {call.args[0] for call in atom_label_service.position_label.call_args_list},
            {label_1, label_2},
        )
        self.assertEqual(
            {
                call.args[0]: (round(call.args[1], 6), round(call.args[2], 6))
                for call in atom_label_service.position_label.call_args_list
            },
            {label_1: (1.0, 1.0), label_2: (0.0, 0.0)},
        )
        self.assertEqual(dot_1.positions, [QPointF(1.0, 1.0)])
        # The bound mark's offset rotates with the selection (matching the
        # Alt+arrows path and the rigid rotation preview): (2, -3) rotated 90
        # degrees becomes (3, 2), applied at the rotated atom (1, 1).
        self.assertEqual(mark_centers, [QPointF(4.0, 3.0), QPointF(1.0, 1.0)])
        self.assertEqual(
            {
                call.args[0]
                for call in move_controller.redraw_connected_bonds.call_args_list
            },
            {1, 2},
        )
        selection_controller.update_selection_outline.assert_called_once_with()

    def test_rotate_selection_skips_when_nothing_can_be_rotated(self) -> None:
        empty_atom_label_service = SimpleNamespace(position_label=mock.Mock())
        empty_move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        empty_ring_fill_service = SimpleNamespace(rotate_ring_fills=mock.Mock())
        empty_selection_controller = SimpleNamespace(
            update_selection_outline=mock.Mock()
        )
        empty_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}, bonds=[]),
            scene=lambda: _FakeScene(),
            services=canvas_runtime_services(
                atom_label_service=empty_atom_label_service,
                canvas_ring_fill_scene_service=empty_ring_fill_service,
                move_controller=empty_move_controller,
                selection_controller=empty_selection_controller,
            ),
        )

        rotate_selection_for(empty_view, 15.0)

        empty_atom_label_service.position_label.assert_not_called()
        empty_move_controller.redraw_connected_bonds.assert_not_called()
        empty_ring_fill_service.rotate_ring_fills.assert_not_called()
        empty_selection_controller.update_selection_outline.assert_not_called()

        no_center_atom_label_service = SimpleNamespace(position_label=mock.Mock())
        no_center_move_controller = SimpleNamespace(redraw_connected_bonds=mock.Mock())
        no_center_ring_fill_service = SimpleNamespace(rotate_ring_fills=mock.Mock())
        no_center_selection_controller = SimpleNamespace(
            update_selection_outline=mock.Mock()
        )
        no_center_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 2.0, 3.0)}, bonds=[]),
            scene=lambda: _FakeScene([_FakeSelectableItem("atom", 99)]),
            services=canvas_runtime_services(
                atom_label_service=no_center_atom_label_service,
                canvas_ring_fill_scene_service=no_center_ring_fill_service,
                move_controller=no_center_move_controller,
                selection_controller=no_center_selection_controller,
            ),
        )
        set_atom_items_for(no_center_view, {1: object()})
        set_atom_dots_for(no_center_view, {})

        rotate_selection_for(no_center_view, 15.0)

        no_center_atom_label_service.position_label.assert_not_called()
        no_center_move_controller.redraw_connected_bonds.assert_not_called()
        no_center_ring_fill_service.rotate_ring_fills.assert_not_called()
        no_center_selection_controller.update_selection_outline.assert_not_called()

    def test_bond_sets_for_atoms_classifies_internal_boundary_and_falls_back_to_model_scan(
        self,
    ) -> None:
        classified_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(1, 2, 2),
                    Bond(3, 4, 1),
                    None,
                ]
            ),
            graph_state=CanvasGraphState(
                atom_bond_ids={
                    1: {0, 1},
                    2: {0, 1},
                    3: {2},
                }
            ),
        )
        classified_graph_service = CanvasGraphService(classified_view)
        classified_view.services = canvas_runtime_services(
            graph_service=classified_graph_service
        )

        internal, boundary = classified_graph_service.bond_sets_for_atoms({1, 2, 3})
        self.assertEqual(internal, {0, 1})
        self.assertEqual(boundary, {2})

        fallback_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(5, 6, 1),
                    Bond(6, 7, 2),
                    None,
                ]
            ),
            graph_state=CanvasGraphState(),
        )
        fallback_graph_service = CanvasGraphService(fallback_view)
        fallback_view.services = canvas_runtime_services(
            graph_service=fallback_graph_service
        )

        internal, boundary = fallback_graph_service.bond_sets_for_atoms({5, 6})
        self.assertEqual(internal, {0})
        self.assertEqual(boundary, {1})
        self.assertEqual(
            fallback_graph_service.bond_sets_for_atoms(set()), (set(), set())
        )

    def test_restore_selection_from_ids_selects_atoms_bonds_and_refreshes_outline(
        self,
    ) -> None:
        atom_item = _FakeSelectableItem("atom", 1)
        atom_dot = _FakeSelectableItem("atom", 2)
        bond_item_a = _FakeSelectableItem("bond", 7)
        bond_item_b = _FakeSelectableItem("bond", 7)
        scene = _FakeScene()
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        view = SimpleNamespace(
            scene=lambda: scene,
            services=canvas_runtime_services(selection_controller=selection_controller),
        )
        set_atom_items_for(view, {1: atom_item})
        set_atom_dots_for(view, {2: atom_dot})
        set_bond_items_for(view, {7: [bond_item_a, bond_item_b]})

        restore_selection_from_ids_for(view, {1, 2}, {7})

        scene.clearSelection.assert_called_once_with()
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_dot.isSelected())
        self.assertTrue(bond_item_a.isSelected())
        self.assertTrue(bond_item_b.isSelected())
        selection_controller.update_selection_outline.assert_called_once_with()

    def test_restore_selection_from_ids_returns_when_scene_is_missing(self) -> None:
        atom_item = _FakeSelectableItem("atom", 1)
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        view = SimpleNamespace(
            services=canvas_runtime_services(selection_controller=selection_controller),
        )
        set_atom_items_for(view, {1: atom_item})
        set_atom_dots_for(view, {})
        set_bond_items_for(view, {})

        restore_selection_from_ids_for(view, {1}, set())

        self.assertFalse(atom_item.isSelected())
        selection_controller.update_selection_outline.assert_not_called()

    def test_expand_connected_atoms_returns_transitive_component(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    Bond(2, 3, 1),
                    Bond(4, 5, 1),
                    None,
                ]
            )
        )
        graph_service = CanvasGraphService(view)
        view.services = canvas_runtime_services(graph_service=graph_service)

        self.assertEqual(graph_service.expand_connected_atoms({1}), {1, 2, 3})
        self.assertEqual(graph_service.expand_connected_atoms({4}), {4, 5})
        self.assertEqual(graph_service.expand_connected_atoms(set()), set())

    def test_update_ring_fills_for_atoms_updates_matching_ring_polygons(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        invalid_ring = _FakeRingItem("bad")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 1.5),
                    4: Atom("O", 9.0, 9.0),
                    5: Atom("O", 10.0, 9.0),
                    6: Atom("O", 9.5, 10.0),
                }
            ),
        )
        set_scene_item_collection_for(
            view, "ring_items", [matching_ring, non_matching_ring, invalid_ring]
        )
        view.services = canvas_runtime_services(
            canvas_ring_fill_scene_service=CanvasRingFillSceneService(view)
        )

        update_ring_fills_for_atoms_for(view, {1, 2, 3})

        matching_ring.setPolygon.assert_called_once()
        polygon = matching_ring.setPolygon.call_args.args[0]
        self.assertEqual(
            [(round(point.x(), 6), round(point.y(), 6)) for point in polygon],
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        non_matching_ring.setPolygon.assert_not_called()
        invalid_ring.setPolygon.assert_not_called()
        update_ring_fills_for_atoms_for(view, set())
        self.assertEqual(matching_ring.setPolygon.call_count, 1)
