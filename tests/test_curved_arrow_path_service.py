import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

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
        canvas = SimpleNamespace(_add_arrow_head=mock.Mock())

        CurvedArrowPathService(canvas).set_curved_arrow_path(
            path_item,
            start=QPointF(0.0, 0.0),
            end=QPointF(10.0, 0.0),
            control=QPointF(5.0, 4.0),
            double=True,
        )

        self.assertFalse(path_item.path().isEmpty())
        self.assertEqual(canvas._add_arrow_head.call_count, 2)


if __name__ == "__main__":
    unittest.main()
