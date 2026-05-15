import unittest
from unittest import mock

from core.model import Atom, Bond
from ui.structure_geometry_logic import (
    _atom_neighbor_points,
    _bond_endpoints,
    compute_free_benzene_ring_points,
    compute_regular_ring_points_for_atom,
    compute_regular_ring_points_for_bond,
    compute_sprout_bond_endpoint,
    compute_template_points_for_bond,
)


class StructureGeometryLogicTest(unittest.TestCase):
    def test_compute_free_benzene_ring_points_builds_regular_hexagon(self) -> None:
        points = compute_free_benzene_ring_points((10.0, 20.0), bond_length=12.0)

        self.assertEqual(len(points), 6)
        self.assertAlmostEqual(points[0][0], 20.392304845413264)
        self.assertAlmostEqual(points[0][1], 14.0)
        self.assertAlmostEqual(points[3][0], -0.39230484541326405)
        self.assertAlmostEqual(points[3][1], 26.0)

    def test_compute_sprout_bond_endpoint_handles_default_and_cyclic_cases(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
            3: Atom("C", 0.0, 10.0),
        }

        self.assertIsNone(
            compute_sprout_bond_endpoint(
                99,
                atoms=atoms,
                bonds=[],
                bond_length=20.0,
                cyclic=False,
                default_endpoint=(5.0, 5.0),
            )
        )
        self.assertEqual(
            compute_sprout_bond_endpoint(
                1,
                atoms=atoms,
                bonds=[],
                bond_length=20.0,
                cyclic=False,
                default_endpoint=(5.0, 5.0),
            ),
            (5.0, 5.0),
        )

        no_neighbor = compute_sprout_bond_endpoint(
            1,
            atoms=atoms,
            bonds=[],
            bond_length=20.0,
            cyclic=True,
        )
        self.assertIsNotNone(no_neighbor)
        assert no_neighbor is not None
        self.assertAlmostEqual(no_neighbor[0], 10.0)
        self.assertAlmostEqual(no_neighbor[1], 17.320508075688775)

        one_neighbor = compute_sprout_bond_endpoint(
            1,
            atoms=atoms,
            bonds=[Bond(1, 2, 1)],
            bond_length=20.0,
            cyclic=True,
        )
        assert one_neighbor is not None
        self.assertAlmostEqual(one_neighbor[0], -10.0)
        self.assertAlmostEqual(one_neighbor[1], 17.320508075688775)

        two_neighbors = compute_sprout_bond_endpoint(
            1,
            atoms=atoms,
            bonds=[Bond(1, 2, 1), Bond(1, 3, 1)],
            bond_length=20.0,
            cyclic=True,
        )
        assert two_neighbors is not None
        self.assertAlmostEqual(two_neighbors[0], -10.0)
        self.assertAlmostEqual(two_neighbors[1], -17.32050807568877)

    def test_compute_sprout_bond_endpoint_skips_zero_length_vectors_and_balanced_neighbors(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 0.0, 0.0),
            3: Atom("C", 10.0, 0.0),
            4: Atom("C", -10.0, 0.0),
        }

        zero_length_neighbor = compute_sprout_bond_endpoint(
            1,
            atoms=atoms,
            bonds=[Bond(1, 2, 1)],
            bond_length=20.0,
            cyclic=True,
        )
        assert zero_length_neighbor is not None
        self.assertAlmostEqual(zero_length_neighbor[0], 10.0)
        self.assertAlmostEqual(zero_length_neighbor[1], 17.320508075688775)

        balanced_neighbors = compute_sprout_bond_endpoint(
            1,
            atoms=atoms,
            bonds=[Bond(1, 3, 1), Bond(1, 4, 1)],
            bond_length=20.0,
            cyclic=True,
        )
        assert balanced_neighbors is not None
        self.assertAlmostEqual(balanced_neighbors[0], -10.0)
        self.assertAlmostEqual(balanced_neighbors[1], 17.320508075688775)

    def test_compute_regular_ring_points_for_atom_forwards_geometry_inputs(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        bonds = [Bond(1, 2, 1)]

        self.assertIsNone(
            compute_regular_ring_points_for_atom(
                2,
                1,
                atoms=atoms,
                bonds=bonds,
                bond_length=20.0,
            )
        )

        with mock.patch(
            "ui.structure_geometry_logic.build_regular_ring_points_for_atom",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as build_ring:
            result = compute_regular_ring_points_for_atom(
                6,
                1,
                atoms=atoms,
                bonds=bonds,
                bond_length=20.0,
            )

        self.assertEqual(result, ([(1.0, 2.0), (3.0, 4.0)], [(1, 0.0, 0.0)]))
        build_ring.assert_called_once_with(6, (0.0, 0.0), [(10.0, 0.0)], 20.0)

    def test_compute_regular_ring_points_for_atom_returns_none_for_missing_atom_or_geometry_failure(self) -> None:
        atoms = {1: Atom("C", 0.0, 0.0)}

        self.assertIsNone(
            compute_regular_ring_points_for_atom(
                6,
                99,
                atoms=atoms,
                bonds=[],
                bond_length=20.0,
            )
        )

        with mock.patch(
            "ui.structure_geometry_logic.build_regular_ring_points_for_atom",
            return_value=None,
        ) as build_ring:
            self.assertIsNone(
                compute_regular_ring_points_for_atom(
                    6,
                    1,
                    atoms=atoms,
                    bonds=[],
                    bond_length=20.0,
                )
            )

        build_ring.assert_called_once_with(6, (0.0, 0.0), [], 20.0)

    def test_compute_regular_ring_points_for_bond_forwards_hint_and_polygon(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        bonds = [Bond(1, 2, 1), None]

        self.assertIsNone(
            compute_regular_ring_points_for_bond(
                6,
                1,
                atoms=atoms,
                bonds=bonds,
            )
        )

        with mock.patch(
            "ui.structure_geometry_logic.build_regular_ring_points_for_bond",
            return_value=[(5.0, 6.0), (7.0, 8.0)],
        ) as build_ring:
            result = compute_regular_ring_points_for_bond(
                6,
                0,
                atoms=atoms,
                bonds=bonds,
                center_hint=(4.0, 5.0),
                occupied_polygon=[(0.0, 0.0), (1.0, 1.0)],
            )

        self.assertEqual(
            result,
            ([(5.0, 6.0), (7.0, 8.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
        )
        build_ring.assert_called_once_with(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            center_hint=(4.0, 5.0),
            occupied_polygon=[(0.0, 0.0), (1.0, 1.0)],
        )

    def test_compute_regular_ring_points_for_bond_and_template_return_none_for_invalid_or_missing_geometry(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        bonds = [Bond(1, 2, 1)]

        self.assertIsNone(
            compute_regular_ring_points_for_bond(
                2,
                0,
                atoms=atoms,
                bonds=bonds,
            )
        )

        with mock.patch(
            "ui.structure_geometry_logic.build_regular_ring_points_for_bond",
            return_value=None,
        ) as build_ring:
            self.assertIsNone(
                compute_regular_ring_points_for_bond(
                    6,
                    0,
                    atoms=atoms,
                    bonds=bonds,
                    center_hint=(4.0, 5.0),
                    occupied_polygon=[(0.0, 0.0)],
                )
            )

        build_ring.assert_called_once_with(
            6,
            (0.0, 0.0),
            (10.0, 0.0),
            center_hint=(4.0, 5.0),
            occupied_polygon=[(0.0, 0.0)],
        )

        with mock.patch(
            "ui.structure_geometry_logic.project_template_on_bond",
            return_value=None,
        ) as project:
            self.assertIsNone(
                compute_template_points_for_bond(
                    [(1.0, 2.0), (3.0, 4.0)],
                    0,
                    atoms=atoms,
                    bonds=bonds,
                    center_hint=(6.0, 7.0),
                    occupied_polygon=[(9.0, 9.0)],
                )
            )

        project.assert_called_once_with(
            [(1.0, 2.0), (3.0, 4.0)],
            (0.0, 0.0),
            (10.0, 0.0),
            center_hint=(6.0, 7.0),
            occupied_polygon=[(9.0, 9.0)],
        )

    def test_compute_template_points_for_bond_projects_template_and_validates_input(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("C", 10.0, 0.0),
        }
        bonds = [Bond(1, 2, 1), None]

        self.assertIsNone(
            compute_template_points_for_bond(
                [(1.0, 2.0)],
                0,
                atoms=atoms,
                bonds=bonds,
            )
        )
        self.assertIsNone(
            compute_template_points_for_bond(
                [(1.0, 2.0), (3.0, 4.0)],
                1,
                atoms=atoms,
                bonds=bonds,
            )
        )

        with mock.patch(
            "ui.structure_geometry_logic.project_template_on_bond",
            return_value=[(2.0, 3.0), (4.0, 5.0)],
        ) as project:
            result = compute_template_points_for_bond(
                [(1.0, 2.0), (3.0, 4.0)],
                0,
                atoms=atoms,
                bonds=bonds,
                center_hint=(6.0, 7.0),
                occupied_polygon=[(9.0, 9.0)],
            )

        self.assertEqual(
            result,
            ([(2.0, 3.0), (4.0, 5.0)], [(1, 0.0, 0.0), (2, 10.0, 0.0)]),
        )
        project.assert_called_once_with(
            [(1.0, 2.0), (3.0, 4.0)],
            (0.0, 0.0),
            (10.0, 0.0),
            center_hint=(6.0, 7.0),
            occupied_polygon=[(9.0, 9.0)],
        )

    def test_internal_neighbor_and_endpoint_helpers_skip_invalid_entries(self) -> None:
        atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("O", 10.0, 0.0),
        }

        self.assertIsNone(_atom_neighbor_points(99, atoms=atoms, bonds=[]))
        self.assertEqual(
            _atom_neighbor_points(
                1,
                atoms=atoms,
                bonds=[None, Bond(2, 3, 1), Bond(1, 99, 1), Bond(1, 2, 1)],
            ),
            ((0.0, 0.0), [(10.0, 0.0)]),
        )

        self.assertIsNone(_bond_endpoints(-1, atoms=atoms, bonds=[Bond(1, 2, 1)]))
        self.assertIsNone(_bond_endpoints(0, atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 2, 1)]))


if __name__ == "__main__":
    unittest.main()
