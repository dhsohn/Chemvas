import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsScene = None
    QGraphicsTextItem = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.graphics_items import NoSelectLineItem
    from ui.hover_scene_renderer import (
        add_hover_preview_items,
        build_atom_hover_indicator,
        build_bond_hover_indicator,
        clear_hover_items,
    )


class _BrokenHoverItem:
    def scene(self):
        raise RuntimeError("wrapped C/C++ object has been deleted")


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for hover scene renderer tests")
class HoverSceneRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene = QGraphicsScene()

    def test_clear_hover_items_removes_scene_items_and_returns_empty_pool(self) -> None:
        line = NoSelectLineItem(0.0, 0.0, 10.0, 0.0)
        dot = QGraphicsEllipseItem(-1.0, -1.0, 2.0, 2.0)
        self.scene.addItem(line)
        self.scene.addItem(dot)

        cleared = clear_hover_items(self.scene, [line, dot])

        self.assertEqual(cleared, [])
        self.assertEqual(len(self.scene.items()), 0)
        self.assertIsNone(line.scene())
        self.assertIsNone(dot.scene())

    def test_clear_hover_items_ignores_off_scene_and_runtime_error_items(self) -> None:
        other_scene = QGraphicsScene()
        line = NoSelectLineItem(0.0, 0.0, 10.0, 0.0)
        other_scene.addItem(line)

        cleared = clear_hover_items(self.scene, [line, _BrokenHoverItem()])

        self.assertEqual(cleared, [])
        self.assertIs(line.scene(), other_scene)
        self.assertEqual(len(self.scene.items()), 0)

    def test_build_hover_indicators_match_atom_and_bond_geometry(self) -> None:
        atom_indicator = build_atom_hover_indicator(QPointF(12.0, -4.0), 3.5)
        bond_indicator = build_bond_hover_indicator(QPointF(-2.0, 6.0), QPointF(10.0, 14.0), 2.0)

        self.assertEqual(atom_indicator.rect().x(), 8.5)
        self.assertEqual(atom_indicator.rect().y(), -7.5)
        self.assertEqual(atom_indicator.rect().width(), 7.0)
        self.assertEqual(atom_indicator.rect().height(), 7.0)
        self.assertEqual(atom_indicator.pen().color(), QColor("#9a9a9a"))
        self.assertEqual(atom_indicator.brush().color(), QColor(190, 190, 190, 80))
        self.assertEqual(atom_indicator.zValue(), 5.0)

        self.assertEqual(bond_indicator.rect().x(), 2.0)
        self.assertEqual(bond_indicator.rect().y(), 8.0)
        self.assertEqual(bond_indicator.rect().width(), 4.0)
        self.assertEqual(bond_indicator.rect().height(), 4.0)
        self.assertEqual(bond_indicator.zValue(), 4.0)

    def test_add_hover_preview_items_styles_and_adds_items_to_scene(self) -> None:
        line = NoSelectLineItem(0.0, 0.0, 8.0, 2.0)
        dot = QGraphicsEllipseItem(1.0, 2.0, 4.0, 4.0)
        dot.setBrush(QColor("#ff0000"))
        text = QGraphicsTextItem("hover")
        preview_color = QColor("#556677")

        added = add_hover_preview_items(
            self.scene,
            [line, dot, text],
            color=preview_color,
            opacity=0.4,
            z_value=7.25,
        )

        self.assertEqual(added, [line, dot, text])
        self.assertEqual(len(self.scene.items()), 3)
        self.assertIs(line.scene(), self.scene)
        self.assertIs(dot.scene(), self.scene)
        self.assertIs(text.scene(), self.scene)
        self.assertEqual(line.pen().color(), preview_color)
        self.assertEqual(dot.pen().color(), preview_color)
        self.assertEqual(dot.brush().color(), preview_color)
        self.assertEqual(text.defaultTextColor(), preview_color)
        self.assertAlmostEqual(line.opacity(), 0.4)
        self.assertAlmostEqual(dot.opacity(), 0.4)
        self.assertAlmostEqual(text.opacity(), 0.4)
        self.assertAlmostEqual(line.zValue(), 7.25)
        self.assertAlmostEqual(dot.zValue(), 7.25)
        self.assertAlmostEqual(text.zValue(), 7.25)

    def test_add_hover_preview_items_uses_default_color_and_keeps_no_brush_items(self) -> None:
        dot = QGraphicsEllipseItem(1.0, 2.0, 4.0, 4.0)

        added = add_hover_preview_items(self.scene, [dot])

        self.assertEqual(added, [dot])
        self.assertIs(dot.scene(), self.scene)
        self.assertEqual(dot.pen().color(), QColor(120, 120, 120, 140))
        self.assertEqual(dot.brush().style().name, dot.brush().style().NoBrush.name)


if __name__ == "__main__":
    unittest.main()
