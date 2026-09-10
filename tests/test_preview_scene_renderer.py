import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPicture
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.features.insertion import TemplatePreviewGeometry
from chemvas.ui.preview_scene_renderer import (
    PREVIEW_OPACITY,
    add_smiles_preview_item,
    apply_template_preview_geometry,
    clear_smiles_preview,
    clear_template_preview,
)


def _crossed_strokes_picture() -> QPicture:
    picture = QPicture()
    painter = QPainter(picture)
    pen = QPen(QColor("black"))
    pen.setWidthF(4.0)
    painter.setPen(pen)
    painter.drawLine(QPointF(-10.0, 0.0), QPointF(10.0, 0.0))
    painter.drawLine(QPointF(0.0, -10.0), QPointF(0.0, 10.0))
    painter.end()
    return picture


class PreviewSceneRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene = QGraphicsScene()
        self.base_pen = QPen(QColor("#123456"))

    def test_clear_smiles_preview_ignores_items_from_other_scenes(self) -> None:
        foreign_item = SimpleNamespace(scene=lambda: object())
        broken_item = SimpleNamespace(
            scene=lambda: (_ for _ in ()).throw(RuntimeError("disposed"))
        )

        self.assertEqual(
            clear_smiles_preview(self.scene, [foreign_item, broken_item]), []
        )

    def test_add_smiles_preview_item_replays_the_picture_without_hit_testing(
        self,
    ) -> None:
        picture = _crossed_strokes_picture()

        item = add_smiles_preview_item(self.scene, picture)

        self.assertIs(item.scene(), self.scene)
        self.assertIs(item.picture(), picture)
        self.assertTrue(item.boundingRect().contains(QRectF(picture.boundingRect())))
        # The ghost is never picked: hover and clicks reach the drawing
        # underneath it.
        self.assertTrue(item.shape().isEmpty())
        self.assertEqual(self.scene.items(QPointF(0.0, 0.0)), [])
        self.assertEqual(clear_smiles_preview(self.scene, [item]), [])
        self.assertIsNone(item.scene())

    def test_smiles_preview_item_blends_overlapping_strokes_once(self) -> None:
        # Per-primitive opacity would paint the crossing of two strokes
        # darker than either arm; the ghost blends the whole picture once.
        add_smiles_preview_item(self.scene, _crossed_strokes_picture())
        image = QImage(40, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.scene.render(
            painter, QRectF(0.0, 0.0, 40.0, 40.0), QRectF(-20.0, -20.0, 40.0, 40.0)
        )
        painter.end()

        crossing = QColor(image.pixel(20, 20))
        arm = QColor(image.pixel(28, 20))

        self.assertEqual(crossing.red(), arm.red())
        self.assertAlmostEqual(arm.red(), round(255 * (1 - PREVIEW_OPACITY)), delta=2)

    def test_apply_template_preview_geometry_reuses_existing_items_on_update(
        self,
    ) -> None:
        geometry = TemplatePreviewGeometry(
            line_segments=[
                (0.0, 0.0, 12.0, 0.0),
                (12.0, 0.0, 6.0, 10.0),
                (6.0, 10.0, 0.0, 0.0),
            ],
            dot_rects=[
                (-1.0, -1.0, 2.0, 2.0),
                (11.0, -1.0, 2.0, 2.0),
                (5.0, 9.0, 2.0, 2.0),
            ],
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
            line_segments=[
                (5.0, 4.0, 17.0, 4.0),
                (17.0, 4.0, 11.0, 14.0),
                (11.0, 14.0, 5.0, 4.0),
            ],
            dot_rects=[
                (4.0, 3.0, 2.0, 2.0),
                (16.0, 3.0, 2.0, 2.0),
                (10.0, 13.0, 2.0, 2.0),
            ],
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

    def test_apply_template_preview_geometry_rebuilds_when_counts_do_not_match(
        self,
    ) -> None:
        geometry = TemplatePreviewGeometry(
            line_segments=[(0.0, 0.0, 12.0, 0.0)],
            dot_rects=[(-1.0, -1.0, 2.0, 2.0)],
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
        old_line = lines[0]

        rebuilt_items, rebuilt_lines, rebuilt_dots = apply_template_preview_geometry(
            self.scene,
            geometry,
            base_pen=self.base_pen,
            existing_items=items,
            existing_lines=[],
            existing_dots=dots,
            action="update",
        )

        self.assertIsNot(rebuilt_lines[0], old_line)
        self.assertEqual(len(rebuilt_items), 2)
        self.assertEqual(len(rebuilt_dots), 1)

    def test_clear_template_preview_removes_scene_items(self) -> None:
        geometry = TemplatePreviewGeometry(
            line_segments=[
                (0.0, 0.0, 10.0, 0.0),
                (10.0, 0.0, 5.0, 8.0),
                (5.0, 8.0, 0.0, 0.0),
            ],
            dot_rects=[
                (-1.0, -1.0, 2.0, 2.0),
                (9.0, -1.0, 2.0, 2.0),
                (4.0, 7.0, 2.0, 2.0),
            ],
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

        cleared_items, cleared_lines, cleared_dots = clear_template_preview(
            self.scene, items
        )

        self.assertEqual(cleared_items, [])
        self.assertEqual(cleared_lines, [])
        self.assertEqual(cleared_dots, [])
        self.assertEqual(len(self.scene.items()), 0)
