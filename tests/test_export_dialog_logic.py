import unittest

from chemvas.features.export import (
    default_export_path,
    file_filter_for_format,
    is_dpi_relevant,
    is_raster_format,
    normalize_export_path,
    suffix_for_format,
)


class ExportDialogLogicTest(unittest.TestCase):
    def test_raster_classification(self):
        self.assertTrue(is_raster_format("png"))
        self.assertTrue(is_raster_format("TIFF"))
        self.assertFalse(is_raster_format("svg"))
        self.assertFalse(is_raster_format("pdf"))

    def test_dpi_relevance_includes_pdf_and_raster_only(self):
        self.assertTrue(is_dpi_relevant("png"))
        self.assertTrue(is_dpi_relevant("pdf"))
        self.assertFalse(is_dpi_relevant("svg"))

    def test_suffix_and_filter(self):
        self.assertEqual(suffix_for_format("pdf"), ".pdf")
        self.assertIn("*.png", file_filter_for_format("png"))
        self.assertTrue(file_filter_for_format("svg").endswith("All Files (*)"))

    def test_normalize_adds_missing_suffix(self):
        self.assertEqual(normalize_export_path("/tmp/figure", "png"), "/tmp/figure.png")
        self.assertEqual(normalize_export_path("/tmp/figure", "pdf"), "/tmp/figure.pdf")

    def test_normalize_keeps_explicit_suffix(self):
        self.assertEqual(
            normalize_export_path("/tmp/figure.tiff", "png"), "/tmp/figure.tiff"
        )

    def test_normalize_blank_is_none(self):
        self.assertIsNone(normalize_export_path("", "svg"))
        self.assertIsNone(normalize_export_path(None, "svg"))

    def test_default_export_path_swaps_suffix(self):
        self.assertEqual(
            default_export_path("/work/mol.chemvas", "pdf"), "/work/mol.pdf"
        )
        self.assertEqual(default_export_path("", "pdf"), "")


if __name__ == "__main__":
    unittest.main()
