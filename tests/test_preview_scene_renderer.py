import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None
    QGraphicsEllipseItem = None
    QGraphicsScene = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.preview_scene_renderer import (
        apply_smiles_preview_geometry,
        apply_template_preview_geometry,
        clear_template_preview,
    )
    from ui.smiles_insert_logic import SmilesPreviewGeometry
    from ui.template_preview_logic import TemplatePreviewGeometry


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for preview renderer tests")
class PreviewSceneRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene = QGraphicsScene()
        self.base_pen = QPen(QColor("#123456"))

    def test_apply_smiles_preview_geometry_reuses_existing_items_on_update(self) -> None:
        geometry = SmilesPreviewGeometry(
            bond_segments={0: ((0.0, 0.0, 10.0, 0.0),)},
            atom_rects={0: (-1.0, -1.0, 2.0, 2.0), 1: (9.0, -1.0, 2.0, 2.0)},
        )
        items, bond_items, atom_items = apply_smiles_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=[],
            existing_bond_items={},
            existing_atom_items={},
            action="rebuild",
        )
        line = bond_items[0][0]
        dot = atom_items[0]

        moved_geometry = SmilesPreviewGeometry(
            bond_segments={0: ((5.0, 3.0, 15.0, 3.0),)},
            atom_rects={0: (4.0, 2.0, 2.0, 2.0), 1: (14.0, 2.0, 2.0, 2.0)},
        )
        updated_items, updated_bond_items, updated_atom_items = apply_smiles_preview_geometry(
            self.scene,
            moved_geometry,
            base_pen=self.base_pen,
            existing_items=items,
            existing_bond_items=bond_items,
            existing_atom_items=atom_items,
            action="update",
        )

        self.assertIs(updated_items[0], line)
        self.assertIs(updated_bond_items[0][0], line)
        self.assertIs(updated_atom_items[0], dot)
        self.assertEqual(line.line().x1(), 5.0)
        self.assertEqual(line.line().y1(), 3.0)
        self.assertEqual(dot.rect().x(), 4.0)
        self.assertEqual(dot.rect().y(), 2.0)

    def test_apply_smiles_preview_geometry_rebuilds_when_existing_pool_is_invalid(self) -> None:
        geometry = SmilesPreviewGeometry(
            bond_segments={0: ((0.0, 0.0, 10.0, 0.0),)},
            atom_rects={0: (-1.0, -1.0, 2.0, 2.0), 1: (9.0, -1.0, 2.0, 2.0)},
        )
        items, bond_items, atom_items = apply_smiles_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=[],
            existing_bond_items={},
            existing_atom_items={},
            action="rebuild",
        )
        old_line = bond_items[0][0]
        bond_items[0] = [QGraphicsEllipseItem(0.0, 0.0, 1.0, 1.0)]

        rebuilt_items, rebuilt_bond_items, rebuilt_atom_items = apply_smiles_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=items,
            existing_bond_items=bond_items,
            existing_atom_items=atom_items,
            action="update",
        )

        self.assertIsNot(rebuilt_bond_items[0][0], old_line)
        self.assertEqual(len(rebuilt_items), 3)
        self.assertEqual(len(rebuilt_atom_items), 2)
        self.assertEqual(len(self.scene.items()), 3)

    def test_apply_template_preview_geometry_reuses_existing_items_on_update(self) -> None:
        geometry = TemplatePreviewGeometry(
            line_segments=[(0.0, 0.0, 12.0, 0.0), (12.0, 0.0, 6.0, 10.0), (6.0, 10.0, 0.0, 0.0)],
            dot_rects=[(-1.0, -1.0, 2.0, 2.0), (11.0, -1.0, 2.0, 2.0), (5.0, 9.0, 2.0, 2.0)],
        )
        items, lines, dots = apply_template_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=[],
            existing_lines=[],
            existing_dots=[],
            action="rebuild",
        )
        line = lines[0]
        dot = dots[0]

        moved_geometry = TemplatePreviewGeometry(
            line_segments=[(5.0, 4.0, 17.0, 4.0), (17.0, 4.0, 11.0, 14.0), (11.0, 14.0, 5.0, 4.0)],
            dot_rects=[(4.0, 3.0, 2.0, 2.0), (16.0, 3.0, 2.0, 2.0), (10.0, 13.0, 2.0, 2.0)],
        )
        updated_items, updated_lines, updated_dots = apply_template_preview_geometry(
            self.scene,
            moved_geometry,
            base_pen=self.base_pen,
            existing_items=items,
            existing_lines=lines,
            existing_dots=dots,
            action="update",
        )

        self.assertIs(updated_items[0], line)
        self.assertIs(updated_lines[0], line)
        self.assertIs(updated_dots[0], dot)
        self.assertEqual(line.line().x1(), 5.0)
        self.assertEqual(dot.rect().x(), 4.0)

    def test_clear_template_preview_removes_scene_items(self) -> None:
        geometry = TemplatePreviewGeometry(
            line_segments=[(0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 5.0, 8.0), (5.0, 8.0, 0.0, 0.0)],
            dot_rects=[(-1.0, -1.0, 2.0, 2.0), (9.0, -1.0, 2.0, 2.0), (4.0, 7.0, 2.0, 2.0)],
        )
        items, _, _ = apply_template_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=[],
            existing_lines=[],
            existing_dots=[],
            action="rebuild",
        )

        cleared_items, cleared_lines, cleared_dots = clear_template_preview(self.scene, items)

        self.assertEqual(cleared_items, [])
        self.assertEqual(cleared_lines, [])
        self.assertEqual(cleared_dots, [])
        self.assertEqual(len(self.scene.items()), 0)


if __name__ == "__main__":
    unittest.main()
