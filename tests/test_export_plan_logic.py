import unittest

from chemvas.features.export import build_export_plan, points_for_mm


class BuildExportPlanTest(unittest.TestCase):
    def test_applies_symmetric_margin_and_unit_scale_one(self):
        plan = build_export_plan(10.0, 20.0, 100.0, 40.0, margin=8.0)
        self.assertIsNotNone(plan)
        self.assertAlmostEqual(plan.source_x, 2.0)
        self.assertAlmostEqual(plan.source_y, 12.0)
        self.assertAlmostEqual(plan.source_w, 116.0)
        self.assertAlmostEqual(plan.source_h, 56.0)
        # unit_scale defaults to 1.0 -> output points equal source units.
        self.assertAlmostEqual(plan.out_w_pt, 116.0)
        self.assertAlmostEqual(plan.out_h_pt, 56.0)

    def test_unit_scale_sets_physical_size_but_not_source(self):
        plan = build_export_plan(0.0, 0.0, 100.0, 40.0, margin=8.0, unit_scale=0.72)
        # Source rect (scene units) is unchanged...
        self.assertAlmostEqual(plan.source_w, 116.0)
        # ...only the physical output scales: a 20px bond -> 20*0.72 = 14.4 pt.
        self.assertAlmostEqual(plan.out_w_pt, 116.0 * 0.72)
        self.assertAlmostEqual(plan.out_h_pt, 56.0 * 0.72)

    def test_target_width_overrides_unit_scale(self):
        plan = build_export_plan(
            0.0, 0.0, 100.0, 40.0, margin=8.0, unit_scale=0.5, target_width_pt=232.0
        )
        self.assertAlmostEqual(plan.out_w_pt, 232.0)
        # height scales by the same factor (232/116 = 2).
        self.assertAlmostEqual(plan.out_h_pt, 112.0)

    def test_points_for_mm(self):
        self.assertAlmostEqual(points_for_mm(25.4), 72.0)
        self.assertAlmostEqual(points_for_mm(84.0), 84.0 / 25.4 * 72.0)

    def test_zero_content_returns_none(self):
        self.assertIsNone(build_export_plan(0.0, 0.0, 0.0, 40.0, margin=4.0))
        self.assertIsNone(build_export_plan(0.0, 0.0, 100.0, 0.0, margin=4.0))


if __name__ == "__main__":
    unittest.main()
