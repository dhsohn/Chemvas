import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsItemGroup, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.selection_highlight_styler import (
        SelectionHighlightStyler,
        selection_highlight_styler_for,
    )
    from ui.selection_style_state import SelectionStyleState


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
            services=SimpleNamespace(),
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"),
                stroke_delta=0.6,
            ),
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
        canvas.selection_style_state.selected_items = [old_item]
        styler.set_selection_highlight([new_item])

        self.assertEqual(canvas.selection_style_state.selected_items, [new_item])
        self.assertEqual(old_item.pen().color().name(), "#333333")
        self.assertEqual(new_item.pen().color().name(), "#1f5eff")

        styler.clear_selection_highlight()
        self.assertEqual(canvas.selection_style_state.selected_items, [])
        self.assertEqual(new_item.pen().color().name(), "#444444")

    def test_apply_selection_style_ignores_items_without_pen(self) -> None:
        canvas = self._make_canvas()
        styler = SelectionHighlightStyler(canvas)
        item = object()

        styler.apply_selection_style(item, True)
        styler.apply_selection_style(item, False)

        self.assertEqual(canvas.selection_style_state.selected_items, [])

    def test_apply_selection_style_ignores_non_pen_restore_data(self) -> None:
        canvas = self._make_canvas()
        styler = SelectionHighlightStyler(canvas)
        item = _path_item("#555555", 1.1)
        item.setData(6, "not-a-pen")

        styler.apply_selection_style(item, False)

        self.assertEqual(item.pen().color().name(), "#555555")
        self.assertAlmostEqual(item.pen().widthF(), 1.1)

    def test_selection_highlight_styler_for_reuses_matching_or_duck_typed_service(self) -> None:
        canvas = self._make_canvas()
        matching = SelectionHighlightStyler(canvas)
        canvas.services.selection_highlight_styler = matching

        self.assertIs(selection_highlight_styler_for(canvas), matching)

        duck = SimpleNamespace(
            canvas=object(),
            set_selection_highlight=lambda items: None,
            clear_selection_highlight=lambda: None,
            apply_selection_style=lambda item, selected: None,
        )
        canvas.services.selection_highlight_styler = duck
        self.assertIs(selection_highlight_styler_for(canvas), duck)

        placeholder = object()
        canvas.services.selection_highlight_styler = placeholder
        self.assertIs(selection_highlight_styler_for(canvas), placeholder)


if __name__ == "__main__":
    unittest.main()
