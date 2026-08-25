import unittest

from chemvas.ui.main_window_toolbar_logic import (
    arrow_preset_from_label,
    arrow_type_from_label,
    bond_style_from_label,
    orbital_type_from_label,
    tool_action_key_for_canvas_state,
    tool_display_name,
)


class MainWindowToolbarLogicTest(unittest.TestCase):
    def test_mapping_helpers_use_expected_defaults(self) -> None:
        self.assertEqual(bond_style_from_label("Bold"), ("bold_in", 1))
        self.assertEqual(bond_style_from_label("Unknown"), ("single", 1))
        self.assertEqual(arrow_type_from_label("Curved Double"), "curved_double")
        self.assertEqual(arrow_type_from_label("Unknown"), "reaction")
        self.assertEqual(orbital_type_from_label("sp2"), "sp2")
        self.assertEqual(orbital_type_from_label("Unknown"), "s")
        self.assertEqual(arrow_preset_from_label("Bold"), (2.2, 0.4))
        self.assertEqual(arrow_preset_from_label("Unknown"), (1.2, 0.3))
        self.assertEqual(tool_display_name("text"), "Atom")
        self.assertEqual(tool_display_name("note"), "Text")
        self.assertEqual(tool_display_name("benzene"), "Ring")
        self.assertEqual(tool_display_name("mystery"), "Mystery")

    def test_tool_action_key_for_canvas_state_handles_bond_mark_and_regular_tools(
        self,
    ) -> None:
        self.assertEqual(tool_action_key_for_canvas_state("bond"), "bond")
        self.assertEqual(tool_action_key_for_canvas_state("mark"), "mark")
        self.assertEqual(tool_action_key_for_canvas_state("perspective"), "perspective")
        self.assertIsNone(tool_action_key_for_canvas_state(None))


if __name__ == "__main__":
    unittest.main()
