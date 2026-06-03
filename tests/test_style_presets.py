import unittest

from core.style_acs1996 import ACS1996Style
from core.style_presets import (
    DEFAULT_PRESET,
    apply_preset_to_current,
    preset_names,
    style_for_preset,
)


class StylePresetsTest(unittest.TestCase):
    def test_default_preset_is_listed_first(self):
        names = preset_names()
        self.assertEqual(names[0], DEFAULT_PRESET)
        self.assertIn("Nature / RSC", names)
        self.assertIn("Presentation", names)

    def test_default_preset_matches_acs_defaults(self):
        self.assertEqual(style_for_preset(DEFAULT_PRESET), ACS1996Style())

    def test_unknown_preset_falls_back_to_default(self):
        self.assertEqual(style_for_preset("does-not-exist"), style_for_preset(DEFAULT_PRESET))

    def test_presets_differ_in_metrics(self):
        acs = style_for_preset("ACS 1996")
        presentation = style_for_preset("Presentation")
        self.assertGreater(presentation.bond_line_width, acs.bond_line_width)
        self.assertGreater(presentation.bond_length_pt, acs.bond_length_pt)

    def test_apply_preset_keeps_current_bond_length_px(self):
        current = ACS1996Style(bond_length_px=37.0)
        applied = apply_preset_to_current("Presentation", current)
        # On-screen working size is preserved...
        self.assertEqual(applied.bond_length_px, 37.0)
        # ...while the preset's print metrics are adopted.
        self.assertEqual(applied.bond_length_pt, style_for_preset("Presentation").bond_length_pt)
        self.assertEqual(applied.font_size_pt, style_for_preset("Presentation").font_size_pt)


if __name__ == "__main__":
    unittest.main()
