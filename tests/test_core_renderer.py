import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
except ModuleNotFoundError:
    Qt = None

if Qt is not None:
    from core.renderer import Renderer


@unittest.skipUnless(Qt is not None, "PyQt6 is required for renderer tests")
class RendererTest(unittest.TestCase):
    def test_bond_pens_use_flat_caps_while_dotted_stays_round(self) -> None:
        renderer = Renderer()

        self.assertEqual(renderer.bond_pen().capStyle(), Qt.PenCapStyle.FlatCap)
        self.assertEqual(renderer.bold_bond_pen().capStyle(), Qt.PenCapStyle.FlatCap)
        self.assertEqual(renderer.dotted_bond_pen().capStyle(), Qt.PenCapStyle.RoundCap)

    def test_visual_metrics_scale_with_bond_length(self) -> None:
        renderer = Renderer()

        self.assertEqual(renderer.metric_scale(), 1.0)
        self.assertAlmostEqual(renderer.bond_pen().widthF(), 1.5)
        self.assertAlmostEqual(renderer.bold_bond_pen().widthF(), 3.3)
        self.assertEqual(renderer.atom_font().pointSize(), 12)

        renderer.set_bond_length(10.0)

        self.assertEqual(renderer.metric_scale(), 0.5)
        self.assertAlmostEqual(renderer.bond_pen().widthF(), 0.75)
        self.assertAlmostEqual(renderer.bold_bond_pen().widthF(), 1.65)
        self.assertAlmostEqual(renderer.bond_spacing(), 2.2)
        self.assertEqual(renderer.atom_font().pointSize(), 6)


if __name__ == "__main__":
    unittest.main()
