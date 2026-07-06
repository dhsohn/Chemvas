import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainterPath
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from PyQt6.QtCore import QRectF
    from ui.selection_outline_items import (
        selection_center_outline_items,
        selection_component_outline_item,
        selection_group_outline_item,
        selection_object_outline_item,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for selection outline item tests")
class SelectionOutlineItemsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selection_group_outline_item_draws_dashed_unfilled_box(self) -> None:
        item = selection_group_outline_item(QRectF(0.0, 0.0, 40.0, 20.0), QColor("#1f5eff"))

        self.assertEqual(item.data(0), "selection_outline")
        self.assertEqual(item.data(2), {"kind": "group"})
        self.assertEqual(item.zValue(), 20)
        self.assertEqual(item.pen().style(), Qt.PenStyle.DashLine)
        self.assertEqual(item.pen().color().name(), "#1f5eff")
        self.assertEqual(item.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertTrue(item.contains(QPointF(20.0, 10.0)))

    def test_selection_object_outline_item_sets_metadata_and_fill(self) -> None:
        path = QPainterPath()
        path.addRect(0.0, 0.0, 10.0, 5.0)

        item = selection_object_outline_item(path, QColor("#abcdef"))

        self.assertEqual(item.data(0), "selection_outline")
        self.assertEqual(item.data(2), {"kind": "object"})
        self.assertEqual(item.zValue(), 19)
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), "#abcdef")

    def test_selection_component_outline_item_sorts_atom_ids(self) -> None:
        path = QPainterPath()
        path.addRect(0.0, 0.0, 10.0, 5.0)

        item = selection_component_outline_item(path, color=QColor("#123456"), atom_ids={3, 1, 2})

        self.assertEqual(item.data(0), "selection_outline")
        self.assertEqual(item.data(2), {"kind": "component", "atom_ids": [1, 2, 3]})
        self.assertEqual(item.zValue(), 19)
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), "#123456")

    def test_selection_center_outline_items_return_outer_and_inner_markers(self) -> None:
        outer, inner = selection_center_outline_items(QPointF(10.0, 12.0), outer_radius=4.0, inner_radius=1.5)

        self.assertEqual(outer.data(0), "selection_outline")
        self.assertEqual(inner.data(0), "selection_outline")
        self.assertEqual(outer.data(2), {"kind": "center"})
        self.assertEqual(inner.data(2), {"kind": "center"})
        self.assertEqual(outer.zValue(), 21)
        self.assertEqual(inner.zValue(), 21)
        self.assertEqual(outer.pen().color().name(), "#ff4dc9")
        self.assertAlmostEqual(outer.pen().widthF(), 1.4)
        self.assertEqual(outer.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(inner.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(inner.brush().color().name(), "#ff4dc9")


if __name__ == "__main__":
    unittest.main()
