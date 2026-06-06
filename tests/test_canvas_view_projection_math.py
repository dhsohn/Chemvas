import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import (
        CompositeCommand,
        SetAtomPositionsCommand,
        SetRingPolygonsCommand,
        UpdateBondLengthCommand,
    )
    from core.model import Atom, Bond
    from ui.atom_coords_access import (
        atom_coords_3d_for,
        current_atom_coords_3d_for,
        set_atom_coords_3d_for,
    )
    from ui.bond_graphics_access import (
        add_bond_graphics_for,
        apply_color_to_bond_item_for,
        bond_offset_unit_3d_for,
        dotted_bond_path_for,
        draw_dotted_bond_for,
        draw_hash_bond_for,
        draw_parallel_bonds_for,
        draw_ring_double_bond_for,
        draw_wedge_bond_for,
        hash_segments_for,
        line_normal_components,
        line_normal_for,
        one_sided_bond_strip_for,
        orient_normal_toward_target,
        parallel_bond_segments_for,
        project_point_3d_for,
        ring_double_segments_for,
        strip_polygon_for,
        wedge_polygon_for,
    )
    from ui.bond_renderer import bond_renderer_for
    from ui.canvas_atom_graphics_state import set_atom_dots_for, set_atom_items_for
    from ui.canvas_geometry_controller import CanvasGeometryController
    from ui.canvas_graph_service import CanvasGraphService
    from ui.canvas_graph_state import CanvasGraphState
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_move_controller import CanvasMoveController
    from ui.canvas_rotation_state import CanvasRotationState
    from ui.canvas_scene_items_state import set_scene_item_collection_for
    from ui.selection_rotation_access import (
        apply_projected_atom_positions_for,
        atom_in_planar_system_for,
        average_bond_length_for_atoms_for,
        bond_ids_for_atom_ids_for,
        bond_ids_within_atom_ids_for,
        bond_is_planar_fragment_edge_for,
        center_for_coords_3d,
        flatten_planar_fragments_for,
        fragment_plane_normal_for,
        normalize_3d,
        planar_fragment_components_for,
        rotate_point_around_axis_for,
        rotation_scale_for_coords_for,
        unproject_scene_point_3d_for,
    )


class _FakeRingItem:
    def __init__(self, points) -> None:
        self._polygon = QPolygonF([QPointF(x, y) for x, y in points])

    def polygon(self):
        return QPolygonF(self._polygon)

    def setPolygon(self, polygon) -> None:
        self._polygon = QPolygonF(polygon)


class _FakeDot:
    def __init__(self) -> None:
        self.positions = []

    def setPos(self, x: float, y: float) -> None:
        self.positions.append((x, y))


class _FakeMark:
    def __init__(self, payload) -> None:
        self._payload = payload

    def data(self, key):
        if key == 1:
            return self._payload
        return None


class _FakePen:
    def __init__(self) -> None:
        self.color = None

    def setColor(self, color) -> None:
        self.color = color


class _FakeBrush:
    def __init__(self, style) -> None:
        self._style = style

    def style(self):
        return self._style


class _FakePenBrushItem:
    def __init__(self, brush_style) -> None:
        self._pen = _FakePen()
        self._brush = _FakeBrush(brush_style)
        self.pen_updates = []
        self.brush_updates = []

    def pen(self):
        return self._pen

    def setPen(self, pen) -> None:
        self.pen_updates.append(pen)

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


