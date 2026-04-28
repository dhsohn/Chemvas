import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.main_window_path_logic import resolve_load_path, resolve_save_as_path, resolve_save_path


class MainWindowPathLogicTest(unittest.TestCase):
    def test_resolve_save_path_reuses_current_path_without_normalizing_extension(self) -> None:
        self.assertEqual(
            resolve_save_path(current_path="/tmp/current", dialog_path="/tmp/ignored.json"),
            "/tmp/current",
        )

    def test_resolve_save_path_appends_default_extension_for_extensionless_dialog_path(self) -> None:
        self.assertEqual(
            resolve_save_path(dialog_path="/tmp/example"),
            "/tmp/example.chemvas",
        )

    def test_resolve_save_path_preserves_explicit_dialog_extension(self) -> None:
        self.assertEqual(
            resolve_save_path(dialog_path="/tmp/example.json"),
            "/tmp/example.json",
        )

    def test_resolve_save_path_returns_none_when_save_dialog_is_cancelled(self) -> None:
        self.assertIsNone(resolve_save_path(dialog_path=""))
        self.assertIsNone(resolve_save_path(dialog_path=None))

    def test_resolve_save_as_path_appends_default_extension_for_extensionless_dialog_path(self) -> None:
        self.assertEqual(
            resolve_save_as_path("/tmp/example"),
            "/tmp/example.chemvas",
        )

    def test_resolve_save_as_path_preserves_explicit_dialog_extension(self) -> None:
        self.assertEqual(
            resolve_save_as_path("/tmp/example.json"),
            "/tmp/example.json",
        )

    def test_resolve_save_as_path_returns_none_when_save_dialog_is_cancelled(self) -> None:
        self.assertIsNone(resolve_save_as_path(""))
        self.assertIsNone(resolve_save_as_path(None))

    def test_resolve_load_path_returns_selected_path(self) -> None:
        self.assertEqual(resolve_load_path("/tmp/drawing.chemvas"), "/tmp/drawing.chemvas")

    def test_resolve_load_path_returns_none_when_load_dialog_is_cancelled(self) -> None:
        self.assertIsNone(resolve_load_path(""))
        self.assertIsNone(resolve_load_path(None))


if __name__ == "__main__":
    unittest.main()
