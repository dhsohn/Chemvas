import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QPointF
from ui.benzene_preview_service import BenzenePreviewService
from ui.canvas_insert_state import CanvasInsertState


class BenzenePreviewServiceTest(unittest.TestCase):
    def test_clear_preview_replaces_preview_pool(self) -> None:
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            insert_state=CanvasInsertState(benzene_preview_items=["stale"]),
        )
        service = BenzenePreviewService(canvas)

        with mock.patch("ui.benzene_preview_service.clear_benzene_preview_for_canvas", return_value=[]) as clear_preview:
            service.clear_preview()

        clear_preview.assert_called_once_with(canvas, ["stale"])
        canvas.scene.assert_not_called()
        self.assertEqual(canvas.insert_state.benzene_preview_items, [])

    def test_render_preview_uses_structure_points_and_renderer(self) -> None:
        structure_build_service = SimpleNamespace(
            benzene_ring_points=mock.Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        )
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            insert_state=CanvasInsertState(benzene_preview_items=["old"]),
            renderer=SimpleNamespace(
                bond_pen=mock.Mock(return_value="pen"),
                style=SimpleNamespace(bond_line_width=2.0),
            ),
        )
        service = BenzenePreviewService(canvas, structure_build_service=structure_build_service)

        with (
            mock.patch("ui.benzene_preview_service.clear_benzene_preview_for_canvas", return_value=[]) as clear_preview,
            mock.patch("ui.benzene_preview_service.rebuild_benzene_preview_for_canvas", return_value=["new"]) as rebuild_preview,
        ):
            service.render_preview(QPointF(5.0, 6.0), attach_atom_id=3, attach_bond_id=4)

        clear_preview.assert_called_once_with(canvas, ["old"])
        structure_build_service.benzene_ring_points.assert_called_once_with(
            QPointF(5.0, 6.0),
            attach_atom_id=3,
            attach_bond_id=4,
        )
        rebuild_preview.assert_called_once()
        self.assertIs(rebuild_preview.call_args.args[0], canvas)
        self.assertEqual(rebuild_preview.call_args.args[1], [QPointF(1.0, 2.0)])
        self.assertEqual(rebuild_preview.call_args.kwargs["base_pen"], "pen")
        self.assertEqual(rebuild_preview.call_args.kwargs["atom_radius"], 1.2)
        self.assertTrue(callable(rebuild_preview.call_args.kwargs["create_inner_bond_item"]))
        canvas.scene.assert_not_called()
        self.assertEqual(canvas.insert_state.benzene_preview_items, ["new"])

    def test_render_preview_skips_rebuild_when_ring_points_are_missing(self) -> None:
        structure_build_service = SimpleNamespace(benzene_ring_points=mock.Mock(return_value=None))
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            insert_state=CanvasInsertState(benzene_preview_items=["old"]),
            renderer=SimpleNamespace(
                bond_pen=mock.Mock(return_value="pen"),
                style=SimpleNamespace(bond_line_width=2.0),
            ),
        )
        service = BenzenePreviewService(canvas, structure_build_service=structure_build_service)

        with (
            mock.patch("ui.benzene_preview_service.clear_benzene_preview_for_canvas", return_value=[]) as clear_preview,
            mock.patch("ui.benzene_preview_service.rebuild_benzene_preview_for_canvas") as rebuild_preview,
        ):
            service.render_preview(QPointF(5.0, 6.0))

        clear_preview.assert_called_once_with(canvas, ["old"])
        rebuild_preview.assert_not_called()
        structure_build_service.benzene_ring_points.assert_called_once_with(
            QPointF(5.0, 6.0),
            attach_atom_id=None,
            attach_bond_id=None,
        )
        canvas.scene.assert_not_called()
        self.assertEqual(canvas.insert_state.benzene_preview_items, [])

    def test_create_inner_bond_item_returns_secondary_item(self) -> None:
        renderer = SimpleNamespace(draw_ring_double_bond=mock.Mock(return_value=["outer", "inner"]))
        canvas = SimpleNamespace(
            bond_renderer=renderer,
        )
        service = BenzenePreviewService(canvas)

        item = service._create_inner_bond_item(QPointF(1.0, 2.0), QPointF(3.0, 4.0), QPointF(5.0, 6.0))

        self.assertEqual(item, "inner")
        renderer.draw_ring_double_bond.assert_called_once()

    def test_create_inner_bond_item_returns_none_when_secondary_item_is_missing(self) -> None:
        renderer = SimpleNamespace(draw_ring_double_bond=mock.Mock(return_value=["outer"]))
        canvas = SimpleNamespace(
            bond_renderer=renderer,
        )
        service = BenzenePreviewService(canvas)

        item = service._create_inner_bond_item(QPointF(1.0, 2.0), QPointF(3.0, 4.0), QPointF(5.0, 6.0))

        self.assertIsNone(item)
        renderer.draw_ring_double_bond.assert_called_once()


if __name__ == "__main__":
    unittest.main()
