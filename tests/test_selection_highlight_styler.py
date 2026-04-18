import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsItemGroup, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.selection_highlight_styler import SelectionHighlightStyler


def _path_item(color: str = "#111111", width: float = 1.5) -> QGraphicsPathItem:
    item = QGraphicsPathItem()
    path = QPainterPath()
    path.moveTo(0.0, 0.0)
    path.lineTo(10.0, 0.0)
    item.setPath(path)
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    item.setPen(pen)
    return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection highlight styler tests")
class SelectionHighlightStylerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_canvas(self):
        return SimpleNamespace(
            _selection_color=QColor("#1f5eff"),
            _selection_stroke_delta=0.6,
            _selected_items=[],
        )

    def test_apply_selection_style_handles_items_and_groups(self) -> None:
        canvas = self._make_canvas()
        styler = SelectionHighlightStyler(canvas)
        item = _path_item()

        styler.apply_selection_style(item, True)
        self.assertEqual(item.pen().color().name(), "#1f5eff")
        self.assertAlmostEqual(item.pen().widthF(), 2.1)
        self.assertIsInstance(item.data(6), QPen)

        styler.apply_selection_style(item, False)
        self.assertEqual(item.pen().color().name(), "#111111")
        self.assertAlmostEqual(item.pen().widthF(), 1.5)

        child = _path_item("#222222", 2.0)
        group = QGraphicsItemGroup()
        group.addToGroup(child)
        styler.apply_selection_style(group, True)
        self.assertEqual(child.pen().color().name(), "#1f5eff")
        styler.apply_selection_style(group, False)
        self.assertEqual(child.pen().color().name(), "#222222")
        self.assertAlmostEqual(child.pen().widthF(), 2.0)

    def test_set_and_clear_selection_highlight_round_trip_items(self) -> None:
        canvas = self._make_canvas()
        old_item = _path_item("#333333", 1.0)
        new_item = _path_item("#444444", 1.2)
        styler = SelectionHighlightStyler(canvas)

        styler.apply_selection_style(old_item, True)
        canvas._selected_items = [old_item]
        styler.set_selection_highlight([new_item])

        self.assertEqual(canvas._selected_items, [new_item])
        self.assertEqual(old_item.pen().color().name(), "#333333")
        self.assertEqual(new_item.pen().color().name(), "#1f5eff")

        styler.clear_selection_highlight()
        self.assertEqual(canvas._selected_items, [])
        self.assertEqual(new_item.pen().color().name(), "#444444")

    def test_apply_selection_style_ignores_items_without_pen(self) -> None:
        canvas = self._make_canvas()
        styler = SelectionHighlightStyler(canvas)
        item = object()

        styler.apply_selection_style(item, True)
        styler.apply_selection_style(item, False)

        self.assertEqual(canvas._selected_items, [])


if __name__ == "__main__":
    unittest.main()
