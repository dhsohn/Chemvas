import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsLineItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.features.selection import (
        selection_line_stroke_path,
        selection_path_for_bond_item,
        selection_path_for_object_item,
    )

    class EmptyShapeItem(QGraphicsPathItem):
        def __init__(self) -> None:
            super().__init__()
            self.setPos(2.0, 3.0)

        def shape(self) -> QPainterPath:
            return QPainterPath()

        def sceneBoundingRect(self) -> QRectF:
            return QRectF(1.0, 2.0, 6.0, 7.0)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for selection outline path tests"
)
class SelectionOutlinePathsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selection_line_stroke_path_builds_non_empty_stroke(self) -> None:
        path = selection_line_stroke_path(QPointF(0.0, 0.0), QPointF(10.0, 0.0), 4.0)

        self.assertFalse(path.isEmpty())
        self.assertGreater(path.boundingRect().height(), 0.0)

    def test_selection_path_for_bond_item_handles_line_polygon_and_paths(self) -> None:
        widths: list[float] = []

        def default_width_for_pen(pen) -> float:
            widths.append(pen.widthF())
            return 5.0

        line_item = QGraphicsLineItem(0.0, 0.0, 10.0, 0.0)
        line_path = selection_path_for_bond_item(
            line_item, default_width_for_pen=default_width_for_pen
        )
        self.assertFalse(line_path.isEmpty())
        self.assertEqual(widths, [1.0])

        polygon_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(8.0, 0.0), QPointF(4.0, 3.0)])
        )
        self.assertFalse(selection_path_for_bond_item(polygon_item).isEmpty())

        source = QPainterPath()
        source.addRect(0.0, 0.0, 8.0, 2.0)
        filled = QGraphicsPathItem(source)
        filled.setPen(QPen(Qt.PenStyle.NoPen))
        filled.setBrush(QBrush(QColor("#334455")))
        self.assertEqual(
            selection_path_for_bond_item(filled).boundingRect(), source.boundingRect()
        )

        stroked = QGraphicsPathItem(source)
        stroked.setPen(QPen(QColor("#112233"), 1.2))
        self.assertFalse(selection_path_for_bond_item(stroked).isEmpty())
        self.assertTrue(selection_path_for_bond_item(object()).isEmpty())

    def test_selection_path_for_object_item_handles_mark_arrow_text_and_fallbacks(
        self,
    ) -> None:
        mark_path = selection_path_for_object_item(
            object(),
            kind="mark",
            pad=2.0,
            mark_center=QPointF(4.0, 5.0),
            mark_radius=3.0,
        )
        self.assertFalse(mark_path.isEmpty())
        self.assertTrue(
            selection_path_for_object_item(object(), kind="mark", pad=2.0).isEmpty()
        )

        arrow_source = QPainterPath()
        arrow_source.moveTo(0.0, 0.0)
        arrow_source.lineTo(10.0, 0.0)
        arrow_item = QGraphicsPathItem(arrow_source)
        arrow_item.setPen(QPen(QColor("#112233"), 1.2))
        arrow_path = selection_path_for_object_item(
            arrow_item, kind="arrow", pad=2.0, atom_pick_radius=10.0
        )
        self.assertFalse(arrow_path.isEmpty())

        text_item = QGraphicsTextItem("note")
        self.assertFalse(
            selection_path_for_object_item(text_item, kind="note", pad=2.0).isEmpty()
        )
        self.assertFalse(
            selection_path_for_object_item(
                EmptyShapeItem(), kind="orbital", pad=2.0
            ).isEmpty()
        )


if __name__ == "__main__":
    unittest.main()
