from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainterPath, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
    )
except ModuleNotFoundError:
    QApplication = None
    Qt = None

if QApplication is not None:
    from chemvas.core.history import CompositeCommand, SetRingPolygonsCommand
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.bond_preview_renderer import (
        BondPreviewBuildResolvers,
        BondPreviewConfig,
        build_bond_preview_items,
    )
    from chemvas.ui.bond_renderer import BondRenderer
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas_graph_state import CanvasGraphState
    from chemvas.ui.scene_clipboard_transaction_logic import translated_scene_item_state
    from chemvas.ui.selection_collection_access import append_selected_item_ids
    from chemvas.ui.selection_rotation_access import (
        average_bond_length_for_atoms_for,
        rotate_selection_for,
    )
    from chemvas.ui.selection_style_access import restore_selection_from_ids_for


class _FakeStyle:
    bond_spacing_px = 4.0
    bond_line_width = 1.2
    bold_bond_width = 2.4
    hash_spacing_px = 4.0
    bond_length_px = 20.0
    bond_color = "#224466"


class _FakeRenderer:
    def __init__(self) -> None:
        self.style = _FakeStyle()

    def bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.style.bond_line_width)
        return pen

    def bond_line_width(self) -> float:
        return self.style.bond_line_width

    def bold_bond_width(self) -> float:
        return self.style.bold_bond_width

    def bond_spacing(self) -> float:
        return self.style.bond_spacing_px

    def hash_spacing(self) -> float:
        return self.style.hash_spacing_px

    def dotted_bond_pen(self) -> QPen:
        pen = self.bond_pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        return pen

    def set_bond_length(self, length_px: float) -> None:
        self.style.bond_length_px = length_px


class _FakeCanvas:
    def __init__(self) -> None:
        self.renderer = _FakeRenderer()
        self.model = SimpleNamespace(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
                2: Atom("C", 0.0, 10.0),
            },
            bonds=[],
        )
        set_bond_items_for(self, {})
        self.graph_state = CanvasGraphState()
        self.atom_coords_3d: dict[int, tuple[float, float, float]] = {}
        self._labels: dict[int, object] = {}
        self._normal = (0.0, 1.0)
        self._ring_center = None
        self._ring_center_3d = None
        self._scene = QGraphicsScene()
        self.services = canvas_runtime_services(
            geometry_controller=SimpleNamespace(
                trim_line_for_labels=self.trim_line_for_labels,
                label_rect_for_atom=self.label_rect_for_atom,
                ring_center_for_bond=lambda bond: self._ring_center,
                ring_center_3d_for_bond=lambda bond: self._ring_center_3d,
            )
        )

    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

    def trim_line_for_labels(self, *_args):
        return (0.0, 1.0)

    def label_rect_for_atom(self, atom_id: int):
        return self._labels.get(atom_id)

    def _line_normal(self, x1, y1, x2, y2, ring_center):
        return self._normal


class _DataItem:
    def __init__(self, values: dict[int, object]) -> None:
        self._values = values

    def data(self, key: int):
        return self._values.get(key)


