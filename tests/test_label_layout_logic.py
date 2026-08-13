import unittest

from chemvas.features.annotations import (
    LabelRun,
    attachment_anchor_token,
    attachment_group_at_end,
    hydride_display_text,
    hydride_hydrogen_text,
    parse_atom_label,
    place_hydride_stack,
    place_runs,
    reversed_display_text,
    split_hydride_label,
)


class AttachmentAnchorTokenTest(unittest.TestCase):
    def test_leading_single_letter_token(self):
        self.assertEqual(attachment_anchor_token("CF3", at_end=False), "C")

    def test_leading_two_letter_token(self):
        self.assertEqual(attachment_anchor_token("Ph3P", at_end=False), "Ph")

    def test_trailing_single_letter_token(self):
        self.assertEqual(attachment_anchor_token("Ph3P", at_end=True), "P")

    def test_trailing_two_letter_token(self):
        self.assertEqual(attachment_anchor_token("OMe", at_end=True), "Me")

    def test_trailing_digit_blocks_the_end_anchor(self):
        self.assertIsNone(attachment_anchor_token("CF3", at_end=True))

    def test_charge_sign_blocks_the_end_anchor(self):
        self.assertIsNone(attachment_anchor_token("NH4+", at_end=True))

    def test_lowercase_start_blocks_the_leading_anchor(self):
        self.assertIsNone(attachment_anchor_token("t-Bu", at_end=False))

    def test_lowercase_prefix_still_anchors_at_the_end(self):
        self.assertEqual(attachment_anchor_token("t-Bu", at_end=True), "Bu")

    def test_whole_label_token_keeps_centred_layout(self):
        self.assertIsNone(attachment_anchor_token("Me", at_end=False))
        self.assertIsNone(attachment_anchor_token("N", at_end=True))

    def test_empty_label_has_no_anchor(self):
        self.assertIsNone(attachment_anchor_token("", at_end=False))


class ReversedDisplayTextTest(unittest.TestCase):
    def test_trailing_subscript_group_flips_to_the_front(self):
        self.assertEqual(reversed_display_text("CF3"), "F3C")

    def test_nickname_flip_matches_the_other_typed_order(self):
        self.assertEqual(reversed_display_text("PPh3"), "Ph3P")
        self.assertEqual(reversed_display_text("Ph3P"), "PPh3")

    def test_three_groups_reverse_group_wise(self):
        self.assertEqual(reversed_display_text("CO2Me"), "MeO2C")

    def test_two_letter_tokens_stay_intact(self):
        self.assertEqual(reversed_display_text("OTs"), "TsO")

    def test_formula_style_label_reverses_group_wise(self):
        self.assertEqual(reversed_display_text("C10H21"), "H21C10")

    def test_hyphen_and_lowercase_start_do_not_reverse(self):
        self.assertIsNone(reversed_display_text("t-Bu"))

    def test_charge_sign_does_not_reverse(self):
        self.assertIsNone(reversed_display_text("NH4+"))

    def test_identity_reversals_return_none(self):
        self.assertIsNone(reversed_display_text("Cl"))
        self.assertIsNone(reversed_display_text("Me3"))
        self.assertIsNone(reversed_display_text(""))


class AttachmentGroupAtEndTest(unittest.TestCase):
    def test_subscripted_first_group_puts_the_attachment_last(self):
        self.assertIs(attachment_group_at_end("Ph3P"), True)
        self.assertIs(attachment_group_at_end("F3C"), True)

    def test_subscripted_last_group_puts_the_attachment_first(self):
        self.assertIs(attachment_group_at_end("CF3"), False)
        self.assertIs(attachment_group_at_end("SiMe3"), False)

    def test_hydrogen_end_defers_to_the_heavy_atom(self):
        self.assertIs(attachment_group_at_end("HO"), True)
        self.assertIs(attachment_group_at_end("H3C"), True)
        self.assertIs(attachment_group_at_end("C10H21"), False)

    def test_symmetric_unsubscripted_labels_are_ambiguous(self):
        self.assertIsNone(attachment_group_at_end("OMe"))
        self.assertIsNone(attachment_group_at_end("PhO"))
        self.assertIsNone(attachment_group_at_end("CO2Me"))

    def test_unclean_or_single_group_labels_are_ambiguous(self):
        self.assertIsNone(attachment_group_at_end("t-Bu"))
        self.assertIsNone(attachment_group_at_end("NH4+"))
        self.assertIsNone(attachment_group_at_end("Cl"))
        self.assertIsNone(attachment_group_at_end(""))


