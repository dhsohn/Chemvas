import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
except ModuleNotFoundError:
    QPointF = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QPointF is not None:
    from core.model import Atom, Bond
    from ui.canvas_graph_service import CanvasGraphService, canvas_graph_service_for


@unittest.skipUnless(QPointF is not None, "PyQt6 is required for canvas graph service tests")
class CanvasGraphServiceTest(unittest.TestCase):
    @staticmethod
    def _make_atoms(*atom_ids: int):
        return {atom_id: Atom("C", float(atom_id), float(atom_id % 3)) for atom_id in atom_ids}

    @staticmethod
    def _bond_id_between(model_bonds, a_id: int, b_id: int, skip_bond_id: int | None = None) -> int | None:
        for bond_id, bond in enumerate(model_bonds):
            if bond_id == skip_bond_id or bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return bond_id
        return None

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
            _atom_neighbors={},
            _atom_bond_ids={},
            _graph_version=0,
            _selection_component_cache_signature=None,
            _selection_component_cache=[],
            _bond_cycle_cache={},
            _rotation_axis_cache={},
            _rotation_axis_cache_version=0,
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
        )
        canvas._bond_id_between = lambda a_id, b_id, skip_bond_id=None: self._bond_id_between(
            canvas.model.bonds,
            a_id,
            b_id,
            skip_bond_id=skip_bond_id,
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
            _component_without_bond=mock.Mock(side_effect=[set(comp_a), set(comp_b)]),
        )

    def test_remove_bond_neighbors_preserves_adjacency_when_parallel_bond_exists(self) -> None:
        bonds = [Bond(1, 2, 1), Bond(1, 2, 2)]
        canvas = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds),
            _atom_neighbors={1: {2}, 2: {1}},
            _graph_version=4,
            _bond_id_between=lambda a_id, b_id, skip_bond_id=None: self._bond_id_between(
                bonds,
                a_id,
                b_id,
                skip_bond_id=skip_bond_id,
            ),
        )
        service = CanvasGraphService(canvas)

        service.remove_bond_neighbors(1, 2, skip_bond_id=0)

        self.assertEqual(canvas._atom_neighbors, {1: {2}, 2: {1}})
        self.assertEqual(canvas._graph_version, 4)

        bonds[1] = None
        service.remove_bond_neighbors(1, 2, skip_bond_id=0)

        self.assertEqual(canvas._atom_neighbors, {1: set(), 2: set()})
        self.assertEqual(canvas._graph_version, 5)

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
            _atom_neighbors={},
            _atom_bond_ids={},
            _graph_version=0,
            _selection_component_cache_signature="cached",
            _selection_component_cache=[{1, 2}],
            _bond_cycle_cache={},
        )
        service = CanvasGraphService(canvas)

        service.rebuild_bond_adjacency()

        self.assertEqual(canvas._atom_neighbors, {1: {2}, 2: {1, 3}, 3: {2}})
        self.assertEqual(canvas._atom_bond_ids, {1: {0}, 2: {0, 1}, 3: {1}})
        self.assertEqual(canvas._graph_version, 1)
        self.assertIsNone(canvas._selection_component_cache_signature)
        self.assertEqual(canvas._selection_component_cache, [])
        self.assertFalse(service.bond_in_cycle(0))

        bonds.append(Bond(1, 3, 1))
        service.rebuild_bond_adjacency()

        self.assertEqual(canvas._graph_version, 2)
        self.assertTrue(service.bond_in_cycle(0))

    def test_basic_graph_helpers_cover_existing_entries_components_and_expansion(self) -> None:
        bonds = [Bond(1, 2, 1), None, Bond(3, 4, 1)]
        canvas = self._make_canvas(
            bonds,
            atoms=self._make_atoms(1, 2, 3, 4, 9),
        )
        canvas._atom_neighbors = {1: {2}}
        canvas._atom_bond_ids = {1: {0}}
        canvas._graph_version = 2
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

        self.assertEqual(canvas._atom_neighbors[9], set())
        self.assertEqual(canvas._atom_bond_ids[9], set())
        self.assertEqual(components, {frozenset({1, 2}), frozenset({4})})
        self.assertEqual(service.expand_connected_atoms(set()), set())
        self.assertEqual(service.expand_connected_atoms({1}), {1, 2})

    def test_component_without_bond_and_bond_in_cycle_cover_invalid_none_alt_and_cache_paths(self) -> None:
        alt_canvas = self._make_canvas([Bond(1, 2, 1), Bond(1, 2, 1), Bond(2, 3, 1)])
        alt_service = CanvasGraphService(alt_canvas)
        alt_service.rebuild_bond_adjacency()

        self.assertEqual(alt_service.component_without_bond(1, 0), {1, 2, 3})

        cycle_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 1, 1), None])
        cycle_service = CanvasGraphService(cycle_canvas)
        cycle_service.rebuild_bond_adjacency()

        self.assertFalse(cycle_service.bond_in_cycle(9))
        self.assertFalse(cycle_service.bond_in_cycle(3))
        self.assertTrue(cycle_service.bond_in_cycle(0))

        cycle_canvas._atom_neighbors = {1: set(), 2: set(), 3: set()}

        self.assertTrue(cycle_service.bond_in_cycle(0))

    def test_rotatable_and_component_helpers_cover_invalid_none_and_override_paths(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 2), None])
        canvas._bond_in_cycle = mock.Mock(return_value=False)
        service = CanvasGraphService(canvas)

        self.assertFalse(service.bond_is_rotatable(-1))
        self.assertFalse(service.bond_is_rotatable(1))
        self.assertFalse(service.bond_is_rotatable(0))
        self.assertIsNone(service.bond_component_atoms(-1))
        self.assertIsNone(service.bond_component_atoms(1))

        canvas.model.bonds[0] = Bond(1, 2, 1)
        canvas._component_without_bond = mock.Mock(side_effect=[{1, 3}, {2, 4, 5}])

        self.assertTrue(service.bond_is_rotatable(0))
        self.assertEqual(service.bond_component_atoms(0), {1, 2, 3, 4, 5})

        canvas._bond_in_cycle.return_value = True
        self.assertFalse(service.bond_is_rotatable(0))

    def test_rotation_side_for_bond_covers_direct_and_fallback_choices(self) -> None:
        canvas = self._rotation_canvas({1, 3, 4}, {2, 5})
        service = CanvasGraphService(canvas)

        self.assertEqual(service.rotation_side_for_bond(0, {3}, allow_fallback=False), {1, 3, 4})

        canvas = self._rotation_canvas({1, 3}, {2, 5, 6})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.rotation_side_for_bond(0, {5}, allow_fallback=False), {2, 5, 6})

        canvas = self._rotation_canvas({1, 3, 4}, {2, 5})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.rotation_side_for_bond(0, {1}, allow_fallback=False), {1, 3, 4})

        canvas = self._rotation_canvas({1, 3}, {2, 5})
        service = CanvasGraphService(canvas)
        self.assertIsNone(service.rotation_side_for_bond(0, set(), allow_fallback=False))

        canvas = self._rotation_canvas({1, 3, 4, 7}, {2, 5})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.rotation_side_for_bond(0, {3, 4, 5}, allow_fallback=True), {1, 3, 4, 7})

        canvas = self._rotation_canvas({1, 3}, {2, 5})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.rotation_side_for_bond(0, set(), allow_fallback=True), {1, 3})

    def test_preferred_rotation_side_for_bond_covers_partial_selection_press_and_fallback_matrix(self) -> None:
        canvas = self._rotation_canvas({1, 3, 4}, {2, 5, 6})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {3}, allow_fallback=True), {1, 3, 4})

        canvas = self._rotation_canvas({1, 3, 4}, {2, 5, 6})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {2}, allow_fallback=True), {2, 5, 6})

        canvas = self._rotation_canvas({1, 3, 4, 6}, {2, 5})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {3, 4, 5}, allow_fallback=True), {1, 3, 4, 6})

        canvas = self._rotation_canvas({1, 3, 4, 6, 7, 8}, {2, 5, 9})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.preferred_rotation_side_for_bond(0, {1, 3, 5}, allow_fallback=True), {1, 3, 4, 6, 7, 8})

        canvas = self._rotation_canvas({1, 3}, {2, 4})
        service = CanvasGraphService(canvas)
        self.assertEqual(
            service.preferred_rotation_side_for_bond(0, {3, 4}, press_pos=QPointF(9.0, 0.0), allow_fallback=True),
            {2, 4},
        )
        canvas = self._rotation_canvas({1, 3}, {2, 4})
        service = CanvasGraphService(canvas)
        self.assertIsNone(
            service.preferred_rotation_side_for_bond(0, {3, 4}, press_pos=QPointF(5.0, 0.0), allow_fallback=False)
        )

        canvas = self._rotation_canvas({1, 3}, {2, 4, 5, 6})
        service = CanvasGraphService(canvas)
        self.assertEqual(service.preferred_rotation_side_for_bond(0, set(), allow_fallback=True), {1, 3})

    def test_rotatable_axis_from_selection_covers_cache_single_bond_leaf_boundary_and_candidate_paths(self) -> None:
        cache_canvas = self._make_canvas([Bond(1, 2, 1)])
        cache_canvas._graph_version = 3
        cache_canvas._rotation_axis_cache_version = 3
        cache_key = (frozenset({1}), frozenset({0}), 3)
        cache_canvas._rotation_axis_cache[cache_key] = (0, {1, 2})
        cache_service = CanvasGraphService(cache_canvas)
        self.assertEqual(cache_service.rotatable_axis_from_selection({1}, {0}), (0, {1, 2}))

        single_canvas = self._make_canvas([Bond(1, 2, 1)])
        single_canvas._bond_is_rotatable = mock.Mock(return_value=True)
        single_canvas._preferred_rotation_side_for_bond = mock.Mock(return_value={2})
        single_service = CanvasGraphService(single_canvas)
        self.assertEqual(single_service.rotatable_axis_from_selection(set(), {0}), (0, {2}))

        leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), Bond(1, 4, 1)])
        leaf_canvas._bond_is_rotatable = mock.Mock(return_value=True)
        leaf_canvas._rotation_side_for_bond = mock.Mock(return_value={1, 4})
        leaf_service = CanvasGraphService(leaf_canvas)
        self.assertEqual(leaf_service.rotatable_axis_from_selection(set(), {0, 1}), (0, {1, 4}))

        empty_canvas = self._make_canvas([])
        empty_service = CanvasGraphService(empty_canvas)
        self.assertIsNone(empty_service.rotatable_axis_from_selection(set(), set()))

        boundary_canvas = self._make_canvas([Bond(1, 2, 1)])
        boundary_canvas._bond_is_rotatable = mock.Mock(side_effect=[False])
        boundary_service = CanvasGraphService(boundary_canvas)
        self.assertIsNone(boundary_service.rotatable_axis_from_selection({1}, set()))

        candidate_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1)])
        candidate_canvas._bond_is_rotatable = mock.Mock(side_effect=[True, False])
        candidate_canvas._rotation_side_for_bond = mock.Mock(side_effect=[{1}, None])
        candidate_service = CanvasGraphService(candidate_canvas)
        self.assertEqual(candidate_service.rotatable_axis_from_selection({1, 2, 3}, set()), (0, {1}))

        multi_candidate_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1)])
        multi_candidate_canvas._bond_is_rotatable = mock.Mock(side_effect=[True, True])
        multi_candidate_canvas._rotation_side_for_bond = mock.Mock(side_effect=[{1}, {2, 3}])
        multi_candidate_service = CanvasGraphService(multi_candidate_canvas)
        self.assertIsNone(multi_candidate_service.rotatable_axis_from_selection({1, 2, 3}, set()))

    def test_rotatable_axis_from_selection_covers_cache_reset_invalid_selected_and_no_axis_paths(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 1), None], atoms=self._make_atoms(1, 2))
        canvas._graph_version = 4
        canvas._rotation_axis_cache_version = 3
        canvas._rotation_axis_cache = {"stale": (0, {1})}
        service = CanvasGraphService(canvas)

        self.assertIsNone(service.rotatable_axis_from_selection(set(), {99, 1}))
        self.assertEqual(canvas._rotation_axis_cache, {(frozenset(), frozenset({99, 1}), 4): None})

        single_canvas = self._make_canvas([Bond(1, 2, 1)])
        single_canvas._bond_is_rotatable = mock.Mock(return_value=True)
        single_canvas._preferred_rotation_side_for_bond = mock.Mock(return_value=None)
        single_service = CanvasGraphService(single_canvas)
        self.assertIsNone(single_service.rotatable_axis_from_selection(set(), {0}))

        leaf_canvas = self._make_canvas([Bond(1, 2, 1), Bond(2, 3, 1), None, Bond(1, 4, 1)])
        leaf_canvas._bond_is_rotatable = mock.Mock(return_value=True)
        leaf_canvas._rotation_side_for_bond = mock.Mock(return_value=None)
        leaf_service = CanvasGraphService(leaf_canvas)
        self.assertIsNone(leaf_service.rotatable_axis_from_selection(set(), {0, 1}))

    def test_rotatable_axis_from_selection_covers_boundary_resolution_path(self) -> None:
        canvas = self._make_canvas([Bond(1, 2, 1), None], atoms=self._make_atoms(1, 2, 3))
        canvas._bond_is_rotatable = mock.Mock(side_effect=[True, False])
        canvas._rotation_side_for_bond = mock.Mock(return_value={2})
        service = CanvasGraphService(canvas)

        self.assertEqual(service.rotatable_axis_from_selection({1}, set()), (0, {2}))

    def test_axis_from_rotation_hint_and_bond_sets_cover_remaining_hint_and_fallback_paths(self) -> None:
        canvas = SimpleNamespace(
            _bond_is_rotatable=mock.Mock(side_effect=[False, True, True, True, True]),
            _bond_component_atoms=mock.Mock(side_effect=[None, {1, 2, 3}, {1, 2, 3}, {1, 2, 3}]),
            _preferred_rotation_side_for_bond=mock.Mock(side_effect=[None, {2, 3}]),
        )
        service = CanvasGraphService(canvas)

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
        stale_canvas._atom_bond_ids = {3: {0, 1, 2}}
        stale_service = CanvasGraphService(stale_canvas)
        self.assertEqual(stale_service.bond_sets_for_atoms({3}), (set(), {1}))

    def test_graph_service_factory_reuses_real_duck_typed_and_fallback_services(self) -> None:
        canvas = SimpleNamespace()
        real_service = CanvasGraphService(canvas)
        canvas._canvas_graph_service = real_service

        self.assertIs(canvas_graph_service_for(canvas), real_service)

        duck_service = SimpleNamespace(
            ensure_atom_neighbors=mock.Mock(),
            ensure_atom_bond_ids=mock.Mock(),
            add_bond_neighbors=mock.Mock(),
            remove_bond_neighbors=mock.Mock(),
            add_bond_index=mock.Mock(),
            remove_bond_index=mock.Mock(),
            rebuild_bond_adjacency=mock.Mock(),
            connected_components=mock.Mock(),
            component_without_bond=mock.Mock(),
            bond_in_cycle=mock.Mock(),
            bond_is_rotatable=mock.Mock(),
            bond_component_atoms=mock.Mock(),
            rotation_side_for_bond=mock.Mock(),
            preferred_rotation_side_for_bond=mock.Mock(),
            rotatable_axis_from_selection=mock.Mock(),
            axis_from_rotation_hint=mock.Mock(),
            bond_sets_for_atoms=mock.Mock(),
            expand_connected_atoms=mock.Mock(),
        )
        canvas._canvas_graph_service = duck_service

        self.assertIs(canvas_graph_service_for(canvas), duck_service)

        canvas._canvas_graph_service = object()

        self.assertIsInstance(canvas_graph_service_for(canvas), CanvasGraphService)

    def test_axis_from_rotation_hint_rejects_atoms_outside_component(self) -> None:
        canvas = SimpleNamespace(
            _bond_is_rotatable=mock.Mock(return_value=True),
            _bond_component_atoms=mock.Mock(return_value={1, 2, 3}),
            _preferred_rotation_side_for_bond=mock.Mock(return_value={2, 3}),
        )
        service = CanvasGraphService(canvas)

        self.assertIsNone(service.axis_from_rotation_hint(4, {9}, press_pos=QPointF(1.0, 2.0)))
        canvas._preferred_rotation_side_for_bond.assert_not_called()

        self.assertEqual(
            service.axis_from_rotation_hint(4, {2, 9}, press_pos=QPointF(3.0, 4.0)),
            (4, {2, 3}),
        )
        canvas._preferred_rotation_side_for_bond.assert_called_once_with(
            4,
            {2},
            press_pos=QPointF(3.0, 4.0),
            allow_fallback=True,
        )


if __name__ == "__main__":
    unittest.main()
