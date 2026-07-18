import unittest

from chemvas.features.insertion import (
    build_benzene_template_preview_geometry,
    build_template_preview_geometry,
    plan_template_preview_update,
)


class TemplatePreviewLogicTest(unittest.TestCase):
    def test_build_template_preview_geometry_returns_segments_and_dot_rects(
        self,
    ) -> None:
        geometry = build_template_preview_geometry(
            [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)],
            atom_radius=2.0,
        )

        self.assertEqual(
            geometry.line_segments,
            [
                (0.0, 0.0, 10.0, 0.0),
                (10.0, 0.0, 5.0, 8.0),
                (5.0, 8.0, 0.0, 0.0),
            ],
        )
        self.assertEqual(
            geometry.dot_rects,
            [
                (-2.0, -2.0, 4.0, 4.0),
                (8.0, -2.0, 4.0, 4.0),
                (3.0, 6.0, 4.0, 4.0),
            ],
        )

    def test_plan_template_preview_update_clears_when_points_missing(self) -> None:
        self.assertEqual(
            plan_template_preview_update(
                None, atom_radius=1.0, existing_line_count=3, existing_dot_count=3
            ).action,
            "clear",
        )
        self.assertEqual(
            plan_template_preview_update(
                [], atom_radius=1.0, existing_line_count=3, existing_dot_count=3
            ).action,
            "clear",
        )
        self.assertEqual(
            plan_template_preview_update(
                [(0.0, 0.0)],
                atom_radius=None,
                existing_line_count=1,
                existing_dot_count=1,
            ).action,
            "clear",
        )

    def test_plan_template_preview_update_rebuilds_when_counts_change(self) -> None:
        plan = plan_template_preview_update(
            [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)],
            atom_radius=1.0,
            existing_line_count=2,
            existing_dot_count=2,
        )

        self.assertEqual(plan.action, "rebuild")
        assert plan.geometry is not None
        self.assertEqual(len(plan.geometry.line_segments), 3)
        self.assertEqual(len(plan.geometry.dot_rects), 3)

    def test_benzene_template_preview_adds_aromatic_inner_segments(self) -> None:
        points = [
            (0.0, 0.0),
            (10.0, 0.0),
            (15.0, 8.0),
            (10.0, 16.0),
            (0.0, 16.0),
            (-5.0, 8.0),
        ]

        geometry = build_benzene_template_preview_geometry(points, atom_radius=1.0)
        plan = plan_template_preview_update(
            points,
            atom_radius=1.0,
            existing_line_count=6,
            existing_dot_count=6,
            aromatic=True,
        )

        self.assertEqual(len(geometry.line_segments), 9)
        self.assertEqual(len(geometry.dot_rects), 6)
        self.assertEqual(
            geometry.line_segments[:6],
            build_template_preview_geometry(points, 1.0).line_segments,
        )
        self.assertEqual(plan.action, "rebuild")
        assert plan.geometry is not None
        self.assertEqual(len(plan.geometry.line_segments), 9)

    def test_plan_template_preview_update_updates_when_counts_match(self) -> None:
        plan = plan_template_preview_update(
            [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)],
            atom_radius=1.5,
            existing_line_count=3,
            existing_dot_count=3,
        )

        self.assertEqual(plan.action, "update")
        assert plan.geometry is not None
        self.assertEqual(plan.geometry.line_segments[0], (0.0, 0.0, 10.0, 0.0))
        self.assertEqual(plan.geometry.dot_rects[1], (8.5, -1.5, 3.0, 3.0))


if __name__ == "__main__":
    unittest.main()
