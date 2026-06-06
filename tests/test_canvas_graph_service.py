import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
except ModuleNotFoundError:
    QPointF = None

if QPointF is not None:
    from core.model import Atom, Bond
    from ui.canvas_graph_service import CanvasGraphService
    from ui.canvas_graph_state import CanvasGraphState


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for canvas graph service tests")
class CanvasGraphServiceTest(unittest.TestCase):
    @staticmethod
    def _make_atoms(*atom_ids: int):
        return {atom_id: Atom("C", float(atom_id), float(atom_id % 3)) for atom_id in atom_ids}

    def _make_canvas(self, bonds, atoms=None, **extra):
        if atoms is None:
            atom_ids = sorted(
                {
                    atom_id
                    for bond in bonds
                    if bond is not None
                    for atom_id in (bond.a, bond.b)
                }
            )
            atoms = self._make_atoms(*atom_ids)
        canvas = SimpleNamespace(
            model=SimpleNamespace(atoms=atoms, bonds=list(bonds)),
            graph_state=CanvasGraphState(),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        for name, value in extra.items():
            setattr(canvas, name, value)
        return canvas

    def _rotation_canvas(self, comp_a, comp_b, *, atoms=None):
        if atoms is None:
            atoms = {
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            }
        return SimpleNamespace(
            model=SimpleNamespace(atoms=atoms, bonds=[Bond(1, 2, 1)]),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )

    def _rotation_service(self, comp_a, comp_b, *, atoms=None):
        service = CanvasGraphService(self._rotation_canvas(comp_a, comp_b, atoms=atoms))
        service.component_without_bond = mock.Mock(side_effect=[set(comp_a), set(comp_b)] * 20)
        return service

    def test_remove_bond_neighbors_preserves_adjacency_when_parallel_bond_exists(self) -> None:
        bonds = [Bond(1, 2, 1), Bond(1, 2, 2)]
        canvas = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds),
            graph_state=CanvasGraphState(atom_neighbors={1: {2}, 2: {1}}, graph_version=4),
        )
        service = CanvasGraphService(canvas)

        service.remove_bond_neighbors(1, 2, skip_bond_id=0)

        self.assertEqual(canvas.graph_state.atom_neighbors, {1: {2}, 2: {1}})
        self.assertEqual(canvas.graph_state.graph_version, 4)

        bonds[1] = None
        service.remove_bond_neighbors(1, 2, skip_bond_id=0)

        self.assertEqual(canvas.graph_state.atom_neighbors, {1: set(), 2: set()})
        self.assertEqual(canvas.graph_state.graph_version, 5)

    def test_rebuild_bond_adjacency_resets_component_cache_and_invalidates_cycle_cache(self) -> None:
        bonds = [Bond(1, 2, 1), Bond(2, 3, 1)]
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("C", 1.0, 0.0),
                    3: Atom("C", 2.0, 0.0),
                },
                bonds=bonds,
            ),
            graph_state=CanvasGraphState(
                selection_component_cache_signature="cached",
                selection_component_cache=[{1, 2}],
            ),
        )
        service = CanvasGraphService(canvas)

        service.rebuild_bond_adjacency()

        self.assertEqual(canvas.graph_state.atom_neighbors, {1: {2}, 2: {1, 3}, 3: {2}})
        self.assertEqual(canvas.graph_state.atom_bond_ids, {1: {0}, 2: {0, 1}, 3: {1}})
        self.assertEqual(canvas.graph_state.graph_version, 1)
        self.assertIsNone(canvas.graph_state.selection_component_cache_signature)
        self.assertEqual(canvas.graph_state.selection_component_cache, [])
        self.assertFalse(service.bond_in_cycle(0))

        bonds.append(Bond(1, 3, 1))
        service.rebuild_bond_adjacency()

        self.assertEqual(canvas.graph_state.graph_version, 2)
        self.assertTrue(service.bond_in_cycle(0))

    def test_basic_graph_helpers_cover_existing_entries_components_and_expansion(self) -> None:
        bonds = [Bond(1, 2, 1), None, Bond(3, 4, 1)]
        canvas = self._make_canvas(
            bonds,
            atoms=self._make_atoms(1, 2, 3, 4, 9),
        )
        canvas.graph_state.atom_neighbors = {1: {2}}
        canvas.graph_state.atom_bond_ids = {1: {0}}
        canvas.graph_state.graph_version = 2
        service = CanvasGraphService(canvas)

        service.ensure_atom_neighbors(1)
        service.ensure_atom_neighbors(9)
        service.ensure_atom_bond_ids(1)
        service.ensure_atom_bond_ids(9)
        service.add_bond_neighbors(3, 4)
        service.remove_bond_neighbors(1, 9)
        service.add_bond_index(2, 3, 4)
        service.remove_bond_index(2, 3, 4)
        service.remove_bond_index(99, 3, 4)
        service.rebuild_bond_adjacency()

        components = {frozenset(component) for component in service.connected_components({1, 2, 4})}

        self.assertEqual(canvas.graph_state.atom_neighbors[9], set())
        self.assertEqual(canvas.graph_state.atom_bond_ids[9], set())
        self.assertEqual(components, {frozenset({1, 2}), frozenset({4})})
        self.assertEqual(service.expand_connected_atoms(set()), set())
        self.assertEqual(service.expand_connected_atoms({1}), {1, 2})

    def test_component_without_bond_and_bond_in_cycle_cover_invalid_none_alt_and_cache_paths(self) -> None:
        alt_canvas = self._make_canvas([Bond(1, 2, 1), Bond(1, 2, 1), Bond(2, 3, 1)])
        alt_service = CanvasGraphService(alt_canvas)
        alt_service.rebuild_bond_adjacency()

        self.assertEqual(alt_service.component_without_bond(1, 0), {1, 2, 3})
        self.assertEqual(alt_service.component_without_bond(1, 99), {1, 2, 3})

        none_skip_canvas = self._make_canvas([None, Bond(1, 2, 1), Bond(2, 3, 1)])
        none_skip_service = CanvasGraphService(none_skip_canvas)
        none_skip_service.rebuild_bond_adjacency()
        self.assertEqual(none_skip_service.component_without_bond(1, 0), {1, 2, 3})

        cycle_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 1, 1), None])
        cycle_service = CanvasGraphService(cycle_canvas)
        cycle_service.rebuild_bond_adjacency()

        self.assertFalse(cycle_service.bond_in_cycle(9))
        self.assertFalse(cycle_service.bond_in_cycle(3))
        self.assertTrue(cycle_service.bond_in_cycle(0))

        cycle_canvas.graph_state.atom_neighbors = {1: set(), 2: set(), 3: set()}

        self.assertTrue(cycle_service.bond_in_cycle(0))

    def test_rotatable_and_component_helpers_cover_invalid_none_and_override_paths(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 2), None])
        service = CanvasGraphService(canvas)
        service.bond_in_cycle = mock.Mock(return_value=False)

        self.assertFalse(service.bond_is_rotatable(-1))
        self.assertFalse(service.bond_is_rotatable(1))
        self.assertFalse(service.bond_is_rotatable(0))
        self.assertIsNone(service.bond_component_atoms(-1))
        self.assertIsNone(service.bond_component_atoms(1))

        canvas.model.bonds[0] = Bond(1, 2, 1)
        service.component_without_bond = mock.Mock(side_effect=[{1, 3}, {2, 4, 5}])

        self.assertTrue(service.bond_is_rotatable(0))
        self.assertEqual(service.bond_component_atoms(0), {1, 2, 3, 4, 5})

        service.bond_in_cycle.return_value = True
        self.assertFalse(service.bond_is_rotatable(0))

    def test_rotation_side_for_bond_covers_direct_and_fallback_choices(self) -> None:
        service = self._rotation_service({1, 3, 4}, {2, 5})

        self.assertEqual(service.rotation_side_for_bond(0, {3}, allow_fallback=False), {1, 3, 4})

        service = self._rotation_service({1, 3}, {2, 5, 6})
        self.assertEqual(service.rotation_side_for_bond(0, {5}, allow_fallback=False), {2, 5, 6})

        service = self._rotation_service({1, 3, 4}, {2, 5})
        self.assertEqual(service.rotation_side_for_bond(0, {1}, allow_fallback=False), {1, 3, 4})

        service = self._rotation_service({1, 3}, {2, 5})
        self.assertIsNone(service.rotation_side_for_bond(0, set(), allow_fallback=False))

        service = self._rotation_service({1, 3, 4, 7}, {2, 5})
        self.assertEqual(service.rotation_side_for_bond(0, {3, 4, 5}, allow_fallback=True), {1, 3, 4, 7})

        service = self._rotation_service({1, 3}, {2, 5})
        self.assertEqual(service.rotation_side_for_bond(0, set(), allow_fallback=True), {1, 3})

    def test_preferred_rotation_side_for_bond_covers_partial_selection_press_and_fallback_matrix(self) -> None:
        service = self._rotation_service({1, 3, 4}, {2, 5, 6})
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {3}, allow_fallback=True), {1, 3, 4})

        service = self._rotation_service({1, 3, 4}, {2, 5, 6})
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {2}, allow_fallback=True), {2, 5, 6})

        service = self._rotation_service({1, 3, 4, 6}, {2, 5})
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {3, 4, 5}, allow_fallback=True), {1, 3, 4, 6})

        service = self._rotation_service({1, 3, 4, 6, 7, 8}, {2, 5, 9})
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {1, 3, 5}, allow_fallback=True), {1, 3, 4, 6, 7, 8})

        service = self._rotation_service({1, 3}, {2, 4})
        self.assertEqual(
            service.preferred_rotation_side_for_bond(0, {3, 4}, press_pos=QPointF(9.0, 0.0), allow_fallback=True),
            {2, 4},
        )
        service = self._rotation_service({1, 3}, {2, 4})
        self.assertIsNone(
            service.preferred_rotation_side_for_bond(0, {3, 4}, press_pos=QPointF(5.0, 0.0), allow_fallback=False)
        )

        service = self._rotation_service({1, 3}, {2, 4, 5, 6})
        self.assertEqual(service.preferred_rotation_side_for_bond(0, set(), allow_fallback=True), {1, 3})

    def test_rotatable_axis_from_selection_covers_cache_single_bond_leaf_boundary_and_candidate_paths(self) -> None:
        cache_canvas = self._make_canvas([Bond(1, 2, 1)])
        cache_canvas.graph_state.graph_version = 3
        cache_canvas.graph_state.rotation_axis_cache_version = 3
        cache_key = (frozenset({1}), frozenset({0}), 3)
        cache_canvas.graph_state.rotation_axis_cache[cache_key] = (0, {1, 2})
        cache_service = CanvasGraphService(cache_canvas)
        self.assertEqual(cache_service.rotatable_axis_from_selection({1}, {0}), (0, {1, 2}))

        single_canvas = self._make_canvas([Bond(1, 2, 1)])
        single_service = CanvasGraphService(single_canvas)
        single_service.bond_is_rotatable = mock.Mock(return_value=True)
        single_service.preferred_rotation_side_for_bond = mock.Mock(return_value={2})
        self.assertEqual(single_service.rotatable_axis_from_selection(set(), {0}), (0, {2}))

        leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), Bond(1, 4, 1)])
        leaf_service = CanvasGraphService(leaf_canvas)
        leaf_service.bond_is_rotatable = mock.Mock(return_value=True)
        leaf_service.rotation_side_for_bond = mock.Mock(return_value={1, 4})
        self.assertEqual(leaf_service.rotatable_axis_from_selection(set(), {0, 1}), (0, {1, 4}))

        empty_canvas = self._make_canvas([])
        empty_service = CanvasGraphService(empty_canvas)
        self.assertIsNone(empty_service.rotatable_axis_from_selection(set(), set()))

        boundary_canvas = self._make_canvas([Bond(1, 2, 1)])
        boundary_service = CanvasGraphService(boundary_canvas)
        boundary_service.bond_is_rotatable = mock.Mock(side_effect=[False])
        self.assertIsNone(boundary_service.rotatable_axis_from_selection({1}, set()))

        candidate_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1)])
        candidate_service = CanvasGraphService(candidate_canvas)
        candidate_service.bond_is_rotatable = mock.Mock(side_effect=[True, False])
        candidate_service.rotation_side_for_bond = mock.Mock(side_effect=[{1}, None])
        self.assertEqual(candidate_service.rotatable_axis_from_selection({1, 2, 3}, set()), (0, {1}))

        multi_candidate_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1)])
        multi_candidate_service = CanvasGraphService(multi_candidate_canvas)
        multi_candidate_service.bond_is_rotatable = mock.Mock(side_effect=[True, True])
        multi_candidate_service.rotation_side_for_bond = mock.Mock(side_effect=[{1}, {2, 3}])
        self.assertIsNone(multi_candidate_service.rotatable_axis_from_selection({1, 2, 3}, set()))

    def test_rotatable_axis_from_selection_covers_cache_reset_invalid_selected_and_no_axis_paths(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 1), None], atoms=self._make_atoms(1, 2))
        canvas.graph_state.graph_version = 4
        canvas.graph_state.rotation_axis_cache_version = 3
        canvas.graph_state.rotation_axis_cache = {"stale": (0, {1})}
        service = CanvasGraphService(canvas)

        self.assertIsNone(service.rotatable_axis_from_selection(set(), {99, 1}))
        self.assertEqual(canvas.graph_state.rotation_axis_cache, {(frozenset(), frozenset({99, 1}), 4): None})

        single_canvas = self._make_canvas([Bond(1, 2, 1)])
        single_service = CanvasGraphService(single_canvas)
        single_service.bond_is_rotatable = mock.Mock(return_value=True)
        single_service.preferred_rotation_side_for_bond = mock.Mock(return_value=None)
        self.assertIsNone(single_service.rotatable_axis_from_selection(set(), {0}))

        leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), None, Bond(1, 4, 1)])
        leaf_service = CanvasGraphService(leaf_canvas)
        leaf_service.bond_is_rotatable = mock.Mock(return_value=True)
        leaf_service.rotation_side_for_bond = mock.Mock(return_value=None)
        self.assertIsNone(leaf_service.rotatable_axis_from_selection(set(), {0, 1}))

    def test_rotatable_axis_from_selection_covers_boundary_resolution_path(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 1), None], atoms=self._make_atoms(1, 2, 3))
        service = CanvasGraphService(canvas)
        service.bond_is_rotatable = mock.Mock(side_effect=[True, False])
        service.rotation_side_for_bond = mock.Mock(return_value={2})

        self.assertEqual(service.rotatable_axis_from_selection({1}, set()), (0, {2}))

    def test_axis_from_rotation_hint_and_bond_sets_cover_remaining_hint_and_fallback_paths(self) -> None:
        canvas = SimpleNamespace()
        service = CanvasGraphService(canvas)
        service.bond_is_rotatable = mock.Mock(side_effect=[False, True, True, True, True])
        service.bond_component_atoms = mock.Mock(side_effect=[None, {1, 2, 3}, {1, 2, 3}, {1, 2, 3}])
        service.preferred_rotation_side_for_bond = mock.Mock(side_effect=[None, {2, 3}])

        self.assertIsNone(service.axis_from_rotation_hint(4, {1}))
        self.assertIsNone(service.axis_from_rotation_hint(4, {1}))
        self.assertIsNone(service.axis_from_rotation_hint(4, {9}))
        self.assertIsNone(service.axis_from_rotation_hint(4, {2}))
        self.assertEqual(service.axis_from_rotation_hint(4, {2, 9}), (4, {2, 3}))

        bond_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), None])
        bond_service = CanvasGraphService(bond_canvas)

        self.assertEqual(bond_service.bond_sets_for_atoms(set()), (set(), set()))
        self.assertEqual(bond_service.bond_sets_for_atoms({1, 2}), ({0}, {1}))
        self.assertEqual(bond_service.expand_connected_atoms({3}), {1, 2, 3})

        stale_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), None], atoms=self._make_atoms(1, 2, 3))
        stale_canvas.graph_state.atom_bond_ids = {3: {0, 1, 2}}
        stale_service = CanvasGraphService(stale_canvas)
        self.assertEqual(stale_service.bond_sets_for_atoms({3}), (set(), {1}))

    def test_axis_from_rotation_hint_rejects_atoms_outside_component(self) -> None:
        canvas = SimpleNamespace()
        service = CanvasGraphService(canvas)
        service.bond_is_rotatable = mock.Mock(return_value=True)
        service.bond_component_atoms = mock.Mock(return_value={1, 2, 3})
        service.preferred_rotation_side_for_bond = mock.Mock(return_value={2, 3})

        self.assertIsNone(service.axis_from_rotation_hint(4, {9}, press_pos=QPointF(1.0, 2.0)))
        service.preferred_rotation_side_for_bond.assert_not_called()

        self.assertEqual(
            service.axis_from_rotation_hint(4, {2, 9}, press_pos=QPointF(3.0, 4.0)),
            (4, {2, 3}),
        )
        service.preferred_rotation_side_for_bond.assert_called_once_with(
            4,
            {2},
            press_pos=QPointF(3.0, 4.0),
            allow_fallback=True,
        )

    def test_preferred_rotation_side_covers_remaining_none_overlap_endpoint_and_distance_paths(self) -> None:
        none_service = self._rotation_service({1, 3}, {2, 4})
        none_service.canvas.model.bonds = [None]
        self.assertIsNone(none_service.rotation_side_for_bond(0, {3}, allow_fallback=True))
        self.assertIsNone(none_service.preferred_rotation_side_for_bond(0, {3}, allow_fallback=True))

        selected_b_service = self._rotation_service({1, 3}, {2, 4, 5})
        self.assertEqual(selected_b_service.preferred_rotation_side_for_bond(0, {4}, allow_fallback=True), {2, 4, 5})

        overlap_a_service = self._rotation_service({1, 3}, {2, 4, 5})
        self.assertEqual(overlap_a_service.preferred_rotation_side_for_bond(0, {1}, allow_fallback=True), {1, 3})

        endpoint_service = self._rotation_service({1}, {1})
        self.assertEqual(endpoint_service.preferred_rotation_side_for_bond(0, {1}, allow_fallback=True), {1})

        distance_service = self._rotation_service({1, 3}, {2, 4})
        self.assertEqual(
            distance_service.preferred_rotation_side_for_bond(
                0,
                set(),
                press_pos=QPointF(5.0, 0.0),
                allow_fallback=True,
            ),
            {1, 3},
        )

    def test_rotatable_axis_and_bond_sets_cover_remaining_boundary_none_and_isolated_paths(self) -> None:
        boundary_canvas = self._make_canvas([Bond(1, 2, 1)], atoms=self._make_atoms(1, 2, 3))
        boundary_service = CanvasGraphService(boundary_canvas)
        boundary_service.bond_is_rotatable = mock.Mock(return_value=True)
        boundary_service.rotation_side_for_bond = mock.Mock(return_value=None)

        self.assertIsNone(boundary_service.rotatable_axis_from_selection({1}, set()))

        isolated_canvas = self._make_canvas([Bond(1, 2, 1)], atoms=self._make_atoms(1, 2, 9))
        isolated_service = CanvasGraphService(isolated_canvas)
        self.assertEqual(isolated_service.bond_sets_for_atoms({9}), (set(), set()))

    def test_preferred_rotation_side_and_rotatable_axis_cover_remaining_fallback_paths(self) -> None:
        reverse_service = CanvasGraphService(
            SimpleNamespace(
                model=SimpleNamespace(
                    atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)},
                    bonds=[Bond(2, 1, 1)],
                ),
                renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            )
        )
        reverse_service.component_without_bond = mock.Mock(side_effect=[{2, 4}, {1, 3}])
        self.assertEqual(reverse_service.preferred_rotation_side_for_bond(0, set(), allow_fallback=True), {1, 3})

        single_canvas = self._make_canvas([Bond(1, 2, 1)])
        single_service = CanvasGraphService(single_canvas)
        single_service.bond_is_rotatable = mock.Mock(return_value=False)
        self.assertIsNone(single_service.rotatable_axis_from_selection(set(), {0}))

        no_leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1)])
        no_leaf_service = CanvasGraphService(no_leaf_canvas)
        no_leaf_service.bond_is_rotatable = mock.Mock(return_value=False)
        self.assertIsNone(no_leaf_service.rotatable_axis_from_selection(set(), {0, 1}))

        unique_leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), Bond(1, 4, 1)])
        unique_leaf_service = CanvasGraphService(unique_leaf_canvas)
        unique_leaf_service.bond_is_rotatable = mock.Mock(return_value=False)
        self.assertIsNone(unique_leaf_service.rotatable_axis_from_selection(set(), {0, 1}))


if __name__ == "__main__":
    unittest.main()
