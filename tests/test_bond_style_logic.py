import unittest

from chemvas.features.rendering import (
    BOLD_STYLE_CENTER,
    BOLD_STYLE_DEFAULT,
    BOLD_STYLE_OUTER,
    DOTTED_DOUBLE_STYLE_DEFAULT,
    DOTTED_DOUBLE_STYLE_OUTER,
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    base_plain_double_style_for_dotted_variant,
    bold_double_style_for_position,
    bold_double_style_for_style,
    cycle_plain_bond_style,
    dotted_double_variant_for_style,
    double_position_for_style,
    is_bold_double_bond_style,
    is_dotted_double_bond_style,
    is_plain_double_bond_style,
    is_positionable_double_bond_style,
    normalized_bold_double_style,
    normalized_plain_double_style,
    style_for_double_position,
    style_for_existing_bond_overlay,
)


class BondStyleLogicTest(unittest.TestCase):
    def test_bold_double_helpers_share_plain_double_position_contract(self) -> None:
        pairs = (
            (DOUBLE_STYLE_DEFAULT, BOLD_STYLE_DEFAULT),
            (DOUBLE_STYLE_CENTER, BOLD_STYLE_CENTER),
            (DOUBLE_STYLE_OUTER, BOLD_STYLE_OUTER),
        )
        for plain_style, bold_style in pairs:
            with self.subTest(plain_style=plain_style, bold_style=bold_style):
                self.assertTrue(is_bold_double_bond_style(bold_style, 2))
                self.assertTrue(is_positionable_double_bond_style(bold_style, 2))
                self.assertEqual(
                    bold_double_style_for_position(plain_style), bold_style
                )
                self.assertEqual(
                    bold_double_style_for_style(plain_style, 2), bold_style
                )
                self.assertEqual(double_position_for_style(bold_style, 2), plain_style)
                self.assertEqual(
                    style_for_double_position(bold_style, 2, plain_style), bold_style
                )
                self.assertEqual(
                    style_for_double_position(plain_style, 2, plain_style), plain_style
                )

        self.assertEqual(normalized_bold_double_style("bold", 2), BOLD_STYLE_DEFAULT)
        self.assertEqual(double_position_for_style("bold", 2), DOUBLE_STYLE_DEFAULT)
        self.assertFalse(is_bold_double_bond_style(BOLD_STYLE_CENTER, 1))
        self.assertFalse(is_positionable_double_bond_style("dotted_double", 2))
        self.assertIsNone(
            style_for_double_position("dotted_double", 2, DOUBLE_STYLE_CENTER)
        )

    def test_double_style_helpers_cover_plain_dotted_and_base_variant_resolution(
        self,
    ) -> None:
        self.assertTrue(is_plain_double_bond_style("single", 2))
        self.assertTrue(is_plain_double_bond_style("double_outer", 2))
        self.assertFalse(is_plain_double_bond_style("double_outer", 1))
        self.assertTrue(is_dotted_double_bond_style("dotted_double_outer", 2))
        self.assertFalse(is_dotted_double_bond_style("dotted_double_outer", 1))

        self.assertEqual(
            normalized_plain_double_style("double_outer", 2), DOUBLE_STYLE_OUTER
        )
        self.assertEqual(
            normalized_plain_double_style("single", 2), DOUBLE_STYLE_DEFAULT
        )
        self.assertEqual(
            dotted_double_variant_for_style("dotted_double", 2),
            DOTTED_DOUBLE_STYLE_DEFAULT,
        )
        self.assertEqual(
            dotted_double_variant_for_style("double_outer", 2),
            DOTTED_DOUBLE_STYLE_OUTER,
        )
        self.assertIsNone(dotted_double_variant_for_style("double_center", 2))
        self.assertIsNone(dotted_double_variant_for_style("single", 1))
        self.assertEqual(
            base_plain_double_style_for_dotted_variant("dotted_double_outer", 2),
            DOUBLE_STYLE_OUTER,
        )
        self.assertEqual(
            base_plain_double_style_for_dotted_variant("double_center", 2),
            DOUBLE_STYLE_DEFAULT,
        )

    def test_cycle_plain_bond_style_covers_single_double_variant_triple_and_fallback_paths(
        self,
    ) -> None:
        self.assertEqual(cycle_plain_bond_style("single", 1), (DOUBLE_STYLE_DEFAULT, 2))
        self.assertEqual(
            cycle_plain_bond_style("double", 2, allow_double_variants=False),
            ("single", 1),
        )
        self.assertEqual(
            cycle_plain_bond_style("double_center", 2), ("double_outer", 2)
        )
        self.assertEqual(cycle_plain_bond_style("double_outer", 2), ("single", 1))
        self.assertEqual(cycle_plain_bond_style("triple", 3), ("single", 1))
        self.assertEqual(cycle_plain_bond_style("wedge", 1), ("single", 1))

    def test_dotted_overlay_uses_short_double_variant_when_available(self) -> None:
        self.assertEqual(
            style_for_existing_bond_overlay("double", 2, "dotted", 1),
            ("dotted_double", 2),
        )
        self.assertEqual(
            style_for_existing_bond_overlay("double_outer", 2, "dotted", 1),
            ("dotted_double_outer", 2),
        )

    def test_dotted_overlay_leaves_centered_double_intact(self) -> None:
        self.assertEqual(
            style_for_existing_bond_overlay("double_center", 2, "dotted", 1),
            ("double_center", 2),
        )
        self.assertEqual(
            style_for_existing_bond_overlay("single", 1, "dotted", 1),
            ("dotted", 1),
        )

    def test_existing_double_single_overlay_promotes_to_triple_and_other_styles_passthrough(
        self,
    ) -> None:
        self.assertEqual(
            style_for_existing_bond_overlay("double", 2, "single", 1),
            ("triple", 3),
        )
        self.assertEqual(
            style_for_existing_bond_overlay("wedge", 1, "hash", 1),
            ("hash", 1),
        )


if __name__ == "__main__":
    unittest.main()
