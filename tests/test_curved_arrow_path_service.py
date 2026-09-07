import os
import unittest
from unittest import mock

from tests.canvas_factory import build_canvas_view

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QApplication, QGraphicsPathItem

from chemvas.ui.curved_arrow_path_service import CurvedArrowPathService


class CurvedArrowPathServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_set_curved_arrow_path_preserves_style_and_resets_origin(self) -> None:
        canvas = build_canvas_view()
        builder = canvas.services.scene_decoration.arrow_build_service
        start, end, control = QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 4.0)
        try:
            for double in (False, True):
                with self.subTest(double=double):
                    item = QGraphicsPathItem()
                    item.setPos(18.0, -7.0)
                    pen = item.pen()
                    pen.setWidthF(7.0)
                    item.setPen(pen)
                    CurvedArrowPathService(canvas).set_curved_arrow_path(
                        item, start, end, control, double
                    )
                    path = item.path()
                    self.assertEqual(path.elementCount(), 10 if double else 7)
                    self.assertEqual(
                        (path.elementAt(0).x, path.elementAt(0).y), (0.0, 0.0)
                    )
                    self.assertEqual(
                        (path.elementAt(3).x, path.elementAt(3).y), (10.0, 0.0)
                    )
                    self.assertEqual(
                        path,
                        builder.build_curved_arrow_path(start, end, control, double),
                    )
                    self.assertEqual(item.pen(), pen)
                    self.assertEqual(item.pos(), QPointF())
        finally:
            canvas.deleteLater()
            self.app.processEvents()

    def test_curved_creation_and_edit_use_one_path_owner(self) -> None:
        canvas = build_canvas_view()
        builder = canvas.services.scene_decoration.arrow_build_service
        replacement = QPainterPath(QPointF(13.0, 17.0))
        replacement.lineTo(29.0, 31.0)
        try:
            with mock.patch.object(
                builder,
                "build_curved_arrow_path",
                return_value=replacement,
                create=True,
            ) as build_path:
                item = builder.build_curved_arrow(QPointF(), QPointF(10.0, 0.0), False)
                self.assertEqual(item.path(), replacement)
                item.setPath(QPainterPath())
                CurvedArrowPathService(canvas).set_curved_arrow_path(
                    item, QPointF(), QPointF(10.0, 0.0), QPointF(5.0, 4.0), True
                )
                self.assertEqual(item.path(), replacement)
                self.assertEqual(build_path.call_count, 2)
        finally:
            canvas.deleteLater()
            self.app.processEvents()