class SplitHydrideLabelTest(unittest.TestCase):
    def test_bare_element_has_zero_hydrogens(self):
        self.assertEqual(split_hydride_label("O"), ("O", 0))
        self.assertEqual(split_hydride_label("Cl"), ("Cl", 0))

    def test_single_hydrogen(self):
        self.assertEqual(split_hydride_label("NH"), ("N", 1))
        self.assertEqual(split_hydride_label("OH"), ("O", 1))

    def test_multiple_hydrogens(self):
        self.assertEqual(split_hydride_label("NH2"), ("N", 2))
        self.assertEqual(split_hydride_label("CH3"), ("C", 3))

    def test_non_hydride_labels_return_none(self):
        self.assertIsNone(split_hydride_label("CO2Me"))
        self.assertIsNone(split_hydride_label(""))
        self.assertIsNone(split_hydride_label("NH4+"))


class HydrideDisplayTextTest(unittest.TestCase):
    def test_bare_element_ignores_direction(self):
        self.assertEqual(hydride_display_text("O", 0, face_left=True), "O")
        self.assertEqual(hydride_display_text("O", 0, face_left=False), "O")

    def test_hydrogens_trail_when_facing_right(self):
        self.assertEqual(hydride_display_text("N", 1, face_left=False), "NH")
        self.assertEqual(hydride_display_text("N", 2, face_left=False), "NH2")

    def test_hydrogens_lead_when_facing_left(self):
        self.assertEqual(hydride_display_text("N", 1, face_left=True), "HN")
        self.assertEqual(hydride_display_text("N", 2, face_left=True), "H2N")


class ParseAtomLabelTest(unittest.TestCase):
    def roles(self, text):
        return [(run.text, run.role) for run in parse_atom_label(text)]

    def test_empty_string_has_no_runs(self):
        self.assertEqual(parse_atom_label(""), [])

    def test_single_element_is_one_normal_run(self):
        self.assertEqual(self.roles("N"), [("N", "normal")])

    def test_digit_after_letter_is_subscript(self):
        self.assertEqual(self.roles("CH3"), [("CH", "normal"), ("3", "sub")])

    def test_interior_digit_then_more_text(self):
        self.assertEqual(
            self.roles("CO2Me"),
            [("CO", "normal"), ("2", "sub"), ("Me", "normal")],
        )

    def test_consecutive_digits_stay_in_one_subscript(self):
        self.assertEqual(self.roles("C10"), [("C", "normal"), ("10", "sub")])

    def test_digit_after_closing_paren_is_subscript(self):
        self.assertEqual(
            self.roles("(CH3)2"),
            [("(CH", "normal"), ("3", "sub"), (")", "normal"), ("2", "sub")],
        )

    def test_leading_digit_stays_normal(self):
        # Isotope-style typography is out of scope for this slice.
        self.assertEqual(self.roles("13C"), [("13C", "normal")])

    def test_inline_charge_sign_is_not_superscripted_yet(self):
        # Charge -> superscript folding is deferred; the count still subscripts
        # but the sign stays on the normal baseline for now.
        self.assertEqual(
            self.roles("NH4+"),
            [("NH", "normal"), ("4", "sub"), ("+", "normal")],
        )

    def test_standalone_charge_mark_stays_normal(self):
        # The '+'/'-' charge mark glyphs reuse AtomLabelItem and must not shrink.
        self.assertEqual(self.roles("+"), [("+", "normal")])
        self.assertEqual(self.roles("-"), [("-", "normal")])

    def test_interior_hyphen_is_not_a_charge(self):
        self.assertEqual(self.roles("t-Bu"), [("t-Bu", "normal")])


