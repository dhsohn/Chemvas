import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.curved_arrow_path_service import CurvedArrowPathService


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for curved arrow path service tests")
class CurvedArrowPathServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_set_curved_arrow_path_builds_path_and_arrow_heads(self) -> None:
        path_item = QGraphicsPathItem()
        path_item.setPos(18.0, -7.0)
        build_service = SimpleNamespace(add_arrow_head=mock.Mock())
        canvas = SimpleNamespace(services=SimpleNamespace(scene_decoration_build_service=build_service))

        CurvedArrowPathService(canvas).set_curved_arrow_path(
            path_item,
            start=QPointF(0.0, 0.0),
            end=QPointF(10.0, 0.0),
            control=QPointF(5.0, 4.0),
            double=True,
        )

        self.assertFalse(path_item.path().isEmpty())
        self.assertEqual(build_service.add_arrow_head.call_count, 2)
        self.assertEqual(path_item.pos(), QPointF())


if __name__ == "__main__":
    unittest.main()
