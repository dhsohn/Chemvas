import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import Atom, Bond
from chemvas.ui.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    set_atom_dots_for,
    set_atom_items_for,
)
from chemvas.ui.canvas_bond_graphics_state import (
    CanvasBondGraphicsState,
    set_bond_items_for,
)
from chemvas.ui.canvas_graph_service import CanvasGraphService
from chemvas.ui.canvas_graph_state import CanvasGraphState
from chemvas.ui.canvas_ring_fill_scene_access import update_ring_fills_for_atoms_for
from chemvas.ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
from chemvas.ui.canvas_scene_items_state import (
    CanvasSceneItemsState,
    set_scene_item_collection_for,
)
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


class CanvasViewTransformHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

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
            runtime_state=canvas_runtime_state(
                graph_state=CanvasGraphState(
                    atom_bond_ids={
                        1: {0, 1},
                        2: {0, 1},
                        3: {2},
                    }
                )
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
            runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
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
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState(),
                bond_graphics_state=CanvasBondGraphicsState(),
            ),
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
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState(),
                bond_graphics_state=CanvasBondGraphicsState(),
            ),
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
            ),
            runtime_state=canvas_runtime_state(graph_state=CanvasGraphState()),
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
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState()
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
