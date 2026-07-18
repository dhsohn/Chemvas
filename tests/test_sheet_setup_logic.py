import unittest

from chemvas.ui.sheet_setup_logic import (
    normalize_sheet_orientation,
    normalize_sheet_setup,
    normalize_sheet_size,
    sheet_dimensions_px,
    supported_sheet_orientations,
    supported_sheet_sizes,
)


class SheetSetupLogicTest(unittest.TestCase):
    def test_supported_sheet_setup_defaults_to_a4_landscape(self) -> None:
        self.assertEqual(supported_sheet_sizes(), ("A4",))
        self.assertEqual(supported_sheet_orientations(), ("landscape", "portrait"))
        self.assertEqual(normalize_sheet_size("a4"), "A4")
        self.assertEqual(normalize_sheet_size("unknown"), "A4")
        self.assertEqual(normalize_sheet_orientation("portrait"), "portrait")
        self.assertEqual(normalize_sheet_orientation("vertical"), "portrait")
        self.assertEqual(normalize_sheet_orientation("weird"), "landscape")
        self.assertEqual(normalize_sheet_setup("a4", "horizontal"), ("A4", "landscape"))

    def test_sheet_dimensions_follow_orientation(self) -> None:
        self.assertEqual(sheet_dimensions_px("A4", "landscape"), (842.0, 595.0))
        self.assertEqual(sheet_dimensions_px("A4", "portrait"), (595.0, 842.0))


if __name__ == "__main__":
    unittest.main()
