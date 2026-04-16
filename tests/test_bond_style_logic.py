import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.bond_style_logic import style_for_existing_bond_overlay


class BondStyleLogicTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
