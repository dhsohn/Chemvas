import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
    from chemvas.ui.canvas_atom_graphics_state import (
        set_atom_dots_for,
        set_atom_items_for,
    )
    from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for
    from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
    from chemvas.ui.canvas_move_controller import CanvasMoveController
    from chemvas.ui.canvas_scene_items_state import set_scene_item_collection_for
    from chemvas.ui.move_access import move_atoms_for, move_item_for


class _FakeItem:
    def __init__(self, kind, *, data1=None, data2=None) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self.moves = []
        self.paths = []
        self.set_data_calls = []

    def data(self, key):
        return self._data.get(key)

    def setData(self, key, value) -> None:
        self._data[key] = value
        self.set_data_calls.append((key, value))

    def moveBy(self, dx: float, dy: float) -> None:
        self.moves.append((dx, dy))

    def setPath(self, path) -> None:
        self.paths.append(path)


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids
        self.polygons = []

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None

    def setPolygon(self, polygon) -> None:
        self.polygons.append(
            [(round(point.x(), 6), round(point.y(), 6)) for point in polygon]
        )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewMoveHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _bind_move_controller(self, view, controller=None):
        services = getattr(view, "services", None)
        if services is None:
            services = canvas_runtime_services()
            view.services = services
        if not hasattr(services, "hit_testing_service"):
            services.hit_testing_service = SimpleNamespace(
                mark_spatial_index_dirty=mock.Mock()
            )
        controller = controller or CanvasMoveController(
            view,
            hit_testing_service=services.hit_testing_service,
        )
        services.move_controller = controller
        if hasattr(view, "refresh_selection_outline") and not hasattr(
            services, "selection_controller"
        ):
            services.selection_controller = SimpleNamespace(
                update_selection_outline=view.refresh_selection_outline
            )
        return controller

    def test_move_item_atom_branch_and_guard_paths(self) -> None:
        missing_item = _FakeItem("atom", data1="bad")
        missing_atom_item = _FakeItem("atom", data1=9)
        atom_item = _FakeItem("atom", data1=1)
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 1.0, 2.0)},
                bonds=[Bond(1, 2, 1), Bond(3, 4, 1), None],
            ),
            bond_renderer=SimpleNamespace(redraw_bond=mock.Mock()),
            refresh_selection_outline=mock.Mock(),
        )
        self._bind_move_controller(view)
        # The atom branch delegates to move_atom, which repositions the atom's
        # registered label/dot by id (rather than moving the grabbed item
        # directly) and marks the hit-test spatial index dirty.
        set_atom_items_for(view, {1: atom_item})

        move_item_for(view, missing_item, 2.0, 3.0)
        move_item_for(view, missing_atom_item, 2.0, 3.0)
        move_item_for(view, atom_item, 2.0, 3.0, update_selection=False)

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (3.0, 5.0))
        self.assertEqual(atom_item.moves, [(2.0, 3.0)])
        view.bond_renderer.redraw_bond.assert_called_once_with(0)
        view.refresh_selection_outline.assert_not_called()
        view.services.selection.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()

    def test_move_item_updates_bond_mark_and_scene_item_payloads(self) -> None:
        bond_item = _FakeItem("bond", data1=0)
        mark_item = _FakeItem("mark", data1={"atom_id": 1})
        orbital_item = _FakeItem("orbital", data1={"center": QPointF(2.0, 3.0)})
        bracket_item = _FakeItem(
            "ts_bracket", data1={"rect": QRectF(1.0, 2.0, 3.0, 4.0)}
        )
        arrow_item = _FakeItem(
            "arrow",
            data2={
                "start": QPointF(0.0, 0.0),
                "end": QPointF(1.0, 1.0),
                "control": QPointF(2.0, 2.0),
            },
        )
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 10.0, 10.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            bond_renderer=SimpleNamespace(redraw_connected_bonds=mock.Mock()),
            services=canvas_runtime_services(
                scene_decoration_build_service=SimpleNamespace(
                    mark_center=mock.Mock(return_value=QPointF(15.0, 18.0))
                )
            ),
            refresh_selection_outline=mock.Mock(),
        )
        controller = self._bind_move_controller(view)
        controller.move_atom = mock.Mock()

        move_item_for(view, bond_item, 4.0, -2.0)
        move_item_for(view, mark_item, 1.0, 2.0)
        move_item_for(view, orbital_item, -3.0, 5.0)
        move_item_for(view, bracket_item, 2.0, 2.0)
        move_item_for(view, arrow_item, 1.5, -0.5)

        controller.move_atom.assert_has_calls(
            [mock.call(1, 4.0, -2.0), mock.call(2, 4.0, -2.0)]
        )
        view.bond_renderer.redraw_connected_bonds.assert_has_calls(
            [mock.call(1, skip_bond_id=None), mock.call(2, skip_bond_id=None)]
        )
        self.assertEqual(mark_item.moves, [(1.0, 2.0)])
        self.assertEqual(mark_item.data(1)["dx"], 5.0)
        self.assertEqual(mark_item.data(1)["dy"], 8.0)
        self.assertEqual(orbital_item.data(1)["center"], QPointF(-1.0, 8.0))
        self.assertEqual(bracket_item.data(1)["rect"], QRectF(3.0, 4.0, 3.0, 4.0))
        self.assertEqual(arrow_item.data(2)["start"], QPointF(1.5, -0.5))
        self.assertEqual(arrow_item.data(2)["end"], QPointF(2.5, 0.5))
        self.assertEqual(arrow_item.data(2)["control"], QPointF(3.5, 1.5))
        self.assertEqual(view.refresh_selection_outline.call_count, 5)

    def test_move_item_shifts_active_handles_glued_to_target(self) -> None:
        from chemvas.ui.handle_state import (
            set_active_handles_for,
            set_handle_target_for,
        )

        shape = _FakeItem("shape", data1={"rect": QRectF(0.0, 0.0, 10.0, 10.0)})
        handle_a = _FakeItem("handle")
        handle_b = _FakeItem("handle")
        view = SimpleNamespace(refresh_selection_outline=mock.Mock())
        self._bind_move_controller(view)
        set_handle_target_for(view, shape)
        set_active_handles_for(view, [handle_a, handle_b])

        move_item_for(view, shape, 5.0, 7.0)

        # The shape's resize handles follow it instead of floating in place.
        self.assertEqual(handle_a.moves, [(5.0, 7.0)])
        self.assertEqual(handle_b.moves, [(5.0, 7.0)])
        self.assertEqual(shape.data(1)["rect"], QRectF(5.0, 7.0, 10.0, 10.0))
        # A shape moves by rebuilding its path (pos stays at the origin) rather than
        # moveBy, so a later resize does not double-apply the offset.
        self.assertEqual(shape.moves, [])
        self.assertEqual(len(shape.paths), 1)

    def test_move_item_covers_bond_mark_and_scene_item_guard_paths(self) -> None:
        invalid_bond_item = _FakeItem("bond", data1="bad")
        missing_bond_item = _FakeItem("bond", data1=1)
        non_int_mark = _FakeItem("mark", data1={"atom_id": "bad"})
        missing_mark_atom = _FakeItem("mark", data1={"atom_id": 9})
        orbital_item = _FakeItem("orbital", data1={"center": (2.0, 3.0)})
        bracket_item = _FakeItem("ts_bracket", data1={"rect": (1.0, 2.0, 3.0, 4.0)})
        arrow_item = _FakeItem(
            "arrow",
            data2={
                "start": "bad",
                "end": QPointF(1.0, 1.0),
                "control": QPointF(2.0, 2.0),
            },
        )
        other_item = _FakeItem("other")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 10.0, 10.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            bond_renderer=SimpleNamespace(redraw_connected_bonds=mock.Mock()),
            services=canvas_runtime_services(
                scene_decoration_build_service=SimpleNamespace(
                    mark_center=mock.Mock(return_value=QPointF(15.0, 18.0))
                )
            ),
            refresh_selection_outline=mock.Mock(),
        )
        controller = self._bind_move_controller(view)
        controller.move_atom = mock.Mock()

        move_item_for(view, invalid_bond_item, 4.0, -2.0)
        move_item_for(view, missing_bond_item, 4.0, -2.0)
        move_item_for(view, non_int_mark, 1.0, 2.0)
        move_item_for(view, missing_mark_atom, 1.0, 2.0)
        move_item_for(view, orbital_item, -3.0, 5.0)
        move_item_for(view, bracket_item, 2.0, 2.0)
        move_item_for(view, arrow_item, 1.5, -0.5)
        move_item_for(view, other_item, 0.5, 0.5)

        controller.move_atom.assert_not_called()
        view.bond_renderer.redraw_connected_bonds.assert_not_called()
        self.assertEqual(non_int_mark.moves, [(1.0, 2.0)])
        self.assertEqual(missing_mark_atom.moves, [(1.0, 2.0)])
        self.assertNotIn("dx", non_int_mark.data(1))
        self.assertNotIn("dx", missing_mark_atom.data(1))
        self.assertEqual(orbital_item.data(1)["center"], (2.0, 3.0))
        self.assertEqual(bracket_item.data(1)["rect"], (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(arrow_item.data(2)["start"], "bad")
        self.assertEqual(arrow_item.data(2)["end"], QPointF(1.0, 1.0))
        self.assertEqual(arrow_item.data(2)["control"], QPointF(3.5, 1.5))
        self.assertEqual(view.refresh_selection_outline.call_count, 6)

    def test_move_atoms_uses_bond_sets_or_falls_back_to_redraw(self) -> None:
        bond_graphic = _FakeItem("bond")
        view = SimpleNamespace(
            bond_renderer=SimpleNamespace(update_bond_geometry=mock.Mock()),
            refresh_selection_outline=mock.Mock(),
        )
        set_bond_items_for(view, {3: [bond_graphic], 4: []})
        controller = self._bind_move_controller(view)
        controller.move_atom = mock.Mock()
        controller.redraw_bonds_for_atoms = mock.Mock()
        controller.move_rings_for_atoms = mock.Mock()

        move_atoms_for(view, set(), 1.0, 2.0)
        controller.move_atom.assert_not_called()

        move_atoms_for(
            view,
            {1, 2},
            3.0,
            -4.0,
            bond_ids={3, 4},
            redraw_bond_ids={5},
            update_selection=False,
        )

        self.assertEqual(
            {call.args[0] for call in controller.move_atom.call_args_list}, {1, 2}
        )
        self.assertEqual(bond_graphic.moves, [(3.0, -4.0)])
        view.bond_renderer.update_bond_geometry.assert_called_once_with(5)
        controller.move_rings_for_atoms.assert_called_once_with({1, 2}, 3.0, -4.0)
        view.refresh_selection_outline.assert_not_called()

        controller.move_atom.reset_mock()
        view.bond_renderer.update_bond_geometry.reset_mock()
        controller.move_rings_for_atoms.reset_mock()

        move_atoms_for(view, {9}, 1.5, 2.5)

        controller.move_atom.assert_called_once_with(9, 1.5, 2.5)
        controller.redraw_bonds_for_atoms.assert_called_once_with({9})
        controller.move_rings_for_atoms.assert_called_once_with({9}, 1.5, 2.5)
        view.refresh_selection_outline.assert_called_once_with()

    def test_move_rings_for_atoms_updates_only_matching_complete_rings(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        short_ring = _FakeRingItem([1, 2, 9])
        non_matching_ring = _FakeRingItem([4, 5, 6])
        invalid_ring = _FakeRingItem("bad")
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 1.0),
                    4: Atom("O", 9.0, 9.0),
                    5: Atom("O", 10.0, 9.0),
                    6: Atom("O", 9.0, 10.0),
                }
            ),
        )
        set_scene_item_collection_for(
            view,
            "ring_items",
            [matching_ring, short_ring, non_matching_ring, invalid_ring],
        )
        controller = self._bind_move_controller(view)

        controller.move_rings_for_atoms({1, 2, 3}, 10.0, 20.0)

        self.assertEqual(matching_ring.polygons, [[(0.0, 0.0), (2.0, 0.0), (1.0, 1.0)]])
        self.assertEqual(short_ring.polygons, [])
        self.assertEqual(non_matching_ring.polygons, [])
        self.assertEqual(invalid_ring.polygons, [])

    def test_move_atoms_uses_capture_bound_rings_without_registry_reads(self) -> None:
        matching_ring = _FakeRingItem([1, 2, 3])
        unrelated_ring = _FakeRingItem([4, 5, 6])
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 2.0, 0.0),
                    3: Atom("C", 1.0, 1.0),
                }
            ),
            refresh_selection_outline=mock.Mock(),
        )
        controller = self._bind_move_controller(view)
        controller.move_atom = mock.Mock()
        controller.redraw_bonds_for_atoms = mock.Mock()

        with mock.patch(
            "chemvas.ui.canvas_move_controller.ring_items_for",
            side_effect=AssertionError("ring registry was rescanned"),
        ) as ring_items_for_port:
            for _ in range(5):
                controller.move_atoms(
                    {1, 2, 3},
                    1.0,
                    -1.0,
                    update_selection=False,
                    affected_ring_items=(matching_ring,),
                )

        ring_items_for_port.assert_not_called()
        self.assertEqual(len(matching_ring.polygons), 5)
        self.assertEqual(unrelated_ring.polygons, [])

    def test_move_atom_updates_model_3d_labels_dots_and_marks(self) -> None:
        label = _FakeItem("atom")
        dot = _FakeItem("dot")
        mark = _FakeItem("mark")
        hit_testing_service = SimpleNamespace(mark_spatial_index_dirty=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}),
            mark_registry=CanvasMarkRegistry({1: [mark]}),
            services=canvas_runtime_services(hit_testing_service=hit_testing_service),
        )
        set_atom_items_for(view, {1: label})
        set_atom_dots_for(view, {1: dot})
        set_atom_coords_3d_for(view, {1: (3.0, 4.0, 5.0)})
        controller = self._bind_move_controller(view)

        controller.move_atom(1, 2.5, -1.5)
        controller.move_atom(9, 2.0, 3.0)

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (3.5, 0.5))
        self.assertEqual(atom_coords_3d_for(view)[1], (5.5, 2.5, 5.0))
        self.assertEqual(label.moves, [(2.5, -1.5)])
        self.assertEqual(dot.moves, [(2.5, -1.5)])
        self.assertEqual(mark.moves, [(2.5, -1.5)])
        hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()

    def test_move_access_delegates_to_controller(self) -> None:
        view = SimpleNamespace()
        item = _FakeItem("arrow")
        controller = mock.Mock()
        self._bind_move_controller(view, controller)

        move_item_for(view, item, 1.0, 2.0, update_selection=False)
        move_atoms_for(
            view,
            {1, 2},
            3.0,
            4.0,
            bond_ids={5},
            redraw_bond_ids={6},
            update_selection=False,
        )

        controller.move_item.assert_called_once_with(
            item, 1.0, 2.0, update_selection=False
        )
        controller.move_atoms.assert_called_once_with(
            {1, 2},
            3.0,
            4.0,
            bond_ids={5},
            redraw_bond_ids={6},
            update_selection=False,
        )

        controller.reset_mock()
        affected_rings = (object(),)
        move_atoms_for(
            view,
            {1},
            2.0,
            -3.0,
            affected_ring_items=affected_rings,
        )

        controller.move_atoms.assert_called_once_with(
            {1},
            2.0,
            -3.0,
            bond_ids=None,
            redraw_bond_ids=None,
            update_selection=True,
            affected_ring_items=affected_rings,
        )


if __name__ == "__main__":
    unittest.main()
