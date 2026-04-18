import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

from PyQt6.QtCore import QPointF


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Atom, Bond, MoleculeModel
from ui.structure_build_service import StructureBuildService


class _FakeRect:
    def __init__(self, center: QPointF) -> None:
        self._center = center

    def center(self) -> QPointF:
        return self._center


class _FakeViewport:
    def __init__(self, center: QPointF) -> None:
        self._center = center

    def rect(self) -> _FakeRect:
        return _FakeRect(self._center)


class _FakePolygon:
    def __init__(self, contains: bool) -> None:
        self._contains = contains

    def containsPoint(self, point: QPointF, fill_rule) -> bool:
        return self._contains


class _FakeRingItem:
    def __init__(self, contains: bool) -> None:
        self._polygon = _FakePolygon(contains)

    def polygon(self) -> _FakePolygon:
        return self._polygon


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.viewport_center = QPointF(50.0, 60.0)
        self._default_endpoint = QPointF(30.0, 0.0)
        self._sprout_endpoint = QPointF(20.0, 0.0)
        self.last_smiles_input = "before"
        self.added_graphics: list[int] = []
        self.carbon_dots: list[int] = []
        self.wrapper_label_calls: list[tuple] = []
        self.ring_points_calls: list[tuple[int, tuple[float, float], float | None]] = []
        self.regular_ring_radius_calls: list[int] = []
        self.record_calls: list[dict] = []
        self.redrawn_bonds: list[int] = []
        self.redrawn_connected: list[tuple[int, int | None]] = []
        self.recorded_bond_updates: list[tuple] = []
        self.scene_items: list[object] = []
        self.ring_items: list[object] = []
        self.find_atom_near = Mock(return_value=None)

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self.viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def _regular_ring_radius(self, n: int) -> float:
        self.regular_ring_radius_calls.append(n)
        return 12.0 + n

    def _ring_points(self, center: QPointF, n: int, radius: float | None = None):
        self.ring_points_calls.append((n, (center.x(), center.y()), radius))
        return [QPointF(center.x() + i, center.y() - i) for i in range(n)]

    def add_atom(self, element: str, x: float, y: float) -> int:
        return self.model.add_atom(element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

    def _atom_point(self, atom_id: int) -> QPointF:
        atom = self.model.atoms[atom_id]
        return QPointF(atom.x, atom.y)

    def _sprout_bond_endpoint(self, atom_id: int, cyclic: bool = False):
        if atom_id not in self.model.atoms:
            return None
        return QPointF(self._sprout_endpoint.x(), self._sprout_endpoint.y())

    def _default_bond_endpoint(self, start: QPointF, start_atom_id: int | None):
        return QPointF(self._default_endpoint.x(), self._default_endpoint.y())

    def _bond_id_between(self, a_id: int, b_id: int) -> int | None:
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return bond_id
        return None

    def _bond_exists(self, a_id: int, b_id: int) -> bool:
        return self._bond_id_between(a_id, b_id) is not None

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {"a": bond.a, "b": bond.b, "order": bond.order, "style": bond.style}

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.added_graphics.append(bond_id)

    def _redraw_bond(self, bond_id: int) -> None:
        self.redrawn_bonds.append(bond_id)

    def _redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        self.redrawn_connected.append((atom_id, skip_bond_id))

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        self.carbon_dots.append(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        self.wrapper_label_calls.append((atom_id, text, clear_smiles, record, allow_merge, show_carbon))

    def _record_additions(self, **kwargs) -> None:
        self.record_calls.append(kwargs)

    def _record_bond_update(self, *args) -> None:
        self.recorded_bond_updates.append(args)

    def scene(self):
        return SimpleNamespace(addItem=lambda item: self.scene_items.append(item))

    def _create_ring_fill_item(self, points, atom_ids):
        return {"kind": "ring", "points": [(point.x(), point.y()) for point in points], "atom_ids": list(atom_ids)}

    def _benzene_ring_points(self, center, attach_atom_id=None, attach_bond_id=None):
        return (
            [QPointF(center.x() + i * 10.0, center.y()) for i in range(6)],
            [],
        )

    def _regular_ring_points_for_atom(self, n: int, atom_id: int):
        return (
            [QPointF(float(i), float(i + 1)) for i in range(n)],
            [(atom_id, 1.0, 2.0)],
        )

    def _regular_ring_points_for_bond(self, n: int, bond_id: int, midpoint: QPointF):
        return (
            [QPointF(midpoint.x() + i, midpoint.y() - i) for i in range(n)],
            [(bond_id, midpoint.x(), midpoint.y())],
        )

    def _cyclohexane_chair_points(self, center: QPointF):
        return [
            QPointF(center.x() + 1.0, center.y() + 2.0),
            QPointF(center.x() + 3.0, center.y() - 4.0),
        ]

    def _template_points_for_bond(self, points_local, bond_id: int, midpoint: QPointF):
        return (
            [QPointF(point.x() + midpoint.x(), point.y() + midpoint.y()) for point in points_local],
            [(bond_id, midpoint.x(), midpoint.y())],
        )


class StructureBuildServiceTest(unittest.TestCase):
    def test_run_recorded_build_captures_history_snapshot_and_added_scene_items(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)
        canvas.model.add_atom("C", 1.0, 2.0)
        canvas.model.add_bond(0, 0, 1)

        added_scene_items = service.run_recorded_build(lambda: [{"kind": "note"}])

        self.assertEqual(added_scene_items, [{"kind": "note"}])
        self.assertIsNone(canvas.last_smiles_input)
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 1,
                    "before_bond_count": 1,
                    "before_smiles_input": "before",
                    "added_scene_items": [{"kind": "note"}],
                }
            ],
        )

    def test_template_helpers_compute_centered_inputs(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)
        service.add_ring_from_points = Mock()

        service.add_regular_ring_template(6)
        service.add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])

        self.assertEqual(canvas.regular_ring_radius_calls, [6, 5])
        self.assertEqual(
            canvas.ring_points_calls,
            [
                (6, (50.0, 60.0), 18.0),
                (5, (50.0, 60.0), 17.0),
            ],
        )
        self.assertEqual(service.add_ring_from_points.call_count, 2)
        self.assertEqual(service.add_ring_from_points.call_args_list[1].kwargs["elements"], ["O", "C", "C", "C", "C"])

    def test_fused_benzene_and_crown_helpers_reuse_ring_builder(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)
        service.add_ring_from_points = Mock()

        service.add_fused_benzenes(2)
        first_merge = service.add_ring_from_points.call_args_list[0].kwargs["merge"]
        second_merge = service.add_ring_from_points.call_args_list[1].kwargs["merge"]
        self.assertIs(first_merge, second_merge)
        self.assertEqual(len(service.add_ring_from_points.call_args_list), 2)

        service.add_ring_from_points.reset_mock()
        service.add_crown_ether(12, 4)
        self.assertEqual(
            service.add_ring_from_points.call_args.kwargs["elements"],
            ["O", "C", "C", "O", "C", "C", "O", "C", "C", "O", "C", "C"],
        )

    def test_add_atom_with_merge_reuses_close_points(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)
        merge = [(7, 10.0, 10.0)]

        existing_id = service.add_atom_with_merge(QPointF(11.0, 11.0), "C", merge)
        created_id = service.add_atom_with_merge(QPointF(40.0, 40.0), "N", merge)

        self.assertEqual(existing_id, 7)
        self.assertEqual(created_id, 0)
        self.assertEqual(merge[-1], (0, 40.0, 40.0))

    def test_add_ring_from_points_builds_bonds_and_labels_hetero_atoms(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas._atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )

        atom_ids = StructureBuildService(canvas).add_ring_from_points(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 8.0)],
            elements=["C", "N", "O"],
        )

        self.assertEqual(atom_ids, [0, 1, 2])
        self.assertEqual(len(canvas.model.bonds), 3)
        self.assertEqual(canvas.added_graphics, [0, 1, 2])
        self.assertEqual(
            service_calls,
            [
                (1, "N", {"clear_smiles": True, "record": False, "allow_merge": True, "show_carbon": False}),
                (2, "O", {"clear_smiles": True, "record": False, "allow_merge": True, "show_carbon": False}),
            ],
        )

    def test_add_linear_chain_and_render_model_cover_wrapper_fallback_paths(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)

        atom_ids = service.add_linear_chain(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(20.0, 0.0)],
            ["C", "N", "C"],
            [1, 2],
        )

        self.assertEqual(atom_ids, [0, 1, 2])
        self.assertEqual(canvas.added_graphics, [0, 1])
        self.assertEqual(canvas.wrapper_label_calls, [(1, "N", True, False, True, False)])

        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0, explicit_label=False),
                1: Atom("C", 10.0, 0.0, explicit_label=True),
                2: Atom("Cl", 20.0, 0.0, explicit_label=False),
            },
            bonds=[Bond(0, 1, 1), None, Bond(1, 2, 1)],
        )
        canvas.added_graphics.clear()
        canvas.carbon_dots.clear()
        canvas.wrapper_label_calls.clear()

        service.render_model()

        self.assertEqual(canvas.added_graphics, [0, 2])
        self.assertEqual(canvas.carbon_dots, [0])
        self.assertEqual(
            canvas.wrapper_label_calls,
            [
                (1, "C", False, False, True, True),
                (2, "Cl", False, False, True, False),
            ],
        )

    def test_add_bond_between_points_creates_or_updates_bonds_with_history(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)

        result = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2)

        self.assertEqual(result, (0, 1))
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual((canvas.model.bonds[0].style, canvas.model.bonds[0].order), ("double", 2))
        self.assertEqual(canvas.added_graphics, [0])
        self.assertEqual(canvas.redrawn_connected, [(0, 0), (1, 0)])
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

        canvas.record_calls.clear()
        canvas.find_atom_near = Mock(side_effect=[0, 1])
        updated = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "wedge", 1)

        self.assertEqual(updated, (0, 1))
        self.assertEqual(canvas.redrawn_bonds, [0])
        self.assertEqual(canvas.redrawn_connected[-2:], [(0, 0), (1, 0)])
        self.assertEqual(len(canvas.recorded_bond_updates), 1)
        self.assertEqual(canvas.record_calls, [])

    def test_add_benzene_ring_builds_ring_item_and_records_scene_item(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)

        ring_item = service.add_benzene_ring(QPointF(5.0, 6.0))

        self.assertEqual(ring_item, canvas.ring_items[0])
        self.assertEqual(canvas.scene_items, [ring_item])
        self.assertEqual(len(canvas.model.bonds), 6)
        self.assertEqual(canvas.added_graphics, [0, 1, 2, 3, 4, 5])
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [ring_item],
                }
            ],
        )

    def test_benzene_ring_points_prefers_bond_then_atom_then_free_geometry(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        canvas._regular_ring_points_for_bond = Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        canvas._regular_ring_points_for_atom = Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        service = StructureBuildService(canvas)

        bond_result = service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0)
        atom_result = service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=9)

        self.assertEqual(bond_result, ([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(atom_result, ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        canvas._regular_ring_points_for_bond.assert_called_once_with(6, 0, QPointF(5.0, 6.0))
        canvas._regular_ring_points_for_atom.assert_called_once_with(6, 1)

    def test_benzene_ring_points_treats_failed_valid_bond_geometry_as_terminal(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        canvas._regular_ring_points_for_bond = Mock(return_value=None)
        canvas._regular_ring_points_for_atom = Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        service = StructureBuildService(canvas)

        self.assertIsNone(service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0))
        canvas._regular_ring_points_for_atom.assert_not_called()

    def test_benzene_ring_points_blocks_free_ring_inside_existing_ring_and_uses_pure_fallback(self) -> None:
        canvas = _FakeCanvas()
        canvas.ring_items = [_FakeRingItem(True)]
        service = StructureBuildService(canvas)

        self.assertIsNone(service.benzene_ring_points(QPointF(5.0, 6.0)))

        canvas.ring_items = [_FakeRingItem(False)]
        with mock.patch(
            "ui.structure_build_service.compute_free_benzene_ring_points",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as free_ring:
            result = service.benzene_ring_points(QPointF(7.0, 8.0))

        self.assertEqual(result, ([QPointF(1.0, 2.0), QPointF(3.0, 4.0)], []))
        free_ring.assert_called_once_with((7.0, 8.0), bond_length=20.0)

    def test_sprout_bond_and_benzene_helpers_delegate_with_expected_points(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={3: Atom("C", 4.0, 5.0)}, bonds=[])
        service = StructureBuildService(canvas)
        service.add_bond_between_points = Mock(return_value=(3, 4))
        service.add_benzene_ring = Mock(return_value="ring")

        result = service.sprout_bond_from_atom(3, style="double", order=2, cyclic=True)
        ring = service.sprout_benzene_from_atom(3)

        self.assertEqual(result, (3, 4))
        self.assertEqual(ring, "ring")
        service.add_bond_between_points.assert_called_once_with(
            QPointF(4.0, 5.0),
            QPointF(20.0, 0.0),
            "double",
            2,
        )
        service.add_benzene_ring.assert_called_once_with(QPointF(4.0, 5.0), attach_atom_id=3)

    def test_sprout_acetyl_from_atom_builds_three_bonds_and_labels_oxygen(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("O", 30.0, 0.0),
                3: Atom("C", 40.0, 0.0),
            },
            bonds=[],
        )
        service = StructureBuildService(canvas)
        service.add_bond_between_points = Mock(side_effect=[(0, 1), (1, 2), (1, 3)])

        service.sprout_acetyl_from_atom(0)

        self.assertEqual(
            service.add_bond_between_points.call_args_list,
            [
                mock.call(QPointF(0.0, 0.0), QPointF(20.0, 0.0), "single", 1),
                mock.call(QPointF(20.0, 0.0), QPointF(30.0, 0.0), "double", 2),
                mock.call(QPointF(20.0, 0.0), QPointF(30.0, 0.0), "single", 1),
            ],
        )
        self.assertEqual(canvas.wrapper_label_calls, [(2, "O", True, True, True, True)])

    def test_fuse_benzene_to_bond_uses_midpoint_and_skips_missing_geometry(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 4.0),
            },
            bonds=[Bond(0, 1, 1), None],
        )
        service = StructureBuildService(canvas)
        service.add_benzene_ring = Mock(return_value="ring")

        self.assertEqual(service.fuse_benzene_to_bond(0), "ring")
        self.assertIsNone(service.fuse_benzene_to_bond(1))
        service.add_benzene_ring.assert_called_once_with(QPointF(5.0, 2.0), attach_bond_id=0)

    def test_ring_growth_helpers_record_only_when_geometry_resolves(self) -> None:
        canvas = _FakeCanvas()
        service = StructureBuildService(canvas)
        service.add_ring_from_points = Mock()
        canvas._regular_ring_points_for_atom = Mock(return_value=None)

        service.sprout_regular_ring_from_atom(7, 6)

        self.assertEqual(canvas.record_calls, [])
        self.assertIsNone(canvas.last_smiles_input)
        service.add_ring_from_points.assert_not_called()

        canvas.last_smiles_input = "before"
        canvas._regular_ring_points_for_atom = Mock(
            return_value=([QPointF(0.0, 0.0), QPointF(1.0, 1.0)], [(7, 1.0, 2.0)])
        )
        service.sprout_regular_ring_from_atom(7, 6)

        service.add_ring_from_points.assert_called_once_with(
            [QPointF(0.0, 0.0), QPointF(1.0, 1.0)],
            merge=[(7, 1.0, 2.0)],
        )
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

    def test_bond_fuse_helpers_build_templates_and_record_history(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(0, 1, 1)],
        )
        service = StructureBuildService(canvas)
        service.add_ring_from_points = Mock()
        canvas._regular_ring_points_for_bond = Mock(
            return_value=([QPointF(5.0, 0.0), QPointF(6.0, -1.0)], [(0, 5.0, 0.0)])
        )
        canvas._template_points_for_bond = Mock(
            return_value=([QPointF(6.0, 2.0), QPointF(8.0, -4.0)], [(0, 5.0, 0.0)])
        )
        canvas._cyclohexane_chair_points = Mock(return_value=[QPointF(1.0, 2.0), QPointF(3.0, -4.0)])

        service.fuse_regular_ring_to_bond(0, 5)
        service.fuse_chair_to_bond(0, mirrored=True)

        first_midpoint = canvas._regular_ring_points_for_bond.call_args.args[2]
        self.assertEqual((first_midpoint.x(), first_midpoint.y()), (5.0, 0.0))
        chair_points = canvas._template_points_for_bond.call_args.args[0]
        self.assertEqual([(point.x(), point.y()) for point in chair_points], [(1.0, -2.0), (3.0, 4.0)])
        second_midpoint = canvas._template_points_for_bond.call_args.args[2]
        self.assertEqual((second_midpoint.x(), second_midpoint.y()), (5.0, 0.0))
        self.assertEqual(
            service.add_ring_from_points.call_args_list,
            [
                mock.call([QPointF(5.0, 0.0), QPointF(6.0, -1.0)], merge=[(0, 5.0, 0.0)]),
                mock.call([QPointF(6.0, 2.0), QPointF(8.0, -4.0)], merge=[(0, 5.0, 0.0)]),
            ],
        )
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": "before",
                },
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": None,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
