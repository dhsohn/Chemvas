import unittest

from chemvas.ui.window.main_window_toolbar_logic import (
    arrow_preset_from_label,
    bond_style_from_label,
    orbital_type_from_label,
    tool_display_name,
)


class MainWindowToolbarLogicTest(unittest.TestCase):
    def test_mapping_helpers_use_expected_defaults(self) -> None:
        self.assertEqual(bond_style_from_label("Bold"), ("bold_in", 1))
        self.assertEqual(bond_style_from_label("Unknown"), ("single", 1))
        self.assertEqual(orbital_type_from_label("sp2"), "sp2")
        self.assertEqual(orbital_type_from_label("Unknown"), "s")
        self.assertEqual(arrow_preset_from_label("Bold"), (2.2, 0.4))
        self.assertEqual(arrow_preset_from_label("Unknown"), (1.5, 0.3))
        self.assertEqual(tool_display_name("text"), "Atom")
        self.assertEqual(tool_display_name("note"), "Text")
        self.assertEqual(tool_display_name("benzene"), "Ring")
        self.assertEqual(tool_display_name("mystery"), "Mystery")
