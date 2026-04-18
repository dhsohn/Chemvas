import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
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
    from core.model import Atom, Bond
    from ui.hover_scene_service import HoverSceneService


class _CanvasStub:
    def __init__(self, scene, *, atoms=None, bonds=None, bond_length_px: float = 20.0) -> None:
        self._scene = scene
        self.model = SimpleNamespace(
            atoms={} if atoms is None else atoms,
            bonds=[] if bonds is None else bonds,
        )
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=bond_length_px))
        self.hover_items = []
        self.hover_atom_id = None
        self.hover_bond_id = None
        self._hover_preview_style = None

    def scene(self):
        return self._scene


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for hover scene service tests")
class HoverSceneServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene = QGraphicsScene()

    def test_clear_hover_highlight_removes_tracked_items_and_resets_state(self) -> None:
        keep = QGraphicsEllipseItem(-1.0, -1.0, 2.0, 2.0)
        hover_text = QGraphicsTextItem("hover")
        hover_dot = QGraphicsEllipseItem(1.0, 2.0, 3.0, 4.0)
        self.scene.addItem(keep)
        self.scene.addItem(hover_text)
        self.scene.addItem(hover_dot)
        canvas = _CanvasStub(self.scene)
        canvas.hover_items = [hover_text, hover_dot]
        canvas.hover_atom_id = 7
        canvas.hover_bond_id = 3
        canvas._hover_preview_style = "hash"

        HoverSceneService(canvas).clear_hover_highlight()

        self.assertEqual(canvas.hover_items, [])
        self.assertIsNone(canvas.hover_atom_id)
        self.assertIsNone(canvas.hover_bond_id)
        self.assertIsNone(canvas._hover_preview_style)
        self.assertIs(keep.scene(), self.scene)
        self.assertIsNone(hover_text.scene())
        self.assertIsNone(hover_dot.scene())
        self.assertEqual(len(self.scene.items()), 1)

    def test_add_hover_preview_items_adds_styled_items_and_tracks_them(self) -> None:
        existing = QGraphicsEllipseItem(0.0, 0.0, 1.0, 1.0)
        dot = QGraphicsEllipseItem(1.0, 2.0, 4.0, 4.0)
        dot.setBrush(QColor("#ff0000"))
        text = QGraphicsTextItem("preview")
        canvas = _CanvasStub(self.scene)
        canvas.hover_items = [existing]

        HoverSceneService(canvas).add_hover_preview_items([dot, text])

        preview_color = QColor(120, 120, 120, 140)
        self.assertEqual(canvas.hover_items, [existing, dot, text])
        self.assertIs(dot.scene(), self.scene)
        self.assertIs(text.scene(), self.scene)
        self.assertEqual(dot.pen().color(), preview_color)
        self.assertEqual(dot.brush().color(), preview_color)
        self.assertEqual(text.defaultTextColor(), preview_color)
        self.assertAlmostEqual(dot.opacity(), 0.55)
        self.assertAlmostEqual(text.opacity(), 0.55)
        self.assertAlmostEqual(dot.zValue(), 4.5)
        self.assertAlmostEqual(text.zValue(), 4.5)

    def test_add_atom_hover_indicator_adds_circle_for_existing_atom(self) -> None:
        canvas = _CanvasStub(
            self.scene,
            atoms={3: Atom("C", 12.0, 34.0)},
            bond_length_px=20.0,
        )

        HoverSceneService(canvas).add_atom_hover_indicator(3)

        self.assertEqual(len(canvas.hover_items), 1)
        indicator = canvas.hover_items[0]
        self.assertIsInstance(indicator, QGraphicsEllipseItem)
        self.assertIs(indicator.scene(), self.scene)
        rect = indicator.rect()
        self.assertAlmostEqual(rect.x(), 7.0)
        self.assertAlmostEqual(rect.y(), 29.0)
        self.assertAlmostEqual(rect.width(), 10.0)
        self.assertAlmostEqual(rect.height(), 10.0)

    def test_add_bond_hover_indicator_adds_midpoint_circle_for_existing_bond(self) -> None:
        canvas = _CanvasStub(
            self.scene,
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 10.0),
            },
            bonds=[Bond(1, 2)],
            bond_length_px=20.0,
        )

        HoverSceneService(canvas).add_bond_hover_indicator(0)

        self.assertEqual(len(canvas.hover_items), 1)
        indicator = canvas.hover_items[0]
        self.assertIsInstance(indicator, QGraphicsEllipseItem)
        self.assertIs(indicator.scene(), self.scene)
        rect = indicator.rect()
        self.assertAlmostEqual(rect.x(), 5.6)
        self.assertAlmostEqual(rect.y(), 0.6)
        self.assertAlmostEqual(rect.width(), 8.8)
        self.assertAlmostEqual(rect.height(), 8.8)

    def test_noop_contract_skips_empty_preview_and_invalid_hover_targets(self) -> None:
        canvas = _CanvasStub(
            self.scene,
            atoms={1: Atom("C", 0.0, 0.0)},
            bonds=[None, Bond(1, 9)],
        )
        service = HoverSceneService(canvas)

        service.add_hover_preview_items([])
        service.add_atom_hover_indicator(99)
        service.add_bond_hover_indicator(None)
        service.add_bond_hover_indicator(99)
        service.add_bond_hover_indicator(0)
        service.add_bond_hover_indicator(1)

        self.assertEqual(canvas.hover_items, [])
        self.assertEqual(len(self.scene.items()), 0)


if __name__ == "__main__":
    unittest.main()
