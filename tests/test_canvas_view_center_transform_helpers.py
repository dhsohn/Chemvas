import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom
    from ui.canvas_view import CanvasView


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewCenterTransformHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_center_helpers_average_and_bounding_box_skip_missing_atoms(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 1.0),
                    2: Atom("C", 6.0, 5.0),
                    3: Atom("C", 3.0, 11.0),
                }
            )
        )

        centroid = CanvasView._center_for_atoms(view, {1, 2, 3, 99})
        bbox_center = CanvasView._bounding_box_center_for_atoms(view, {1, 2, 3, 99})

        self.assertEqual(centroid, QPointF(3.0, 17.0 / 3.0))
        self.assertEqual(bbox_center, QPointF(3.0, 6.0))
        self.assertIsNone(CanvasView._center_for_atoms(view, {99}))
        self.assertIsNone(CanvasView._bounding_box_center_for_atoms(view, {99}))

    def test_update_view_transform_applies_shear_and_scale_over_base_transform(self) -> None:
        plain_view = SimpleNamespace(
            _base_transform=QTransform().translate(2.0, 3.0),
            _perspective_shear=0.0,
            _perspective_scale_y=1.0,
            setTransform=mock.Mock(),
        )

        CanvasView._update_view_transform(plain_view)

        plain_transform = plain_view.setTransform.call_args.args[0]
        self.assertAlmostEqual(plain_transform.dx(), 2.0)
        self.assertAlmostEqual(plain_transform.dy(), 3.0)
        self.assertAlmostEqual(plain_transform.m12(), 0.0)
        self.assertAlmostEqual(plain_transform.m22(), 1.0)

        skewed_view = SimpleNamespace(
            _base_transform=QTransform().translate(2.0, 3.0),
            _perspective_shear=0.25,
            _perspective_scale_y=1.5,
            setTransform=mock.Mock(),
        )

        CanvasView._update_view_transform(skewed_view)

        skewed_transform = skewed_view.setTransform.call_args.args[0]
        self.assertAlmostEqual(skewed_transform.dx(), 2.0)
        self.assertAlmostEqual(skewed_transform.dy(), 3.0)
        self.assertAlmostEqual(skewed_transform.m21(), 0.375)
        self.assertAlmostEqual(skewed_transform.m22(), 1.5)


if __name__ == "__main__":
    unittest.main()
