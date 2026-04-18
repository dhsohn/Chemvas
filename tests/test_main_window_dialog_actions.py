import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tests")
class MainWindowDialogActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_open_arrow_settings_delegates_to_ui_assembly_service(self) -> None:
        service = mock.Mock()
        self.window._ui_assembly_service = service

        self.window._open_arrow_settings()

        service.open_arrow_settings.assert_called_once_with(self.window)

    def test_set_bond_length_delegates_to_document_action_service(self) -> None:
        service = mock.Mock()
        self.window._document_action_service = service

        self.window._set_bond_length()

        service.set_bond_length.assert_called_once_with(self.window)


if __name__ == "__main__":
    unittest.main()
