import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QPointF


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.benzene_preview_service import BenzenePreviewService


class BenzenePreviewServiceTest(unittest.TestCase):
    def test_clear_preview_replaces_preview_pool(self) -> None:
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            _benzene_preview_items=["stale"],
        )
        service = BenzenePreviewService(canvas)

        with mock.patch("ui.benzene_preview_service.clear_benzene_preview", return_value=[]) as clear_preview:
            service.clear_preview()

        clear_preview.assert_called_once_with("scene", ["stale"])
        self.assertEqual(canvas._benzene_preview_items, [])

    def test_render_preview_uses_structure_points_and_renderer(self) -> None:
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            _benzene_preview_items=["old"],
            renderer=SimpleNamespace(
                bond_pen=mock.Mock(return_value="pen"),
                style=SimpleNamespace(bond_line_width=2.0),
            ),
            _structure_build_service=SimpleNamespace(
                benzene_ring_points=mock.Mock(return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
            ),
        )
        service = BenzenePreviewService(canvas)

        with (
            mock.patch("ui.benzene_preview_service.clear_benzene_preview", return_value=[]) as clear_preview,
            mock.patch("ui.benzene_preview_service.rebuild_benzene_preview", return_value=["new"]) as rebuild_preview,
        ):
            service.render_preview(QPointF(5.0, 6.0), attach_atom_id=3, attach_bond_id=4)

        clear_preview.assert_called_once_with("scene", ["old"])
        canvas._structure_build_service.benzene_ring_points.assert_called_once_with(
            QPointF(5.0, 6.0),
            attach_atom_id=3,
            attach_bond_id=4,
        )
        rebuild_preview.assert_called_once()
        self.assertEqual(rebuild_preview.call_args.kwargs["base_pen"], "pen")
        self.assertEqual(rebuild_preview.call_args.kwargs["atom_radius"], 1.2)
        self.assertTrue(callable(rebuild_preview.call_args.kwargs["create_inner_bond_item"]))
        self.assertEqual(canvas._benzene_preview_items, ["new"])

    def test_render_preview_skips_rebuild_when_ring_points_are_missing(self) -> None:
        canvas = SimpleNamespace(
            scene=mock.Mock(return_value="scene"),
            _benzene_preview_items=["old"],
            renderer=SimpleNamespace(
                bond_pen=mock.Mock(return_value="pen"),
                style=SimpleNamespace(bond_line_width=2.0),
            ),
            _structure_build_service=SimpleNamespace(
                benzene_ring_points=mock.Mock(return_value=None)
            ),
        )
        service = BenzenePreviewService(canvas)

        with (
            mock.patch("ui.benzene_preview_service.clear_benzene_preview", return_value=[]) as clear_preview,
            mock.patch("ui.benzene_preview_service.rebuild_benzene_preview") as rebuild_preview,
        ):
            service.render_preview(QPointF(5.0, 6.0))

        clear_preview.assert_called_once_with("scene", ["old"])
        rebuild_preview.assert_not_called()
        self.assertEqual(canvas._benzene_preview_items, [])

    def test_create_inner_bond_item_returns_secondary_item(self) -> None:
        canvas = SimpleNamespace(
            _draw_ring_double_bond=mock.Mock(return_value=["outer", "inner"]),
        )
        service = BenzenePreviewService(canvas)

        item = service._create_inner_bond_item(QPointF(1.0, 2.0), QPointF(3.0, 4.0), QPointF(5.0, 6.0))

        self.assertEqual(item, "inner")
        canvas._draw_ring_double_bond.assert_called_once()

    def test_create_inner_bond_item_returns_none_when_secondary_item_is_missing(self) -> None:
        canvas = SimpleNamespace(
            _draw_ring_double_bond=mock.Mock(return_value=["outer"]),
        )
        service = BenzenePreviewService(canvas)

        item = service._create_inner_bond_item(QPointF(1.0, 2.0), QPointF(3.0, 4.0), QPointF(5.0, 6.0))

        self.assertIsNone(item)
        canvas._draw_ring_double_bond.assert_called_once()


if __name__ == "__main__":
    unittest.main()
