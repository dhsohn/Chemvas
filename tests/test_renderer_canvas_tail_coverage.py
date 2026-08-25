from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None
    Qt = None

if QApplication is not None:
    from chemvas.core.history import CompositeCommand, SetRingPolygonsCommand
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
    from chemvas.ui.bond_renderer import BondRenderer
    from chemvas.ui.canvas_atom_graphics_state import CanvasAtomGraphicsState
    from chemvas.ui.canvas_bond_graphics_state import (
        CanvasBondGraphicsState,
        bond_items_for,
        set_bond_items_for,
    )
    from chemvas.ui.canvas_geometry_controller import CanvasGeometryController
    from chemvas.ui.canvas_graph_state import CanvasGraphState, graph_state_for
    from chemvas.ui.canvas_rotation_state import CanvasRotationState
    from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState
    from chemvas.ui.scene_clipboard_transaction_logic import translated_scene_item_state
    from chemvas.ui.selection_collection_access import append_selected_item_ids
    from chemvas.ui.selection_rotation_access import average_bond_length_for_atoms_for
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
        self.runtime_state = canvas_runtime_state(
            bond_graphics_state=CanvasBondGraphicsState(),
            graph_state=CanvasGraphState(),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
        )
        set_bond_items_for(self, {})
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

    def test_renderer_helper_tails_cover_optional_neighbor_and_id_paths(self) -> None:
        graph_state_for(self.canvas).atom_bond_ids = {0: {0, 1}}
        self.canvas.model.bonds = [Bond(0, 1, 1), Bond(0, 2, 1)]
        self.assertGreater(
            self.renderer.line_geometry._junction_trim_for_atom(0, None), 0.0
        )

        graph_state_for(self.canvas).atom_bond_ids = {}
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

    def test_set_bond_length_without_ring_items_pushes_non_ring_composite(self) -> None:
        pushed = []
        view = SimpleNamespace(
            renderer=_FakeRenderer(),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 10.0, 0.0)}
            ),
            runtime_state=canvas_runtime_state(
                scene_items_state=CanvasSceneItemsState(),
                bond_graphics_state=CanvasBondGraphicsState(),
                atom_graphics_state=CanvasAtomGraphicsState(),
                atom_coords_3d_state=CanvasAtomCoords3DState(),
                rotation_state=CanvasRotationState(),
            ),
            scene=lambda: SimpleNamespace(removeItem=mock.Mock()),
            services=canvas_runtime_services(
                history_service=SimpleNamespace(push=pushed.append),
                hit_testing_service=SimpleNamespace(
                    mark_spatial_index_dirty=mock.Mock()
                ),
                structure_build_service=SimpleNamespace(render_model=mock.Mock()),
                # set_bond_length refreshes the selection outline on its way out.
                selection_controller=SimpleNamespace(
                    update_selection_outline=mock.Mock()
                ),
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

    def test_selection_translation_helpers_cover_missing_item_branches(self) -> None:
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

        scene = SimpleNamespace(clearSelection=mock.Mock())
        selection_controller = SimpleNamespace(update_selection_outline=mock.Mock())
        restore_view = SimpleNamespace(
            scene=lambda: scene,
            runtime_state=canvas_runtime_state(
                atom_graphics_state=CanvasAtomGraphicsState(),
                bond_graphics_state=CanvasBondGraphicsState(),
            ),
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
            runtime_state=canvas_runtime_state(
                graph_state=CanvasGraphState(
                    atom_bond_ids={1: {0, 1, 2}, 2: {0, 1, 2}}
                ),
            ),
        )
        coords = {1: (0.0, 0.0, 0.0), 2: (10.0, 0.0, 0.0)}
        self.assertEqual(
            average_bond_length_for_atoms_for(average_view, {1, 2}, coords), 10.0
        )


if __name__ == "__main__":
    unittest.main()