class _FakeBrushOnlyItem:
    def __init__(self, brush_style) -> None:
        self._brush = _FakeBrush(brush_style)
        self.brush_updates = []

    def brush(self):
        return self._brush

    def setBrush(self, color) -> None:
        self.brush_updates.append(color)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewProjectionMathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_set_bond_length_rescales_model_and_pushes_composite_command(self) -> None:
        ring_item = _FakeRingItem([(0.0, 0.0), (20.0, 0.0), (10.0, 10.0)])
        style = SimpleNamespace(bond_length_px=20.0)

        def _set_renderer_bond_length(length_px: float) -> None:
            style.bond_length_px = length_px

        pushed = []
        structure_build_service = SimpleNamespace(render_model=mock.Mock())
        view = SimpleNamespace(
            renderer=SimpleNamespace(style=style, set_bond_length=mock.Mock(side_effect=_set_renderer_bond_length)),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 20.0, 0.0),
                }
            ),
            bond_items={},
            atom_items={},
            atom_dots={},
            scene=lambda: SimpleNamespace(removeItem=mock.Mock()),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=pushed.append),
                structure_build_service=structure_build_service,
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
            ),
        )
        set_scene_item_collection_for(view, "ring_items", [ring_item])

        CanvasGeometryController(
            view,
            hit_testing_service=view.services.hit_testing_service,
            history_service=view.services.history_service,
        ).set_bond_length(30.0)

        self.assertEqual(style.bond_length_px, 30.0)
        self.assertAlmostEqual(view.model.atoms[1].x, -5.0)
        self.assertAlmostEqual(view.model.atoms[2].x, 25.0)
        scaled_points = [(point.x(), point.y()) for point in ring_item.polygon()]
        self.assertEqual(scaled_points, [(-5.0, 0.0), (25.0, 0.0), (10.0, 15.0)])
        structure_build_service.render_model.assert_called_once_with()
        self.assertEqual(len(pushed), 1)
        command = pushed[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(entry) for entry in command.commands], [UpdateBondLengthCommand, SetAtomPositionsCommand, SetRingPolygonsCommand])

    def test_set_bond_length_short_circuits_for_empty_model_or_same_scale(self) -> None:
        empty_style = SimpleNamespace(bond_length_px=20.0)
        empty_view = SimpleNamespace(
            renderer=SimpleNamespace(style=empty_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(empty_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={}),
            push_command=mock.Mock(),
            services=SimpleNamespace(),
        )
        set_scene_item_collection_for(empty_view, "ring_items", [])
        empty_view.services.history_service = SimpleNamespace(push=empty_view.push_command)

        CanvasGeometryController(empty_view).set_bond_length(30.0)

        empty_view.push_command.assert_not_called()

        same_style = SimpleNamespace(bond_length_px=24.0)
        same_view = SimpleNamespace(
            renderer=SimpleNamespace(style=same_style, set_bond_length=mock.Mock(side_effect=lambda value: setattr(same_style, "bond_length_px", value))),
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0)}),
            push_command=mock.Mock(),
            services=SimpleNamespace(),
        )
        set_scene_item_collection_for(same_view, "ring_items", [])
        same_view.services.history_service = SimpleNamespace(push=same_view.push_command)

        CanvasGeometryController(same_view).set_bond_length(24.0)

        same_view.push_command.assert_not_called()

    def test_normalize_project_unproject_and_current_coords_3d_helpers(self) -> None:
        self.assertIsNone(normalize_3d(0.0, 0.0, 0.0))
        self.assertEqual(normalize_3d(0.0, 3.0, 4.0), (0.0, 0.6, 0.8))

        no_projection_view = SimpleNamespace(rotation_state=CanvasRotationState())
        self.assertEqual(project_point_3d_for(no_projection_view, (2.0, 3.0, 4.0)), (2.0, 3.0))
        self.assertEqual(
            unproject_scene_point_3d_for(no_projection_view, QPointF(2.0, 3.0), 4.0),
            (2.0, 3.0, 4.0),
        )

        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            rotation_state=CanvasRotationState(
                projection_center_3d=(10.0, 20.0, 30.0),
                projection_anchor_2d=(100.0, 200.0),
            ),
        )

        scene_xy = project_point_3d_for(projected_view, (14.0, 26.0, 40.0))
        restored = unproject_scene_point_3d_for(projected_view, QPointF(*scene_xy), 40.0)
        self.assertAlmostEqual(restored[0], 14.0, places=6)
        self.assertAlmostEqual(restored[1], 26.0, places=6)
        self.assertAlmostEqual(restored[2], 40.0, places=6)

        projected_atom = project_point_3d_for(projected_view, (12.0, 13.0, 30.0))
        projected_view.model = SimpleNamespace(
            atoms={
                1: Atom("C", projected_atom[0], projected_atom[1]),
                2: Atom("N", 40.0, 50.0),
            }
        )
        set_atom_coords_3d_for(
            projected_view,
            {
                1: (12.0, 13.0, 30.0),
                2: (50.0, 60.0, 80.0),
            },
        )

        coords = current_atom_coords_3d_for(projected_view, 1)
        self.assertEqual(coords, (12.0, 13.0, 30.0))
        self.assertEqual(current_atom_coords_3d_for(projected_view, 2), (40.0, 50.0, 0.0))
        self.assertIsNone(current_atom_coords_3d_for(projected_view, 99))

        set_atom_coords_3d_for(projected_view, {})
        self.assertEqual(current_atom_coords_3d_for(projected_view, 1), projected_atom + (0.0,))

    def test_projection_and_center_helpers_cover_anchor_and_empty_fallbacks(self) -> None:
        projected_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            rotation_state=CanvasRotationState(projection_center_3d=(10.0, 20.0, 30.0)),
        )

        projected = project_point_3d_for(projected_view, (12.0, 24.0, 30.0))
        restored = unproject_scene_point_3d_for(projected_view, QPointF(*projected), 30.0)
        self.assertAlmostEqual(projected[0], 12.0)
        self.assertAlmostEqual(projected[1], 24.0)
        self.assertAlmostEqual(restored[0], 12.0)
        self.assertAlmostEqual(restored[1], 24.0)
        self.assertEqual(center_for_coords_3d(set(), {}), None)
        self.assertEqual(
            center_for_coords_3d({1, 2}, {3: (1.0, 2.0, 3.0)}),
            None,
        )

        explicit_projected = project_point_3d_for(
            projected_view,
            (12.0, 24.0, 31.0),
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        explicit_restored = unproject_scene_point_3d_for(
            projected_view,
            QPointF(*explicit_projected),
            31.0,
            center_3d=(10.0, 20.0, 30.0),
            anchor_2d=(0.0, 0.0),
        )
        self.assertAlmostEqual(explicit_restored[0], 12.0)
        self.assertAlmostEqual(explicit_restored[1], 24.0)

    def test_planar_fragment_helpers_detect_and_flatten_connected_planar_atoms(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 2),
                    Bond(2, 3, 1),
                    Bond(3, 4, 1),
                    Bond(4, 5, 1),
                    None,
                ]
            ),
            graph_state=CanvasGraphState(
                atom_bond_ids={
                    1: {0},
                    2: {0, 1},
                    3: {1, 2},
                    4: {2, 3},
                    5: {3},
                }
            ),
            services=SimpleNamespace(
                canvas_graph_service=SimpleNamespace(bond_in_cycle=lambda bond_id: bond_id in {2, 3})
            ),
        )
        bond_in_cycle = view.services.canvas_graph_service.bond_in_cycle
        self.assertTrue(atom_in_planar_system_for(view, 2, bond_in_cycle=bond_in_cycle))
        self.assertTrue(bond_is_planar_fragment_edge_for(view, 1, bond_in_cycle=bond_in_cycle))
        self.assertTrue(bond_is_planar_fragment_edge_for(view, 3, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 99, bond_in_cycle=bond_in_cycle))
        self.assertEqual(
            planar_fragment_components_for(view, {1, 2, 3, 4, 5}, bond_in_cycle=bond_in_cycle),
            [{1, 2, 3, 4, 5}],
        )

        coords = {
            1: (0.0, 0.0, 0.0),
            2: (1.0, 0.0, 1.0),
            3: (2.0, 0.0, 0.0),
            4: (3.0, 1.0, 0.0),
            5: (4.0, 1.0, 2.0),
        }
        normal = fragment_plane_normal_for({1, 2, 3}, coords)
        self.assertIsNotNone(normal)
        flattened = flatten_planar_fragments_for(view, {1, 2, 3, 4, 5}, coords, bond_in_cycle=bond_in_cycle)
        self.assertNotEqual(flattened[5], coords[5])

    def test_planar_fragment_helpers_cover_invalid_none_collinear_and_skip_paths(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(bonds=[None, Bond(1, 2, 1), Bond(2, 3, 1)]),
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 9}, 2: {0, 1}, 3: {2}}),
            services=SimpleNamespace(canvas_graph_service=SimpleNamespace(bond_in_cycle=lambda bond_id: False)),
        )
        bond_in_cycle = view.services.canvas_graph_service.bond_in_cycle
        self.assertFalse(atom_in_planar_system_for(view, 1, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 0, bond_in_cycle=bond_in_cycle))
        self.assertFalse(bond_is_planar_fragment_edge_for(view, 9, bond_in_cycle=bond_in_cycle))
        self.assertIsNone(
            fragment_plane_normal_for(
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(
            fragment_plane_normal_for(
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (1.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            ),
            (0.0, 0.0, 1.0),
        )
        self.assertEqual(
            flatten_planar_fragments_for(view, set(), {1: (1.0, 2.0, 3.0)}),
            {1: (1.0, 2.0, 3.0)},
        )

        skip_view = SimpleNamespace()
        coords = {1: (0.0, 0.0, 0.0), 2: (1.0, 0.0, 1.0), 3: (2.0, 0.0, 0.0)}
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=None),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=(1.0, 1.0, 1.0)),
        ):
            self.assertEqual(flatten_planar_fragments_for(skip_view, {1, 2, 3}, coords), coords)

        centroid_skip_view = SimpleNamespace()
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=(0.0, 0.0, 1.0)),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=None),
        ):
            self.assertEqual(flatten_planar_fragments_for(centroid_skip_view, {1, 2, 3}, coords), coords)

        small_component_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 2)]),
        )
        self.assertEqual(planar_fragment_components_for(small_component_view, {1, 2}), [])

        missing_point_view = SimpleNamespace()
        with (
            mock.patch("ui.selection_rotation_planarity.planar_fragment_components_for", return_value=[{1, 2, 3}]),
            mock.patch("ui.selection_rotation_planarity.fragment_plane_normal_for", return_value=(0.0, 0.0, 1.0)),
            mock.patch("ui.selection_rotation_planarity.center_for_coords_3d", return_value=(0.0, 0.0, 0.0)),
        ):
            flattened_missing = flatten_planar_fragments_for(
                missing_point_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 1.0),
                    2: (1.0, 0.0, 0.0),
                },
            )
        self.assertEqual(flattened_missing[1], (0.0, 0.0, 0.0))
        self.assertEqual(flattened_missing[2], (1.0, 0.0, 0.0))

    def test_apply_projected_atom_positions_updates_labels_dots_and_marks(self) -> None:
        label = object()
        dot = _FakeDot()
        mark_with_offset = _FakeMark({"dx": 2.0, "dy": -3.0})
        mark_without_offset = _FakeMark({})
        atom_label_service = SimpleNamespace(position_label=mock.Mock())
        scene_decoration_build_service = SimpleNamespace(set_mark_center=mock.Mock())
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 4.0, 5.0)}),
            mark_registry=CanvasMarkRegistry({1: [mark_with_offset, mark_without_offset]}),
            services=SimpleNamespace(
                atom_label_service=atom_label_service,
                scene_decoration_build_service=scene_decoration_build_service,
            ),
        )
        set_atom_coords_3d_for(view, {})
        set_atom_items_for(view, {1: label})
        set_atom_dots_for(view, {1: dot})

        with mock.patch(
            "ui.selection_rotation_access.project_point_3d_for",
            side_effect=lambda canvas, point: (point[0] + 10.0, point[1] - 5.0),
        ):
            apply_projected_atom_positions_for(
                view,
                {1, 2, 99},
                {
                    1: (1.0, 2.0, 3.0),
                    2: (5.0, 7.0, 11.0),
                },
            )

        self.assertEqual(atom_coords_3d_for(view)[1], (1.0, 2.0, 3.0))
        self.assertEqual(atom_coords_3d_for(view)[2], (5.0, 7.0, 11.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (11.0, -3.0))
        self.assertEqual((view.model.atoms[2].x, view.model.atoms[2].y), (15.0, 2.0))
        atom_label_service.position_label.assert_called_once_with(label, 11.0, -3.0)
        self.assertEqual(dot.positions, [(11.0, -3.0)])
        set_mark_center = scene_decoration_build_service.set_mark_center
        self.assertEqual(set_mark_center.call_count, 2)
        first_mark_pos = set_mark_center.call_args_list[0].args[1]
        second_mark_pos = set_mark_center.call_args_list[1].args[1]
        self.assertEqual((first_mark_pos.x(), first_mark_pos.y()), (13.0, -6.0))
        self.assertEqual((second_mark_pos.x(), second_mark_pos.y()), (11.0, -3.0))

    def test_apply_projected_positions_average_lengths_and_rotation_scale_cover_noop_cases(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            mark_registry=CanvasMarkRegistry(),
            services=SimpleNamespace(
                atom_label_service=SimpleNamespace(position_label=mock.Mock()),
                scene_decoration_build_service=SimpleNamespace(set_mark_center=mock.Mock()),
            ),
        )
        set_atom_coords_3d_for(view, {})
        set_atom_items_for(view, {})
        set_atom_dots_for(view, {})

        with mock.patch(
            "ui.selection_rotation_access.project_point_3d_for",
            side_effect=lambda canvas, point: (point[0], point[1]),
        ):
            apply_projected_atom_positions_for(
                view,
                {1, 2},
                {
                    1: (1.0, 2.0, 3.0),
                    2: (4.0, 5.0, 6.0),
                },
            )
        self.assertEqual(atom_coords_3d_for(view)[2], (4.0, 5.0, 6.0))
        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (1.0, 2.0))

        sparse_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 99}, 2: {0}, 3: {1}}),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None]),
            rotation_state=CanvasRotationState(
                base_bond_length=10.0,
                base_coords={1: (0.0, 0.0, 0.0), 2: (5.0, 0.0, 0.0)},
            ),
        )
        self.assertEqual(bond_ids_within_atom_ids_for(sparse_view, set()), set())
        self.assertIsNone(
            average_bond_length_for_atoms_for(
                sparse_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    3: (0.0, 0.0, 0.0),
                },
            )
        )
        self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 2.0)
        with mock.patch("ui.selection_rotation_access.average_bond_length_for_atoms_for", return_value=float("nan")):
            self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 1.0)
        with mock.patch("ui.selection_rotation_access.average_bond_length_for_atoms_for", return_value=0.0):
            self.assertEqual(rotation_scale_for_coords_for(sparse_view, {1, 2}, {}), 1.0)

        tail_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1, 2}, 2: {0, 2}, 3: {1}}),
            model=SimpleNamespace(
                bonds=[
                    None,
                    Bond(1, 3, 1),
                    Bond(1, 2, 1),
                ]
            ),
        )
        self.assertIsNone(
            average_bond_length_for_atoms_for(
                tail_view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (0.0, 0.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            )
        )

        forced_tail_view = SimpleNamespace(
            model=SimpleNamespace(
                bonds=[
                    None,
                    Bond(1, 3, 1),
                    Bond(1, 2, 1),
                ]
            )
        )
        self.assertAlmostEqual(
            average_bond_length_for_atoms_for(
                forced_tail_view,
                {1, 2},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (3.0, 4.0, 0.0),
                    3: (2.0, 0.0, 0.0),
                },
            ),
            5.0,
        )

    def test_bond_lookup_average_scale_and_axis_rotation_helpers(self) -> None:
        indexed_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 99}, 2: {0, 1}, 3: {1, 2}}),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 4, 1), None]),
            rotation_state=CanvasRotationState(
                base_bond_length=10.0,
                base_coords={1: (0.0, 0.0, 0.0), 2: (8.0, 0.0, 0.0), 3: (18.0, 0.0, 0.0)},
            ),
            _redraw_bond=mock.Mock(),
        )

        self.assertEqual(bond_ids_for_atom_ids_for(indexed_view, {1, 2, 99}), {0, 1, 99})
        self.assertEqual(bond_ids_within_atom_ids_for(indexed_view, {1, 2, 3}), {0, 1})
        self.assertAlmostEqual(
            average_bond_length_for_atoms_for(
                indexed_view,
                {1, 2, 3},
                {
                    1: (0.0, 0.0, 0.0),
                    2: (3.0, 4.0, 0.0),
                    3: (3.0, 8.0, 0.0),
                },
            ),
            4.5,
        )
        self.assertAlmostEqual(
            rotation_scale_for_coords_for(
                indexed_view,
                {2},
                {2: (6.0, 0.0, 0.0)},
                extra_atom_ids={1, 3},
            ),
            10.0 / 9.0,
        )

        redraw_view = SimpleNamespace(
            graph_state=CanvasGraphState(atom_bond_ids={1: {0}, 2: {0, 1}}),
            bond_renderer=SimpleNamespace(redraw_bond=mock.Mock()),
        )
        CanvasMoveController(
            redraw_view,
            hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
        ).redraw_bonds_for_atoms({1, 2})
        self.assertEqual({call.args[0] for call in redraw_view.bond_renderer.redraw_bond.call_args_list}, {0, 1})

        fallback_view = SimpleNamespace(
            graph_state=CanvasGraphState(),
            model=SimpleNamespace(bonds=[Bond(1, 2, 1), None, Bond(2, 3, 1)]),
        )
        self.assertEqual(bond_ids_within_atom_ids_for(fallback_view, {1, 2, 3}), {0, 2})
        self.assertIsNone(average_bond_length_for_atoms_for(fallback_view, set(), {}))

        no_scale_view = SimpleNamespace(rotation_state=CanvasRotationState())
        self.assertEqual(rotation_scale_for_coords_for(no_scale_view, set(), {}), 1.0)

        rotated = rotate_point_around_axis_for(
            SimpleNamespace(),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            math.pi / 2,
        )
        self.assertAlmostEqual(rotated[0], 0.0, places=6)
        self.assertAlmostEqual(rotated[1], 1.0, places=6)
        self.assertAlmostEqual(rotated[2], 0.0, places=6)
        self.assertEqual(
            rotate_point_around_axis_for(
                SimpleNamespace(),
                (1.0, 2.0, 3.0),
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                0.75,
            ),
            (1.0, 2.0, 3.0),
        )

    def test_bond_match_lookup_order_sum_and_normal_helpers(self) -> None:
        bonds = [Bond(1, 2, 2), Bond(2, 1, 3), None, Bond(1, 3, 0)]
        cached_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1, 3}, 2: {0, 1}, 3: {3}}),
        )
        fallback_view = SimpleNamespace(
            model=SimpleNamespace(bonds=bonds, atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}),
            graph_state=CanvasGraphState(),
        )

        cached_service = CanvasGraphService(cached_view)
        fallback_service = CanvasGraphService(fallback_view)
        cached_view.services = SimpleNamespace(canvas_graph_service=cached_service)

        self.assertFalse(CanvasGraphService.bond_matches_atoms(None, 1, 2))
        self.assertTrue(CanvasGraphService.bond_matches_atoms(bonds[0], 1, 2))
        self.assertTrue(CanvasGraphService.bond_matches_atoms(bonds[0], 2, 1))
        self.assertEqual(CanvasGraphService.first_matching_bond_id(bonds, 1, 2), 0)
        self.assertEqual(CanvasGraphService.first_matching_bond_id(bonds, 1, 2, skip_bond_id=0), 1)
        self.assertIsNone(cached_service.bond_id_between(1, 1))
        self.assertEqual(cached_service.bond_id_between(1, 2), 0)
        self.assertEqual(cached_service.bond_id_between(1, 2, skip_bond_id=0), 1)
        self.assertEqual(fallback_service.bond_id_between(1, 2, skip_bond_id=0), 1)
        self.assertIsNone(CanvasGraphService.first_matching_bond_id([Bond(3, 4, 1), None], 1, 2))
        self.assertIsNone(
            CanvasGraphService(
                SimpleNamespace(
                    model=SimpleNamespace(bonds=[Bond(3, 4, 1), None]),
                    graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1}, 2: {0, 1}}),
                )
            ).bond_id_between(1, 2)
        )
        self.assertTrue(cached_service.bond_exists(1, 2))
        self.assertFalse(cached_service.bond_exists(2, 3))
        self.assertEqual(CanvasGraphService(cached_view).atom_bond_order_sum(1), 6)

        nx, ny, length = line_normal_components(0.0, 0.0, 10.0, 0.0)
        self.assertEqual((nx, ny, length), (0.0, 1.0, 10.0))
        self.assertEqual(line_normal_components(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(orient_normal_toward_target(0.0, 1.0, 5.0, 0.0, 5.0, -3.0), (0.0, -1.0))
        self.assertEqual(line_normal_for(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0), (0.0, 1.0))
        self.assertEqual(
            line_normal_for(SimpleNamespace(), 0.0, 0.0, 10.0, 0.0, QPointF(5.0, -2.0)),
            (0.0, -1.0),
        )

        self.assertEqual(bond_offset_unit_3d_for(cached_view, 99, 2), None)
        self.assertEqual(
            bond_offset_unit_3d_for(
                SimpleNamespace(
                    model=SimpleNamespace(
                        atoms={1: Atom("C", 1.0, 1.0), 2: Atom("C", 1.0, 1.0)},
                    ),
                ),
                1,
                2,
            ),
            None,
        )
        self.assertEqual(bond_offset_unit_3d_for(cached_view, 1, 2), (0.0, 1.0))
        self.assertEqual(bond_offset_unit_3d_for(cached_view, 1, 2, target=(5.0, -2.0, 0.0)), (0.0, -1.0))

    def test_bond_graphics_access_and_color_fallbacks_delegate_cleanly(self) -> None:
        wedge_polygon = object()
        hash_segments = [(0.0, 0.0, 1.0, 1.0)]
        strip_polygon = object()
        ring_segments = ((1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0), (0.0, 1.0))
        ring_bond = object()
        one_sided_strip = object()
        parallel_bonds = [object(), object()]
        wedge_bond = object()
        hash_bond = object()
        dotted_bond = object()
        dotted_path = object()
        renderer = SimpleNamespace(
            parallel_bond_segments=mock.Mock(return_value=hash_segments),
            wedge_polygon=mock.Mock(return_value=wedge_polygon),
            hash_segments=mock.Mock(return_value=hash_segments),
            strip_polygon=mock.Mock(return_value=strip_polygon),
            ring_double_segments=mock.Mock(return_value=ring_segments),
            update_bond_geometry=mock.Mock(),
            add_bond_graphics=mock.Mock(),
            redraw_connected_bonds=mock.Mock(),
            draw_ring_double_bond=mock.Mock(return_value=ring_bond),
            one_sided_bond_strip=mock.Mock(return_value=one_sided_strip),
            draw_parallel_bonds=mock.Mock(return_value=parallel_bonds),
            draw_wedge_bond=mock.Mock(return_value=wedge_bond),
            draw_hash_bond=mock.Mock(return_value=hash_bond),
            draw_dotted_bond=mock.Mock(return_value=dotted_bond),
            dotted_bond_path=mock.Mock(return_value=dotted_path),
        )
        view = SimpleNamespace(bond_renderer=renderer)
        center = QPointF(5.0, 6.0)

        self.assertEqual(parallel_bond_segments_for(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), hash_segments)
        self.assertIs(wedge_polygon_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_polygon)
        self.assertEqual(hash_segments_for(view, 1.0, 2.0, 3.0, 4.0, 3, 7, 8), hash_segments)
        self.assertIs(strip_polygon_for(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), strip_polygon)
        self.assertEqual(ring_double_segments_for(view, "a", "b", center, 7, 8, (0.0, 0.0, 1.0)), ring_segments)
        bond_renderer_for(view).update_bond_geometry(4)
        add_bond_graphics_for(view, 5)
        self.assertIs(
            draw_ring_double_bond_for(
                view,
                "a",
                "b",
                center,
                7,
                8,
                outer_style="bold",
                center_3d=(1.0, 2.0, 3.0),
            ),
            ring_bond,
        )
        self.assertIs(one_sided_bond_strip_for(view, 1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0), one_sided_strip)
        self.assertEqual(draw_parallel_bonds_for(view, 1.0, 2.0, 3.0, 4.0, 2, 7, 8), parallel_bonds)
        self.assertIs(draw_wedge_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), wedge_bond)
        self.assertIs(draw_hash_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), hash_bond)
        self.assertIs(draw_dotted_bond_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_bond)
        self.assertIs(dotted_bond_path_for(view, 1.0, 2.0, 3.0, 4.0, 7, 8), dotted_path)

        renderer.parallel_bond_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.wedge_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.hash_segments.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 3, 7, 8)
        renderer.strip_polygon.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.ring_double_segments.assert_called_once_with("a", "b", center, 7, 8, (0.0, 0.0, 1.0))
        renderer.update_bond_geometry.assert_called_once_with(4)
        renderer.add_bond_graphics.assert_called_once_with(5)
        renderer.draw_ring_double_bond.assert_called_once_with(
            "a",
            "b",
            center,
            7,
            8,
            outer_style="bold",
            center_3d=(1.0, 2.0, 3.0),
        )
        renderer.one_sided_bond_strip.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 0.0, 1.0, 2.0, 3.0)
        renderer.draw_parallel_bonds.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 2, 7, 8)
        renderer.draw_wedge_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_hash_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.draw_dotted_bond.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)
        renderer.dotted_bond_path.assert_called_once_with(1.0, 2.0, 3.0, 4.0, 7, 8)

        CanvasMoveController(
            view,
            hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
        ).redraw_connected_bonds(1, skip_bond_id=3)
        renderer.redraw_connected_bonds.assert_called_once_with(1, skip_bond_id=3)

        color = object()
        pen_and_brush_item = _FakePenBrushItem(Qt.BrushStyle.SolidPattern)
        brush_only_item = _FakeBrushOnlyItem(Qt.BrushStyle.SolidPattern)
        no_brush_item = _FakeBrushOnlyItem(Qt.BrushStyle.NoBrush)

        apply_color_to_bond_item_for(view, pen_and_brush_item, color)
        apply_color_to_bond_item_for(view, brush_only_item, color)
        apply_color_to_bond_item_for(view, no_brush_item, color)

        self.assertIs(pen_and_brush_item._pen.color, color)
        self.assertEqual(pen_and_brush_item.pen_updates, [pen_and_brush_item._pen])
        self.assertEqual(pen_and_brush_item.brush_updates, [color])
        self.assertEqual(brush_only_item.brush_updates, [color])
        self.assertEqual(no_brush_item.brush_updates, [])


if __name__ == "__main__":
    unittest.main()
