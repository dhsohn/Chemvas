import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

from core.model import Atom, Bond, MoleculeModel
from PyQt6.QtCore import QPointF
from ui.canvas_scene_items_state import ring_items_for, set_scene_item_collection_for
from ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
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
        set_last_smiles_input_for(self, "before")
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
        set_scene_item_collection_for(self, "ring_items", [])
        self.find_atom_near = Mock(side_effect=AssertionError("canvas facade should not be used"))
        self.hit_testing_find_atom_near = Mock(return_value=None)
        self.bond_renderer = SimpleNamespace(add_bond_graphics=self._add_bond_graphics)
        self.services = SimpleNamespace(
            hit_testing_service=SimpleNamespace(find_atom_near=self.hit_testing_find_atom_near),
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                ensure_carbon_dot=self.ensure_carbon_dot,
            ),
            canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
            canvas_bond_mutation_service=SimpleNamespace(add_bond=self.add_bond),
            canvas_history_recording_service=SimpleNamespace(
                record_additions=self._record_additions,
                record_bond_update=self._record_bond_update,
            ),
            scene_item_controller=SimpleNamespace(attach_scene_item=self.attach_scene_item),
            canvas_graph_service=SimpleNamespace(
                bond_id_between=self.bond_id_between,
                bond_exists=self.bond_exists,
            ),
            move_controller=SimpleNamespace(
                redraw_bond=self.redraw_bond,
                redraw_connected_bonds=self.redraw_connected_bonds,
            ),
            canvas_ring_fill_scene_service=SimpleNamespace(create_ring_fill_item=self._create_ring_fill_item),
        )

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self.viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def add_atom(self, element: str, x: float, y: float) -> int:
        return self.model.add_atom(element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

    def bond_id_between(self, a_id: int, b_id: int) -> int | None:
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return bond_id
        return None

    def bond_exists(self, a_id: int, b_id: int) -> bool:
        return self.bond_id_between(a_id, b_id) is not None

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {"a": bond.a, "b": bond.b, "order": bond.order, "style": bond.style}

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.added_graphics.append(bond_id)

    def redraw_bond(self, bond_id: int) -> None:
        self.redrawn_bonds.append(bond_id)

    def redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        self.redrawn_connected.append((atom_id, skip_bond_id))

    def ensure_carbon_dot(self, atom_id: int) -> None:
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

    @property
    def ring_items(self):
        return ring_items_for(self)

    @ring_items.setter
    def ring_items(self, value) -> None:
        set_scene_item_collection_for(self, "ring_items", value)

    def attach_scene_item(self, item) -> None:
        self.scene_items.append(item)
        if isinstance(item, dict) and item.get("kind") == "ring":
            self.ring_items.append(item)

    def _create_ring_fill_item(self, points, atom_ids):
        return {"kind": "ring", "points": [(point.x(), point.y()) for point in points], "atom_ids": list(atom_ids)}

    def _benzene_ring_points(self, center, attach_atom_id=None, attach_bond_id=None):
        return (
            [QPointF(center.x() + i * 10.0, center.y()) for i in range(6)],
            [],
        )


def _service_for(canvas: _FakeCanvas) -> StructureBuildService:
    return StructureBuildService(
        canvas,
        hit_testing_service=canvas.services.hit_testing_service,
        move_controller=canvas.services.move_controller,
        graph_service=canvas.services.canvas_graph_service,
    )


class StructureBuildServiceTest(unittest.TestCase):
    def test_run_recorded_build_captures_history_snapshot_and_added_scene_items(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        canvas.model.add_atom("C", 1.0, 2.0)
        canvas.model.add_atom("C", 3.0, 4.0)
        canvas.model.add_bond(0, 1, 1)

        added_scene_items = service.run_recorded_build(lambda: [{"kind": "note"}])

        self.assertEqual(added_scene_items, [{"kind": "note"}])
        self.assertIsNone(last_smiles_input_for(canvas))
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": "before",
                    "added_scene_items": [{"kind": "note"}],
                }
            ],
        )

    def test_recorded_build_helpers_preserve_explicit_smiles_input_and_skip_failed_actions(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        service.run_recorded_build(lambda: [], before_smiles_input="explicit")

        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "explicit",
                    "added_scene_items": [],
                }
            ],
        )

        canvas.record_calls.clear()
        set_last_smiles_input_for(canvas, "current")
        self.assertEqual(service.run_recorded_build(lambda: None), [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "current")

        def failed_build() -> None:
            service.committer.add_atom("C", 1.0, 2.0)
            return None

        self.assertEqual(service.run_recorded_build(failed_build), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.record_calls, [])

        self.assertFalse(service._run_recorded_additions_action(lambda: False, before_smiles_input="kept"))
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "kept")

    def test_template_helpers_compute_centered_inputs(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()
        regular_ring_radius_calls: list[int] = []
        ring_points_calls: list[tuple[int, tuple[float, float], float | None]] = []

        def regular_ring_radius(n: int) -> float:
            regular_ring_radius_calls.append(n)
            return 12.0 + n

        def ring_points(center: QPointF, n: int, radius: float | None = None):
            ring_points_calls.append((n, (center.x(), center.y()), radius))
            return [QPointF(center.x() + i, center.y() - i) for i in range(n)]

        service.regular_ring_radius = Mock(side_effect=regular_ring_radius)
        service.ring_points = Mock(side_effect=ring_points)

        service.template_builder.add_regular_ring_template(6)
        service.template_builder.add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])

        self.assertEqual(regular_ring_radius_calls, [6, 5])
        self.assertEqual(
            ring_points_calls,
            [
                (6, (50.0, 60.0), 18.0),
                (5, (50.0, 60.0), 17.0),
            ],
        )
        self.assertEqual(service.add_ring_from_points.call_count, 2)
        self.assertEqual(service.add_ring_from_points.call_args_list[1].kwargs["elements"], ["O", "C", "C", "C", "C"])

    def test_fused_benzene_and_crown_helpers_reuse_ring_builder(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()

        service.template_builder.add_fused_benzenes(2)
        first_merge = service.add_ring_from_points.call_args_list[0].kwargs["merge"]
        second_merge = service.add_ring_from_points.call_args_list[1].kwargs["merge"]
        self.assertIs(first_merge, second_merge)
        self.assertEqual(len(service.add_ring_from_points.call_args_list), 2)

        service.add_ring_from_points.reset_mock()
        service.template_builder.add_crown_ether(12, 4)
        self.assertEqual(
            service.add_ring_from_points.call_args.kwargs["elements"],
            ["O", "C", "C", "O", "C", "C", "O", "C", "C", "O", "C", "C"],
        )

    def test_cyclohexane_builders_delegate_to_ring_builder_and_record_history(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        chair_points = [QPointF(float(index), float(index + 1)) for index in range(6)]
        boat_points = [QPointF(float(index), float(-index)) for index in range(6)]
        service.cyclohexane_chair_points = Mock(return_value=chair_points)
        service.cyclohexane_boat_points = Mock(return_value=boat_points)
        service.add_ring_from_points = Mock()

        service.template_builder.add_cyclohexane_chair()

        service.cyclohexane_chair_points.assert_called_once_with(QPointF(50.0, 60.0))
        self.assertEqual(service.add_ring_from_points.call_args.args[0], chair_points)
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [],
                }
            ],
        )

        set_last_smiles_input_for(canvas, "before")
        canvas.record_calls.clear()
        service.add_ring_from_points.reset_mock()

        service.template_builder.add_cyclohexane_boat()

        service.cyclohexane_boat_points.assert_called_once_with(QPointF(50.0, 60.0))
        self.assertEqual(service.add_ring_from_points.call_args.args[0], boat_points)
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [],
                }
            ],
        )

    def test_fused_heterocycle_builders_use_expected_offsets_and_merge_contract(self) -> None:
        cases = (
            ("add_indole", 5, ["N", "C", "C", "C", "C"], (72.0, 72.0)),
            ("add_quinoline", 6, ["N", "C", "C", "C", "C", "C"], (80.0, 60.0)),
            ("add_isoquinoline", 6, ["C", "C", "C", "C", "N", "C"], (80.0, 60.0)),
            ("add_benzimidazole", 5, ["N", "C", "N", "C", "C"], (72.0, 72.0)),
        )

        for method_name, ring_size, elements, expected_second_center in cases:
            with self.subTest(method=method_name):
                canvas = _FakeCanvas()
                service = _service_for(canvas)
                service.add_ring_from_points = Mock()
                ring_points_calls: list[tuple[int, tuple[float, float], float | None]] = []

                def ring_points(center: QPointF, n: int, radius: float | None = None, *, calls=ring_points_calls):
                    calls.append((n, (center.x(), center.y()), radius))
                    return [QPointF(center.x() + i, center.y() - i) for i in range(n)]

                service.ring_points = Mock(side_effect=ring_points)

                getattr(service.template_builder, method_name)()

                self.assertEqual(
                    ring_points_calls,
                    [
                        (6, (50.0, 60.0), None),
                        (ring_size, expected_second_center, None),
                    ],
                )
                first_merge = service.add_ring_from_points.call_args_list[0].kwargs["merge"]
                second_merge = service.add_ring_from_points.call_args_list[1].kwargs["merge"]
                self.assertIs(first_merge, second_merge)
                self.assertEqual(service.add_ring_from_points.call_args_list[1].kwargs["elements"], elements)
                self.assertEqual(
                    canvas.record_calls,
                    [
                        {
                            "before_next_atom_id": 0,
                            "before_bond_count": 0,
                            "before_smiles_input": "before",
                            "added_scene_items": [],
                        }
                    ],
                )

    def test_add_atom_with_merge_reuses_close_points(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        merge = [(7, 10.0, 10.0)]

        existing_id = service.add_atom_with_merge(QPointF(11.0, 11.0), "C", merge)
        created_id = service.add_atom_with_merge(QPointF(40.0, 40.0), "N", merge)

        self.assertEqual(existing_id, 7)
        self.assertEqual(created_id, 0)
        self.assertEqual(merge[-1], (0, 40.0, 40.0))

    def test_add_ring_from_points_builds_bonds_and_labels_hetero_atoms(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas.services.atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )

        atom_ids = _service_for(canvas).add_ring_from_points(
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

    def test_add_linear_chain_and_render_model_use_atom_label_service(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

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
        service = _service_for(canvas)

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
        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.hit_testing_service.find_atom_near = canvas.hit_testing_find_atom_near
        updated = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "wedge", 1)

        self.assertEqual(updated, (0, 1))
        self.assertEqual(canvas.redrawn_bonds, [0])
        self.assertEqual(canvas.redrawn_connected[-2:], [(0, 0), (1, 0)])
        self.assertEqual(len(canvas.recorded_bond_updates), 1)
        self.assertEqual(canvas.record_calls, [])

    def test_add_bond_between_points_uses_hit_testing_service_for_snap_lookup(self) -> None:
        canvas = _FakeCanvas()
        hit_testing_service = SimpleNamespace(find_atom_near=Mock(side_effect=[None, None]))
        canvas.services.hit_testing_service = hit_testing_service
        canvas.find_atom_near = Mock(side_effect=AssertionError("canvas facade should not be used"))
        service = _service_for(canvas)

        result = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1)

        self.assertEqual(result, (0, 1))
        self.assertEqual(
            hit_testing_service.find_atom_near.call_args_list,
            [mock.call(0.0, 0.0, 2.0), mock.call(10.0, 0.0, 2.0)],
        )
        canvas.find_atom_near.assert_not_called()

    def test_add_bond_between_points_uses_injected_hit_testing_over_canvas_aliases(self) -> None:
        canvas = _FakeCanvas()
        hit_testing_service = SimpleNamespace(find_atom_near=Mock(side_effect=[None, None]))
        registry_hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(side_effect=AssertionError("registry service should not be used"))
        )
        direct_alias_hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(side_effect=AssertionError("direct alias should not be used"))
        )
        canvas.services.hit_testing_service = registry_hit_testing_service
        canvas.hit_testing = direct_alias_hit_testing_service
        canvas.find_atom_near = Mock(side_effect=AssertionError("canvas facade should not be used"))
        service = StructureBuildService(
            canvas,
            hit_testing_service=hit_testing_service,
            move_controller=canvas.services.move_controller,
            graph_service=canvas.services.canvas_graph_service,
        )

        result = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1)

        self.assertEqual(result, (0, 1))
        self.assertEqual(
            hit_testing_service.find_atom_near.call_args_list,
            [mock.call(0.0, 0.0, 2.0), mock.call(10.0, 0.0, 2.0)],
        )
        registry_hit_testing_service.find_atom_near.assert_not_called()
        direct_alias_hit_testing_service.find_atom_near.assert_not_called()
        canvas.find_atom_near.assert_not_called()

    def test_add_bond_between_points_ignores_short_drag_before_mutation(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        result = service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(1.5, 1.0), "single", 1)

        self.assertIsNone(result)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.record_calls, [])
        canvas.hit_testing_find_atom_near.assert_not_called()

    def test_add_benzene_ring_builds_ring_item_and_records_scene_item(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

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
        service = _service_for(canvas)
        service.regular_ring_points_for_bond = Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        service.regular_ring_points_for_atom = Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))

        bond_result = service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0)
        atom_result = service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=9)

        self.assertEqual(bond_result, ([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(atom_result, ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        service.regular_ring_points_for_bond.assert_called_once_with(6, 0, QPointF(5.0, 6.0))
        service.regular_ring_points_for_atom.assert_called_once_with(6, 1)

    def test_benzene_ring_points_treats_failed_valid_bond_geometry_as_terminal(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        service = _service_for(canvas)
        service.regular_ring_points_for_bond = Mock(return_value=None)
        service.regular_ring_points_for_atom = Mock(return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))

        self.assertIsNone(service.benzene_ring_points(QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0))
        service.regular_ring_points_for_atom.assert_not_called()

    def test_benzene_ring_points_blocks_free_ring_inside_existing_ring_and_uses_pure_fallback(self) -> None:
        canvas = _FakeCanvas()
        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(True)])
        service = _service_for(canvas)

        self.assertIsNone(service.benzene_ring_points(QPointF(5.0, 6.0)))

        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(False)])
        with mock.patch(
            "ui.structure_benzene_build_service.compute_free_benzene_ring_points",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as free_ring:
            result = service.benzene_ring_points(QPointF(7.0, 8.0))

        self.assertEqual(result, ([QPointF(1.0, 2.0), QPointF(3.0, 4.0)], []))
        free_ring.assert_called_once_with((7.0, 8.0), bond_length=20.0)

    def test_sprout_bond_and_benzene_helpers_delegate_with_expected_points(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={3: Atom("C", 4.0, 5.0)}, bonds=[])
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
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

    def test_sprout_and_fuse_helpers_return_early_when_geometry_resolution_fails(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(0, 1, 1)],
        )
        service = _service_for(canvas)
        service.default_bond_endpoint = Mock(return_value=QPointF(30.0, 0.0))
        service.add_bond_between_points = Mock()
        service.add_ring_from_points = Mock()

        service.sprout_bond_endpoint = Mock(return_value=None)
        self.assertIsNone(service.sprout_bond_from_atom(0, style="single", order=1))
        service.sprout_acetyl_from_atom(0)
        service.add_bond_between_points.assert_not_called()
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

        set_last_smiles_input_for(canvas, "before")
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.default_bond_endpoint = Mock(return_value=None)
        service.sprout_acetyl_from_atom(0)
        service.add_bond_between_points.assert_not_called()
        self.assertEqual(sorted(canvas.model.atoms), [0, 1])
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

        service.regular_ring_points_for_bond = Mock(return_value=None)
        service.template_points_for_bond = Mock(return_value=None)
        service.fuse_regular_ring_to_bond(99, 6)
        service.fuse_regular_ring_to_bond(0, 6)
        service.fuse_chair_to_bond(99)
        service.fuse_chair_to_bond(0)
        service.add_ring_from_points.assert_not_called()

    def test_sprout_acetyl_from_atom_builds_three_bonds_and_labels_oxygen(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
            },
            bonds=[],
        )
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.default_bond_endpoint = Mock(side_effect=[QPointF(20.0, 10.0), QPointF(20.0, -10.0)])
        service.add_bond_between_points = Mock()

        service.sprout_acetyl_from_atom(0)

        service.add_bond_between_points.assert_not_called()
        self.assertEqual(
            {atom_id: (atom.element, atom.x, atom.y) for atom_id, atom in canvas.model.atoms.items()},
            {
                0: ("C", 0.0, 0.0),
                1: ("C", 20.0, 0.0),
                2: ("O", 20.0, 10.0),
                3: ("C", 20.0, -10.0),
            },
        )
        self.assertEqual(
            [(bond.a, bond.b, bond.order, bond.style) for bond in canvas.model.bonds if bond is not None],
            [
                (0, 1, 1, "single"),
                (1, 2, 2, "double"),
                (1, 3, 1, "single"),
            ],
        )
        self.assertEqual(canvas.added_graphics, [0, 1, 2])
        self.assertEqual(canvas.wrapper_label_calls, [(2, "O", True, False, True, True)])
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 1,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

    def test_fuse_benzene_to_bond_uses_midpoint_and_skips_missing_geometry(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 4.0),
            },
            bonds=[Bond(0, 1, 1), None],
        )
        service = _service_for(canvas)
        service.add_benzene_ring = Mock(return_value="ring")

        self.assertEqual(service.fuse_benzene_to_bond(0), "ring")
        self.assertIsNone(service.fuse_benzene_to_bond(1))
        service.add_benzene_ring.assert_called_once_with(QPointF(5.0, 2.0), attach_bond_id=0)

    def test_add_bond_between_points_returns_none_for_collapsed_or_invalid_paths(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 10.0, 0.0)}, bonds=[])
        service = _service_for(canvas)

        self.assertIsNone(service.add_bond_between_points(QPointF(1.0, 2.0), QPointF(1.0, 2.0), "single", 1))

        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 0])
        canvas.services.hit_testing_service.find_atom_near = canvas.hit_testing_find_atom_near
        self.assertIsNone(service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1))

        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.hit_testing_service.find_atom_near = canvas.hit_testing_find_atom_near
        canvas.model.bonds = [None]
        canvas.services.canvas_graph_service.bond_id_between = Mock(return_value=0)
        self.assertIsNone(service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1))
        self.assertEqual(last_smiles_input_for(canvas), "before")
        self.assertEqual(canvas.record_calls, [])

        failed_canvas = _FakeCanvas()
        failed_service = _service_for(failed_canvas)
        failed_canvas.services.canvas_bond_mutation_service.add_bond = Mock(return_value=0)
        self.assertIsNone(
            failed_service.add_bond_between_points(QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1)
        )
        self.assertEqual(failed_canvas.model.atoms, {})
        self.assertEqual(failed_canvas.model.bonds, [])
        self.assertEqual(failed_canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(failed_canvas), "before")

    def test_ring_growth_helpers_record_only_when_geometry_resolves(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()
        service.regular_ring_points_for_atom = Mock(return_value=None)

        service.sprout_regular_ring_from_atom(7, 6)

        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")
        service.add_ring_from_points.assert_not_called()

        set_last_smiles_input_for(canvas, "before")
        service.regular_ring_points_for_atom = Mock(
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
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()
        service.regular_ring_points_for_bond = Mock(
            return_value=([QPointF(5.0, 0.0), QPointF(6.0, -1.0)], [(0, 5.0, 0.0)])
        )
        service.template_points_for_bond = Mock(
            return_value=([QPointF(6.0, 2.0), QPointF(8.0, -4.0)], [(0, 5.0, 0.0)])
        )
        service.cyclohexane_chair_points = Mock(return_value=[QPointF(1.0, 2.0), QPointF(3.0, -4.0)])

        service.fuse_regular_ring_to_bond(0, 5)
        service.fuse_chair_to_bond(0, mirrored=True)

        first_midpoint = service.regular_ring_points_for_bond.call_args.args[2]
        self.assertEqual((first_midpoint.x(), first_midpoint.y()), (5.0, 0.0))
        chair_points = service.template_points_for_bond.call_args.args[0]
        self.assertEqual([(point.x(), point.y()) for point in chair_points], [(1.0, -2.0), (3.0, 4.0)])
        second_midpoint = service.template_points_for_bond.call_args.args[2]
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

    def test_add_benzene_ring_handles_failed_geometry_and_preexisting_ring_bonds(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        service.benzene_ring_points = Mock(return_value=None)
        self.assertIsNone(service.add_benzene_ring(QPointF(5.0, 6.0)))
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [],
                }
            ],
        )

        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={index: Atom("C", float(index), 0.0) for index in range(6)},
            bonds=[Bond(0, 1, 1)],
        )
        service = _service_for(canvas)
        points = [QPointF(float(index), float(index % 2)) for index in range(6)]
        service.benzene_ring_points = Mock(return_value=(points, []))
        service.add_atom_with_merge = Mock(side_effect=list(range(6)))

        ring_item = service.add_benzene_ring(QPointF(1.0, 2.0))

        self.assertIsNotNone(ring_item)
        assert ring_item is not None
        self.assertEqual(len(canvas.model.bonds), 6)
        self.assertEqual(canvas.added_graphics, [1, 2, 3, 4, 5])
        self.assertEqual(canvas.scene_items, [ring_item])

    def test_ring_and_chain_fragment_builders_record_expected_counts(self) -> None:
        cases = (
            ("add_phenyl", 7, 7, 7),
            ("add_benzyl", 8, 8, 8),
            ("add_vinyl", 2, 1, 1),
            ("add_allyl", 3, 2, 2),
            ("add_carboxyl", 4, 2, 2),
            ("add_nitro", 4, 2, 2),
            ("add_sulfonyl", 4, 2, 2),
            ("add_carbonyl", 2, 1, 1),
            ("add_tbu", 6, 3, 3),
            ("add_ipr", 4, 2, 2),
            ("add_me", 1, 0, 0),
            ("add_et", 2, 1, 1),
        )

        for method_name, atom_count, bond_count, graphic_count in cases:
            with self.subTest(method=method_name):
                canvas = _FakeCanvas()
                service = _service_for(canvas)
                if method_name in {"add_phenyl", "add_benzyl"}:
                    service.ring_points = Mock(
                        return_value=[QPointF(50.0 + index * 10.0, 60.0) for index in range(6)]
                    )

                getattr(service.template_builder, method_name)()

                self.assertEqual(len(canvas.model.atoms), atom_count)
                self.assertEqual(len(canvas.model.bonds), bond_count)
                self.assertEqual(len(canvas.added_graphics), graphic_count)
                self.assertEqual(
                    canvas.record_calls,
                    [
                        {
                            "before_next_atom_id": 0,
                            "before_bond_count": 0,
                            "before_smiles_input": "before",
                            "added_scene_items": [],
                        }
                    ],
                )

    def test_add_peptide_2_adds_carbonyl_oxygens_and_labels_them(self) -> None:
        canvas = _FakeCanvas()
        oxygen_label_service = Mock()
        canvas.services.atom_label_service = SimpleNamespace(add_or_update_atom_label=oxygen_label_service)
        service = _service_for(canvas)

        service.template_builder.add_peptide_2()

        oxygen_labels = [call.args[:2] for call in oxygen_label_service.call_args_list if call.args[1] == "O"]
        self.assertEqual(len(canvas.model.atoms), 8)
        self.assertEqual(len(canvas.model.bonds), 7)
        self.assertEqual(canvas.added_graphics, [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(oxygen_labels, [(6, "O"), (7, "O")])
        self.assertTrue(all(call.kwargs == {"record": False} for call in oxygen_label_service.call_args_list[-2:]))
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
