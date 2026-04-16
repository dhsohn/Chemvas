import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
except ModuleNotFoundError:
    Qt = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if Qt is not None:
    from core.renderer import Renderer


@unittest.skipUnless(Qt is not None, "PyQt6 is required for renderer tests")
class RendererTest(unittest.TestCase):
    def test_bond_pens_use_flat_caps_while_dotted_stays_round(self) -> None:
        renderer = Renderer()

        self.assertEqual(renderer.bond_pen().capStyle(), Qt.PenCapStyle.FlatCap)
        self.assertEqual(renderer.bold_bond_pen().capStyle(), Qt.PenCapStyle.FlatCap)
        self.assertEqual(renderer.dotted_bond_pen().capStyle(), Qt.PenCapStyle.RoundCap)


if __name__ == "__main__":
    unittest.main()
