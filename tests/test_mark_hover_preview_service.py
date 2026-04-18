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

from ui.mark_hover_preview_service import MarkHoverPreviewService


class MarkHoverPreviewServiceTest(unittest.TestCase):
    def test_add_mark_hover_preview_prefers_hover_scene_service_when_available(self) -> None:
        hover_scene_service = mock.Mock()
        canvas = SimpleNamespace(
            find_atom_near=mock.Mock(return_value=1),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_atom_id=None,
            hover_bond_id=None,
            _hover_preview_style=None,
            _mark_center_for_pointer=mock.Mock(return_value=QPointF(12.0, 18.0)),
            _hover_scene_service=hover_scene_service,
            _build_mark_item=mock.Mock(return_value="item"),
            _set_mark_center=mock.Mock(),
        )

        MarkHoverPreviewService(canvas).add_mark_hover_preview(QPointF(4.0, 5.0))

        hover_scene_service.clear_hover_highlight.assert_called_once_with()
        hover_scene_service.add_atom_hover_indicator.assert_called_once_with(1)
        hover_scene_service.add_hover_preview_items.assert_called_once_with(["item"])
        canvas._set_mark_center.assert_called_once_with("item", QPointF(12.0, 18.0))

    def test_add_mark_hover_preview_adds_atom_preview_and_skips_duplicate_key(self) -> None:
        canvas = SimpleNamespace(
            find_atom_near=mock.Mock(return_value=1),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_atom_id=None,
            hover_bond_id=None,
            _hover_preview_style=None,
            _mark_center_for_pointer=mock.Mock(return_value=QPointF(12.0, 18.0)),
            _clear_hover_highlight=mock.Mock(),
            _add_atom_hover_indicator=mock.Mock(),
            _build_mark_item=mock.Mock(return_value="item"),
            _set_mark_center=mock.Mock(),
            _add_hover_preview_items=mock.Mock(),
        )
        service = MarkHoverPreviewService(canvas)

        service.add_mark_hover_preview(QPointF(4.0, 5.0))

        self.assertEqual(canvas.hover_atom_id, 1)
        self.assertEqual(canvas._hover_preview_style, "mark:plus:atom:1:12.0:18.0")
        canvas._clear_hover_highlight.assert_called_once_with()
        canvas._add_atom_hover_indicator.assert_called_once_with(1)
        canvas._set_mark_center.assert_called_once_with("item", QPointF(12.0, 18.0))
        canvas._add_hover_preview_items.assert_called_once_with(["item"])

        canvas._clear_hover_highlight.reset_mock()
        canvas._add_atom_hover_indicator.reset_mock()
        canvas._add_hover_preview_items.reset_mock()

        service.add_mark_hover_preview(QPointF(4.0, 5.0))

        canvas._clear_hover_highlight.assert_not_called()
        canvas._add_atom_hover_indicator.assert_not_called()
        canvas._add_hover_preview_items.assert_not_called()

    def test_add_mark_hover_preview_skips_duplicate_free_preview_and_handles_missing_item(self) -> None:
        canvas = SimpleNamespace(
            find_atom_near=mock.Mock(return_value=None),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0)),
            mark_kind="plus",
            hover_atom_id=None,
            hover_bond_id=None,
            _hover_preview_style="mark:plus:free:3.5:7.5",
            _mark_center_for_pointer=mock.Mock(return_value=QPointF(3.5, 7.5)),
            _clear_hover_highlight=mock.Mock(),
            _add_atom_hover_indicator=mock.Mock(),
            _build_mark_item=mock.Mock(return_value="item"),
            _set_mark_center=mock.Mock(),
            _add_hover_preview_items=mock.Mock(),
        )
        service = MarkHoverPreviewService(canvas)

        service.add_mark_hover_preview(QPointF(3.5, 7.5))

        canvas._clear_hover_highlight.assert_not_called()
        canvas._add_hover_preview_items.assert_not_called()

        canvas._hover_preview_style = None
        canvas._build_mark_item = mock.Mock(return_value=None)

        service.add_mark_hover_preview(QPointF(3.5, 7.5))

        canvas._clear_hover_highlight.assert_called_once_with()
        canvas._add_atom_hover_indicator.assert_not_called()
        canvas._add_hover_preview_items.assert_not_called()


if __name__ == "__main__":
    unittest.main()
