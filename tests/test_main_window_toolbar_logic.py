import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.main_window_toolbar_logic import (
    arrow_preset_from_label,
    arrow_type_from_label,
    bond_style_from_label,
    build_template_entries,
    orbital_type_from_label,
    tool_action_key_for_canvas_state,
    tool_display_name,
)


class MainWindowToolbarLogicTest(unittest.TestCase):
    def test_build_template_entries_preserves_ring_size_and_style(self) -> None:
        calls: list[tuple[int, str]] = []
        entries = dict(
            build_template_entries(
                lambda ring_size, *, style: calls.append((ring_size, style))
            )
        )

        entries["Cyclopropane"]()
        entries["Cycloheptane"]()
        entries["Cyclooctane"]()
        entries["Cyclohexane (Chair)"]()

        self.assertEqual(calls, [(3, "regular"), (7, "regular"), (8, "regular"), (6, "chair")])

    def test_mapping_helpers_use_expected_defaults(self) -> None:
        self.assertEqual(bond_style_from_label("Bold"), ("bold_in", 1))
        self.assertEqual(bond_style_from_label("Unknown"), ("single", 1))
        self.assertEqual(arrow_type_from_label("Curved Double"), "curved_double")
        self.assertEqual(arrow_type_from_label("Unknown"), "reaction")
        self.assertEqual(orbital_type_from_label("sp2"), "sp2")
        self.assertEqual(orbital_type_from_label("Unknown"), "s")
        self.assertEqual(arrow_preset_from_label("Bold"), (2.2, 0.4))
        self.assertEqual(arrow_preset_from_label("Unknown"), (1.2, 0.3))
        self.assertEqual(tool_display_name("text"), "Atom / Text")
        self.assertEqual(tool_display_name("mystery"), "Mystery")

    def test_tool_action_key_for_canvas_state_handles_bond_mark_and_regular_tools(self) -> None:
        self.assertEqual(
            tool_action_key_for_canvas_state(
                "bond",
                active_bond_style="hash",
                mark_kind="plus",
            ),
            "bond_hash",
        )
        self.assertEqual(
            tool_action_key_for_canvas_state(
                "bond",
                active_bond_style="bold_out",
                mark_kind="plus",
            ),
            "bond_bold",
        )
        self.assertEqual(
            tool_action_key_for_canvas_state(
                "mark",
                active_bond_style="single",
                mark_kind="minus",
            ),
            "mark_minus",
        )
        self.assertEqual(
            tool_action_key_for_canvas_state(
                "perspective",
                active_bond_style="single",
                mark_kind="plus",
            ),
            "perspective",
        )
        self.assertIsNone(
            tool_action_key_for_canvas_state(
                None,
                active_bond_style="single",
                mark_kind="plus",
            )
        )


if __name__ == "__main__":
    unittest.main()