class _ChangingBonds:
    def __init__(self) -> None:
        self._calls = {0: 0, 1: 0, 2: 0}

    def __len__(self) -> int:
        return 3

    def __getitem__(self, bond_id: int):
        calls = self._calls[bond_id]
        self._calls[bond_id] += 1
        if bond_id == 0:
            return Bond(1, 2, 1) if calls == 0 else None
        if bond_id == 1:
            return Bond(1, 2, 1) if calls == 0 else Bond(1, 99, 1)
        return Bond(1, 2, 1)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for renderer/canvas tail tests"
)
class RendererCanvasTailCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.canvas = _FakeCanvas()
        self.renderer = BondRenderer(self.canvas)

    def _set_bond(self, bond: Bond) -> None:
        self.canvas.model.bonds = [bond]
        set_bond_items_for(self.canvas, {})

    def test_preview_bold_single_keeps_normal_for_non_outward_style(self) -> None:
        strip = QGraphicsPolygonItem()
        line_normal = mock.Mock(return_value=(0.25, 0.75))
        one_sided = mock.Mock(return_value=strip)
        resolvers = BondPreviewBuildResolvers(
            draw_wedge_bond=mock.Mock(),
            draw_hash_bond=mock.Mock(),
            draw_dotted_bond=mock.Mock(),
            draw_parallel_bonds=mock.Mock(),
            line_normal=line_normal,
            one_sided_bond_strip=one_sided,
            bond_pen=mock.Mock(),
            dotted_bond_pen=mock.Mock(),
        )

        items = build_bond_preview_items(
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            config=BondPreviewConfig(
                style="bold",
                order=1,
                bond_length_px=20.0,
                bond_line_width=1.2,
                bold_bond_width=2.4,
                hash_spacing_px=4.0,
            ),
            a_id=None,
            b_id=None,
            resolvers=resolvers,
        )

        self.assertEqual(items, [strip])
        self.assertEqual(one_sided.call_args.args[4:6], (0.25, 0.75))

    def test_renderer_helper_tails_cover_optional_neighbor_and_id_paths(self) -> None:
        self.canvas.graph_state.atom_bond_ids = {0: {0, 1}}
        self.canvas.model.bonds = [Bond(0, 1, 1), Bond(0, 2, 1)]
        self.assertGreater(
            self.renderer.line_geometry._junction_trim_for_atom(0, None), 0.0
        )

        self.canvas.graph_state.atom_bond_ids = {}
        self.assertEqual(
            self.renderer.line_geometry._plain_double_normal(
                0.0, 0.0, 10.0, 0.0, None, 1
            ),
            (0.0, 1.0),
        )

        items = self.renderer.draw_parallel_bonds(0.0, 0.0, 10.0, 0.0, 2)
        self.assertEqual(len(items), 2)
        self.assertLess(items[0].line().y1(), items[1].line().y1())

    def test_ring_double_segments_uses_offset_unit_without_flipping_when_center_aligned(
        self,
    ) -> None:
        outer, inner, normal = self.renderer.ring_double_segments(
            self.canvas.model.atoms[0],
            self.canvas.model.atoms[1],
            QPointF(5.0, 5.0),
            0,
            1,
        )

        self.assertEqual(normal, (0.0, 1.0))
        self.assertEqual(outer, (0.0, 0.0, 10.0, 0.0))
        self.assertGreater(inner[1], 0.0)

    def test_update_dotted_double_skips_short_or_mismatched_item_lists(self) -> None:
        self._set_bond(Bond(0, 1, 2, style="dotted_double_outer"))
        only_path = QGraphicsPathItem(QPainterPath())
        self.canvas.bond_items[0] = [only_path]
        self.renderer.update_bond_geometry(0)
        self.assertTrue(only_path.path().isEmpty())

        wrong_outer = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        wrong_inner = QGraphicsPolygonItem(QPolygonF())
        self.canvas.bond_items[0] = [wrong_outer, wrong_inner]
        self.renderer.update_bond_geometry(0)
        self.assertEqual(wrong_outer.line().length(), 0.0)
        self.assertEqual(len(wrong_inner.polygon()), 0)

    def test_update_bold_geometry_covers_line_fallback_branches(self) -> None:
        ring_outer_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        ring_inner_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self._set_bond(Bond(0, 1, 2, style="bold_out"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        self.canvas.bond_items[0] = [ring_outer_line, ring_inner_line]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        # The first scene-item slot is always the bold segment, even when the
        # ring-outward ordinary-double geometry selects its second segment.
        self.assertEqual(
            (ring_outer_line.line().x1(), ring_outer_line.line().x2()), (1.0, 9.0)
        )

        first_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        second_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self._set_bond(Bond(0, 1, 3, style="bold"))
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = [first_line, second_line]
        with mock.patch.object(
            self.renderer,
            "parallel_bond_segments",
            return_value=((1.0, 0.0, 9.0, 0.0), (1.0, 2.0, 9.0, 2.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual((first_line.line().x1(), first_line.line().x2()), (1.0, 9.0))

        single_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self._set_bond(Bond(0, 1, 1, style="bold"))
        self.canvas.bond_items[0] = [single_line]
        self.renderer.update_bond_geometry(0)
        # Bold strips run straight between the atoms now (no overshoot pad).
        self.assertAlmostEqual(single_line.line().length(), 10.0)

    def test_update_plain_and_higher_order_bonds_cover_tail_type_guards(self) -> None:
        self._set_bond(Bond(0, 1, 2, style="single"))
        self.canvas._ring_center = QPointF(5.0, 5.0)
        wrong_outer = QGraphicsPolygonItem(QPolygonF())
        wrong_inner = QGraphicsPolygonItem(QPolygonF())
        self.canvas.bond_items[0] = [wrong_outer, wrong_inner]
        with mock.patch.object(
            self.renderer,
            "ring_double_segments",
            return_value=((0.0, 0.0, 10.0, 0.0), (1.0, 1.0, 9.0, 1.0), (0.0, 1.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual(len(wrong_outer.polygon()), 0)
        self.assertEqual(len(wrong_inner.polygon()), 0)

        outer_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        inner_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self.canvas._ring_center = None
        self.canvas.bond_items[0] = [outer_line, inner_line]
        self.renderer.update_bond_geometry(0)
        self.assertGreater(outer_line.line().length(), 0.0)
        self.assertGreater(inner_line.line().length(), 0.0)

        skipped_polygon = QGraphicsPolygonItem(QPolygonF())
        updated_line = QGraphicsLineItem(0.0, 0.0, 0.0, 0.0)
        self._set_bond(Bond(0, 1, 3, style="single"))
        self.canvas.bond_items[0] = [skipped_polygon, updated_line]
        with mock.patch.object(
            self.renderer,
            "parallel_bond_segments",
            return_value=((0.0, -2.0, 10.0, -2.0), (0.0, 2.0, 10.0, 2.0)),
        ):
            self.renderer.update_bond_geometry(0)
        self.assertEqual(len(skipped_polygon.polygon()), 0)
        self.assertEqual(
            (updated_line.line().y1(), updated_line.line().y2()), (2.0, 2.0)
        )

    def test_set_bond_length_without_ring_items_pushes_non_ring_composite(self) -> None:
        pushed = []
        view = SimpleNamespace(
            renderer=_FakeRenderer(),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}
            ),
            ring_items=[],
            bond_items={},
            atom_items={},
            atom_dots={},
            scene=lambda: SimpleNamespace(removeItem=mock.Mock()),
            services=canvas_runtime_services(
                history_service=SimpleNamespace(push=pushed.append),
                hit_testing_service=SimpleNamespace(
                    mark_spatial_index_dirty=mock.Mock()
                ),
                structure_build_service=SimpleNamespace(render_model=mock.Mock()),
            ),
        )

        CanvasGeometryController(
            view,
            hit_testing_service=view.services.selection.hit_testing_service,
            history_service=view.services.history_service,
        ).set_bond_length(30.0)

        self.assertEqual(view.renderer.style.bond_length_px, 30.0)
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], CompositeCommand)
        self.assertEqual(len(pushed[0].commands), 2)
        self.assertFalse(
            any(
                isinstance(command, SetRingPolygonsCommand)
                for command in pushed[0].commands
            )
        )

    def test_selection_translation_and_rotation_helpers_cover_missing_item_branches(
        self,
    ) -> None:
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        append_selected_item_ids(
            SimpleNamespace(),
            atom_ids,
            bond_ids,
            _DataItem({0: "ring", 2: ("not", "a", "list")}),
        )
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, set())

        translated_note = translated_scene_item_state(
            {"kind": "note", "text": "unchanged"},
            dx=4.0,
            dy=5.0,
            atom_id_map={},
        )
        self.assertEqual(translated_note, {"kind": "note", "text": "unchanged"})

        rotating_scene = SimpleNamespace(
            selectedItems=lambda: [
                _DataItem({0: "atom", 1: 1}),
                _DataItem({0: "atom", 1: 2}),
            ]
        )
        atom_label_service = SimpleNamespace(position_label=mock.Mock())
        rotating_view = SimpleNamespace(
            scene=lambda: rotating_scene,
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 1.0, 0.0),
                    2: Atom("C", -1.0, 0.0),
                },
                bonds=[],
            ),
            atom_items={},
            services=canvas_runtime_services(
                atom_label_service=atom_label_service,
                move_controller=SimpleNamespace(redraw_connected_bonds=mock.Mock()),
                canvas_ring_fill_scene_service=SimpleNamespace(
                    rotate_ring_fills=mock.Mock()
                ),
                selection_controller=SimpleNamespace(
                    update_selection_outline=mock.Mock()
                ),
            ),
        )
        rotate_selection_for(rotating_view, 90.0)
        self.assertAlmostEqual(rotating_view.model.atoms[1].x, 0.0)
        self.assertAlmostEqual(rotating_view.model.atoms[1].y, 1.0)
        atom_label_service.position_label.assert_not_called()

        scene = SimpleNamespace(clearSelection=mock.Mock())
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        restore_view = SimpleNamespace(
            scene=lambda: scene,
            atom_items={},
            atom_dots={},
            bond_items={},
            services=canvas_runtime_services(selection_controller=selection_controller),
        )
        restore_selection_from_ids_for(restore_view, {99}, {42})
        scene.clearSelection.assert_called_once_with()
        selection_controller.update_selection_outline.assert_called_once_with()

    def test_average_bond_length_and_order_sum_cover_defensive_tail_branches(
        self,
    ) -> None:
        average_view = SimpleNamespace(
            model=SimpleNamespace(bonds=_ChangingBonds()),
            graph_state=CanvasGraphState(atom_bond_ids={1: {0, 1, 2}, 2: {0, 1, 2}}),
        )
        coords = {1: (0.0, 0.0, 0.0), 2: (10.0, 0.0, 0.0)}
        self.assertEqual(
            average_bond_length_for_atoms_for(average_view, {1, 2}, coords), 10.0
        )

        order_view = SimpleNamespace(
            model=SimpleNamespace(bonds=[Bond(1, 2, 2), Bond(3, 4, 3), None]),
        )
        order_view.services = canvas_runtime_services(
            canvas_graph_service=CanvasGraphService(order_view)
        )
        self.assertEqual(CanvasGraphService(order_view).atom_bond_order_sum(1), 2)
        self.assertEqual(CanvasGraphService(order_view).atom_bond_order_sum(99), 0)


if __name__ == "__main__":
    unittest.main()
