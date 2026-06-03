import unittest

from ui.label_layout_logic import (
    LabelRun,
    parse_atom_label,
    place_runs,
)


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


if __name__ == "__main__":
    unittest.main()
