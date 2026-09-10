import errno
import unittest
from pathlib import Path

from chemvas.features.export import (
    default_export_path,
    export_error_message,
    file_filter_for_format,
    is_dpi_relevant,
    is_raster_format,
    normalize_export_path,
    suffix_for_format,
    supports_minimum_font_check,
)


class ExportDialogLogicTest(unittest.TestCase):
    def test_minimum_font_check_is_whole_canvas_svg_png_only(self):
        for fmt in ("svg", "png", "SVG", "PNG"):
            self.assertTrue(supports_minimum_font_check(fmt, "sheet"))
            self.assertFalse(supports_minimum_font_check(fmt, "selection"))
        for fmt in ("pdf", "tiff", "unknown"):
            self.assertFalse(supports_minimum_font_check(fmt, "sheet"))

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
        self.assertEqual(
            normalize_export_path("/tmp/figure", "png"), str(Path("/tmp/figure.png"))
        )
        self.assertEqual(
            normalize_export_path("/tmp/figure", "pdf"), str(Path("/tmp/figure.pdf"))
        )

    def test_normalize_keeps_a_suffix_the_format_accepts(self):
        self.assertEqual(
            normalize_export_path("/tmp/figure.tif", "tiff"),
            str(Path("/tmp/figure.tif")),
        )
        self.assertEqual(
            normalize_export_path("/tmp/figure.PNG", "png"),
            str(Path("/tmp/figure.PNG")),
        )

    def test_normalize_retargets_another_formats_suffix(self):
        # Writing SVG bytes into "figure.pdf" left a file whose name lied about
        # its contents to every other program.
        self.assertEqual(
            normalize_export_path("/tmp/figure.pdf", "svg"),
            str(Path("/tmp/figure.svg")),
        )
        self.assertEqual(
            normalize_export_path("/tmp/figure.tiff", "png"),
            str(Path("/tmp/figure.png")),
        )

    def test_normalize_keeps_a_suffix_that_names_no_format(self):
        # "scheme.v2" is a filename the user chose, not a format claim.
        self.assertEqual(
            normalize_export_path("/tmp/scheme.v2", "svg"),
            str(Path("/tmp/scheme.v2")),
        )

    def test_normalize_blank_is_none(self):
        self.assertIsNone(normalize_export_path("", "svg"))
        self.assertIsNone(normalize_export_path(None, "svg"))

    def test_filesystem_failures_explain_the_destination(self):
        missing = FileNotFoundError(errno.ENOENT, "No such file or directory")
        message = export_error_message(missing)
        self.assertIn("destination folder does not exist", message)
        self.assertIn("No file was written", message)

        denied = PermissionError(errno.EACCES, "Permission denied")
        self.assertIn("permission", export_error_message(denied))

        full = OSError(errno.ENOSPC, "No space left on device")
        self.assertIn("disk is full", export_error_message(full).lower())

    def test_filesystem_failures_hide_the_staging_path(self):
        # Exports stage through a temporary sibling file; naming it told the
        # user about a path they never chose and which no longer exists.
        staged = FileNotFoundError(
            errno.ENOENT,
            "No such file or directory",
            "/figures/out.pdf.p06982tm.tmp",
        )
        message = export_error_message(staged)
        self.assertNotIn(".tmp", message)
        self.assertNotIn("Errno", message)

    def test_unknown_oserror_keeps_the_system_reason_without_errno_text(self):
        message = export_error_message(OSError(errno.EIO, "Input/output error"))
        self.assertIn("Input/output error", message)
        self.assertNotIn("Errno", message)
        self.assertIn("Choose another location", message)

    def test_errno_less_oserror_keeps_its_own_message(self):
        message = export_error_message(OSError("Unsupported export format"))
        self.assertIn("Unsupported export format", message)

    def test_default_export_path_swaps_suffix(self):
        self.assertEqual(
            default_export_path("/work/mol.chemvas", "pdf"),
            str(Path("/work/mol.pdf")),
        )
        self.assertEqual(default_export_path("", "pdf"), "")
