import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
except ModuleNotFoundError:
    Qt = None

if Qt is not None:
    from chemvas.core.renderer import Renderer


@unittest.skipUnless(Qt is not None, "PyQt6 is required for renderer tests")
class RendererTest(unittest.TestCase):
    def test_bond_pens_use_round_caps_so_vertices_join_cleanly(self) -> None:
        renderer = Renderer()

        # Round caps make bonds meeting at an atom overlap into a clean join.
        self.assertEqual(renderer.bond_pen().capStyle(), Qt.PenCapStyle.RoundCap)
        self.assertEqual(renderer.dotted_bond_pen().capStyle(), Qt.PenCapStyle.RoundCap)
        # Bold bonds are drawn as mitred polygons, so their pen cap is unused.
        self.assertEqual(renderer.bold_bond_pen().capStyle(), Qt.PenCapStyle.FlatCap)

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