class PlaceRunsTest(unittest.TestCase):
    def measure(self, text, point_size):
        # Deterministic, Qt-free advance: one unit of width per char per point.
        return len(text) * point_size

    def layout(self, runs):
        return place_runs(
            runs,
            measure=self.measure,
            ascent=8.0,
            descent=2.0,
            base_point_size=10.0,
        )

    def test_empty_runs_layout_is_empty(self):
        layout = self.layout([])
        self.assertEqual(layout.runs, ())
        self.assertEqual(layout.width, 0.0)
        self.assertEqual(layout.height, 0.0)
        self.assertFalse(layout.has_typography)

    def test_normal_only_has_no_typography(self):
        layout = self.layout([LabelRun("N", "normal")])
        self.assertFalse(layout.has_typography)
        self.assertAlmostEqual(layout.width, 10.0)

    def test_subscript_advances_after_base_and_drops_baseline(self):
        layout = self.layout([LabelRun("CH", "normal"), LabelRun("3", "sub")])
        self.assertTrue(layout.has_typography)
        base, sub = layout.runs
        self.assertAlmostEqual(base.x, 0.0)
        self.assertAlmostEqual(sub.x, 20.0)  # "CH" -> 2 chars * 10pt
        self.assertAlmostEqual(sub.point_size, 7.2)  # 10 * SUB_SCALE
        self.assertAlmostEqual(layout.width, 27.2)  # 20 + 1 char * 7.2
        # Subscript sits lower on screen => larger baseline y than the base run.
        self.assertGreater(sub.baseline, base.baseline)

    def test_superscript_rises_above_base_baseline(self):
        layout = self.layout([LabelRun("NH", "normal"), LabelRun("+", "super")])
        base, sup = layout.runs
        self.assertLess(sup.baseline, base.baseline)


class HydrideHydrogenTextTest(unittest.TestCase):
    def test_counts_render_like_the_inline_form(self):
        self.assertEqual(hydride_hydrogen_text(1), "H")
        self.assertEqual(hydride_hydrogen_text(2), "H2")
        self.assertEqual(hydride_hydrogen_text(3), "H3")


class PlaceHydrideStackTest(unittest.TestCase):
    def measure(self, text, point_size):
        # Deterministic, Qt-free advance: one unit of width per char per point.
        return len(text) * point_size

    def stack(self, element, h_count, *, hydrogens_below=True):
        return place_hydride_stack(
            element,
            h_count,
            hydrogens_below=hydrogens_below,
            measure=self.measure,
            ascent=8.0,
            descent=2.0,
            base_point_size=10.0,
        )

    def test_single_hydrogen_stacks_below_the_element(self):
        layout, element_box = self.stack("N", 1)
        self.assertTrue(layout.has_typography)
        self.assertAlmostEqual(layout.width, 10.0)
        self.assertAlmostEqual(layout.height, 20.0)  # two plain 1-em lines
        element_run, hydrogen_run = layout.runs
        self.assertEqual(element_run.text, "N")
        self.assertEqual(hydrogen_run.text, "H")
        self.assertGreater(hydrogen_run.baseline, element_run.baseline)
        self.assertEqual(element_box, (0.0, 0.0, 10.0, 10.0))

    def test_hydrogens_above_put_the_element_on_the_second_line(self):
        layout, element_box = self.stack("N", 1, hydrogens_below=False)
        element_run = next(run for run in layout.runs if run.text == "N")
        hydrogen_run = next(run for run in layout.runs if run.text == "H")
        self.assertLess(hydrogen_run.baseline, element_run.baseline)
        self.assertAlmostEqual(element_box[1], 10.0)  # below the 1-em H line

    def test_lines_are_centred_on_each_other(self):
        # "H2" (H at 10 + subscript 2 at 7.2) is wider than "N", so the element
        # shifts right by half the difference and the hydrogen line starts at 0.
        layout, element_box = self.stack("N", 2)
        self.assertAlmostEqual(layout.width, 17.2)
        self.assertAlmostEqual(element_box[0], 3.6)
        hydrogen_run = next(run for run in layout.runs if run.text == "H")
        self.assertAlmostEqual(hydrogen_run.x, 0.0)


if __name__ == "__main__":
    unittest.main()
