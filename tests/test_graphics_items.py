import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter, QPen
    from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionGraphicsItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.graphics_items import AtomDotItem, AtomLabelItem, NoSelectRectItem


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for graphics item tests")
class GraphicsItemsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def assertRectAlmostEqual(self, left: QRectF, right: QRectF) -> None:
        self.assertAlmostEqual(left.x(), right.x())
        self.assertAlmostEqual(left.y(), right.y())
        self.assertAlmostEqual(left.width(), right.width())
        self.assertAlmostEqual(left.height(), right.height())

    def test_no_select_rect_item_paint_accepts_selected_option(self) -> None:
        item = NoSelectRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
        option = QStyleOptionGraphicsItem()
        option.state = QStyle.StateFlag.State_Selected
        image = QImage(16, 16, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try:
            item.paint(painter, option)
        finally:
            painter.end()

        self.assertTrue(option.state & QStyle.StateFlag.State_Selected)

    def test_atom_dot_item_without_hit_padding_uses_base_bounds_and_shape(self) -> None:
        item = AtomDotItem(-1.0, -1.0, 2.0, 2.0, hit_padding=0.0)
        item.setPen(QPen(Qt.PenStyle.NoPen))

        rect = item.rect()
        self.assertRectAlmostEqual(item.boundingRect(), rect)
        self.assertRectAlmostEqual(item.shape().boundingRect(), rect)

    def test_atom_label_item_without_hit_padding_or_radius_uses_text_bounds(self) -> None:
        item = AtomLabelItem("N", hit_padding=0.0, hit_radius=None)
        base_rect = super(AtomLabelItem, item).boundingRect()

        self.assertFalse(item._typographic)
        self.assertRectAlmostEqual(item._hit_rect(), base_rect)
        self.assertRectAlmostEqual(item.boundingRect(), base_rect)
        self.assertRectAlmostEqual(item.shape().boundingRect(), base_rect)

    def test_atom_label_item_with_subscript_uses_layout_bounds(self) -> None:
        item = AtomLabelItem("CH3", hit_padding=0.0, hit_radius=None)

        self.assertTrue(item._typographic)
        self.assertIsNotNone(item._layout)
        self.assertEqual([run.role for run in item._layout.runs], ["normal", "sub"])

        margin = item._doc_margin()
        expected = QRectF(
            0.0,
            0.0,
            item._layout.width + 2.0 * margin,
            item._layout.height + 2.0 * margin,
        )
        self.assertRectAlmostEqual(item.boundingRect(), expected)

    def test_atom_label_item_subscript_paints_without_error(self) -> None:
        item = AtomLabelItem("CO2Me", hit_padding=0.0, hit_radius=None)
        option = QStyleOptionGraphicsItem()
        image = QImage(48, 48, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try:
            item.paint(painter, option)
        finally:
            painter.end()

        self.assertTrue(item._typographic)

    def test_atom_label_item_outline_mode_paints_filled_glyphs(self) -> None:
        for text in ("CH3", "N"):
            item = AtomLabelItem(text, hit_padding=0.0, hit_radius=None)
            item.set_outline_mode(True)
            self.assertTrue(item._outline_mode)
            option = QStyleOptionGraphicsItem()
            image = QImage(48, 48, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            try:
                item.paint(painter, option)
            finally:
                painter.end()
            # Outlined glyphs are filled, so the image must have opaque pixels.
            non_empty = any(
                image.pixelColor(x, y).alpha() > 0
                for x in range(image.width())
                for y in range(image.height())
            )
            self.assertTrue(non_empty, f"expected outlined pixels for {text!r}")


if __name__ == "__main__":
    unittest.main()
