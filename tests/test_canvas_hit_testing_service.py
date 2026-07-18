import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom, Bond
    from chemvas.ui.canvas_bond_graphics_state import set_bond_items_for
    from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas_hover_state import set_hover_bond_id_for
    from chemvas.ui.spatial_index_state import CanvasSpatialIndexState


class _FakeScene:
    def __init__(self, items_at_pos=None) -> None:
        self._items_at_pos = list(items_at_pos or [])

    def items(self, *_args, **_kwargs):
        return list(self._items_at_pos)


class _FakeItem:
    def __init__(self, kind, *, data1=None, data2=None) -> None:
        self._data = {0: kind, 1: data1, 2: data2}

    def data(self, key):
        return self._data.get(key)


class _PositionEvent:
    def position(self):
        return SimpleNamespace(toPoint=lambda: "position-point")


def _service_double(**overrides):
    defaults = dict(
        scene_pos_from_event=mock.Mock(),
        item_at_scene_pos=mock.Mock(),
        item_at_event=mock.Mock(),
        grid_cell_size=mock.Mock(),
        cell_coords=mock.Mock(),
        ensure_spatial_index=mock.Mock(),
        rebuild_spatial_index=mock.Mock(),
        find_atom_near=mock.Mock(),
        find_bond_near=mock.Mock(),
        distance_point_to_segment=mock.Mock(),
        nearest_atom_hit=mock.Mock(),
        nearest_bond_hit=mock.Mock(),
        bond_id_from_event=mock.Mock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas hit testing service tests"
)
class CanvasHitTestingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_scene_pos_from_event_uses_qt6_position(self) -> None:
        scene_pos_mapper = mock.Mock(return_value=QPointF(1.0, 2.0))
        service = CanvasHitTestingService(
            SimpleNamespace(), scene_pos_mapper=scene_pos_mapper
        )

        self.assertEqual(
            service.scene_pos_from_event(_PositionEvent()), QPointF(1.0, 2.0)
        )
        scene_pos_mapper.assert_called_once()

    def test_item_lookup_prefers_atom_and_falls_back_to_nearby_bond(self) -> None:
        atom_item = _FakeItem("atom")
        canvas = SimpleNamespace(
            scene=lambda: _FakeScene(
                [
                    _FakeItem("selection_outline"),
                    _FakeItem("note_select"),
                    _FakeItem("bond"),
                    _FakeItem("ring"),
                    atom_item,
                ]
            ),
        )
        set_bond_items_for(canvas, {})
        service = CanvasHitTestingService(canvas)
        service.find_bond_near = mock.Mock(return_value=None)

        self.assertIs(service.item_at_scene_pos(QPointF(0.0, 0.0)), atom_item)

        nearby_bond_graphic = _FakeItem("bond_graphic")
        fallback_canvas = SimpleNamespace(
            scene=lambda: _FakeScene([_FakeItem("note_box"), _FakeItem("other")]),
        )
        set_bond_items_for(fallback_canvas, {4: [nearby_bond_graphic]})
        fallback_service = CanvasHitTestingService(fallback_canvas)
        fallback_service.find_bond_near = mock.Mock(return_value=4)

        self.assertIs(
            fallback_service.item_at_scene_pos(QPointF(2.0, 2.0)), nearby_bond_graphic
        )

        empty_fallback_canvas = SimpleNamespace(
            scene=lambda: _FakeScene([_FakeItem("note_box"), _FakeItem("other")]),
        )
        set_bond_items_for(empty_fallback_canvas, {4: []})
        empty_fallback_service = CanvasHitTestingService(empty_fallback_canvas)
        empty_fallback_service.find_bond_near = mock.Mock(return_value=4)

        self.assertEqual(
            empty_fallback_service.item_at_scene_pos(QPointF(2.0, 2.0)).data(0), "other"
        )

    def test_item_lookup_uses_scene_access_helper_without_canvas_scene_facade(
        self,
    ) -> None:
        atom_item = _FakeItem("atom")
        canvas = SimpleNamespace()
        set_bond_items_for(canvas, {})
        canvas.scene = mock.Mock(
            side_effect=AssertionError("scene facade should not be used by service")
        )
        service = CanvasHitTestingService(canvas)
        service.find_bond_near = mock.Mock(return_value=None)

        with mock.patch(
            "chemvas.ui.canvas_hit_testing_service.scene_items_at_pos_for_canvas",
            return_value=[_FakeItem("selection_outline"), atom_item],
        ) as scene_items:
            self.assertIs(service.item_at_scene_pos(QPointF(2.0, 2.0)), atom_item)

        scene_items.assert_called_once_with(canvas, QPointF(2.0, 2.0))
        canvas.scene.assert_not_called()

    def test_spatial_index_helpers_rebuild_and_find_atom_and_bond(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 10.0, 0.0),
                    3: Atom("N", 50.0, 50.0),
                },
                bonds=[Bond(1, 2, 1), None],
            ),
            spatial_index_state=CanvasSpatialIndexState(),
        )
        service = CanvasHitTestingService(canvas)

        self.assertEqual(service.grid_cell_size(), 20.0)
        self.assertEqual(service.cell_coords(21.0, -1.0, 10.0), (2, -1))

        service.ensure_spatial_index()

        self.assertFalse(canvas.spatial_index_state.dirty)
        self.assertEqual(canvas.spatial_index_state.cell_size, 20.0)
        self.assertEqual(service.find_atom_near(1.0, 1.0, 5.0), 1)
        self.assertEqual(service.find_bond_near(QPointF(5.0, 2.0), 4.0), 0)
        self.assertIsNone(service.find_bond_near(QPointF(40.0, 40.0), 4.0))

        service.mark_spatial_index_dirty()
        self.assertTrue(canvas.spatial_index_state.dirty)

    def test_spatial_index_self_heals_when_dirty_mark_was_missed(self) -> None:
        # The dirty flag depends on every mutation path remembering to call
        # mark_spatial_index_dirty; if one forgets, a changed atom/bond count
        # must still trigger a rebuild instead of serving stale hits.
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)},
                bonds=[],
            ),
            spatial_index_state=CanvasSpatialIndexState(),
        )
        service = CanvasHitTestingService(canvas)
        service.ensure_spatial_index()
        self.assertIsNone(service.find_atom_near(30.0, 0.0, 5.0))

        # Mutate the model WITHOUT marking the index dirty.
        canvas.model.atoms[2] = Atom("O", 30.0, 0.0)

        self.assertEqual(service.find_atom_near(30.0, 0.0, 5.0), 2)

    def test_spatial_index_and_nearest_helpers_cover_missing_sparse_and_zero_cell_paths(
        self,
    ) -> None:
        sparse_canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)},
                bonds=[Bond(1, 99, 1)],
            ),
            spatial_index_state=CanvasSpatialIndexState(),
        )
        sparse_service = CanvasHitTestingService(sparse_canvas)
        sparse_service.rebuild_spatial_index(20.0)
        self.assertEqual(sparse_canvas.spatial_index_state.bond_grid, {})

        sparse_lookup_canvas = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0)}, bonds=[None, Bond(1, 99, 1)]
            ),
            spatial_index_state=CanvasSpatialIndexState(
                dirty=False,
                cell_size=20.0,
                atom_grid={(0, 0): {9, 1}},
                bond_grid={(0, 0): {5, 0, 1}},
            ),
        )
        sparse_lookup_service = CanvasHitTestingService(sparse_lookup_canvas)
        self.assertEqual(sparse_lookup_service.find_atom_near(0.0, 0.0, 5.0), 1)
        self.assertIsNone(sparse_lookup_service.find_bond_near(QPointF(0.0, 0.0), 5.0))

    def test_nearest_hit_helpers_and_bond_id_from_event_use_service_methods(
        self,
    ) -> None:
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={1: Atom("C", 3.0, 4.0), 2: Atom("O", 10.0, 0.0)},
                bonds=[Bond(1, 2, 1), None],
            ),
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0)
            ),
        )
        set_hover_bond_id_for(canvas, 7)
        service = CanvasHitTestingService(canvas)
        service.find_atom_near = mock.Mock(return_value=1)
        service.find_bond_near = mock.Mock(return_value=0)
        service.distance_point_to_segment = mock.Mock(return_value=2.5)
        service.scene_pos_from_event = mock.Mock(return_value=QPointF(3.0, 4.0))

        self.assertEqual(service.nearest_atom_hit(QPointF(0.0, 0.0)), (1, 5.0))
        self.assertEqual(service.nearest_bond_hit(QPointF(5.0, 2.0)), (0, 2.5))
        self.assertEqual(service.bond_id_from_event(object()), 7)

        set_hover_bond_id_for(canvas, None)
        service.find_bond_near.return_value = 2
        self.assertEqual(service.bond_id_from_event(object()), 2)
        service.find_bond_near.assert_called_with(QPointF(3.0, 4.0), 10.56)


if __name__ == "__main__":
    unittest.main()
