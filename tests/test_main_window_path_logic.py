import unittest
from pathlib import Path

from chemvas.ui.window.main_window_path_logic import (
    is_desktop_document_path,
    is_recent_document_path,
    resolve_load_path,
    resolve_save_as_path,
    resolve_save_path,
)


class MainWindowPathLogicTest(unittest.TestCase):
    def test_resolve_save_path_reuses_current_path_without_normalizing_extension(
        self,
    ) -> None:
        self.assertEqual(resolve_save_path(current_path="/tmp/current"), "/tmp/current")

    def test_resolve_save_as_path_appends_default_extension_for_extensionless_dialog_path(
        self,
    ) -> None:
        self.assertEqual(
            resolve_save_as_path("/tmp/example"),
            str(Path("/tmp/example.cdxml")),
        )

    def test_resolve_save_as_path_replaces_noncanonical_extension(self) -> None:
        self.assertEqual(
            resolve_save_as_path("/tmp/example.custom"),
            str(Path("/tmp/example.cdxml")),
        )

    def test_resolve_save_as_path_returns_none_when_save_dialog_is_cancelled(
        self,
    ) -> None:
        self.assertIsNone(resolve_save_as_path(""))
        self.assertIsNone(resolve_save_as_path(None))

    def test_resolve_load_path_returns_selected_path(self) -> None:
        self.assertEqual(resolve_load_path("/tmp/drawing.cdxml"), "/tmp/drawing.cdxml")

    def test_resolve_load_path_returns_none_when_load_dialog_is_cancelled(self) -> None:
        self.assertIsNone(resolve_load_path(""))
        self.assertIsNone(resolve_load_path(None))

    def test_only_cdxml_and_mol_are_openable_and_only_cdxml_is_recent(self) -> None:
        for suffix, openable, recent in (
            (".cdxml", True, True),
            (".mol", True, False),
            (".svg", False, False),
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(is_desktop_document_path("figure" + suffix), openable)
                self.assertEqual(is_recent_document_path("figure" + suffix), recent)
