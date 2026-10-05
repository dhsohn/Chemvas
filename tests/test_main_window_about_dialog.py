import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QMainWindow, QPushButton

from chemvas.ui.window.main_window_about_dialog import show_about_dialog


class AboutDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = QMainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_show_about_dialog_presents_identity_and_links(self) -> None:
        captured: dict[str, object] = {}

        def drive_dialog(dialog: QDialog):
            captured["title"] = dialog.windowTitle()
            captured["labels"] = [label.text() for label in dialog.findChildren(QLabel)]
            captured["close"] = next(
                (
                    button
                    for button in dialog.findChildren(QPushButton)
                    if button.text() == "Close"
                ),
                None,
            )
            return QDialog.DialogCode.Accepted

        with mock.patch(
            "chemvas.ui.window.main_window_about_dialog.QDialog.exec", new=drive_dialog
        ):
            show_about_dialog(self.window)

        self.assertEqual(captured["title"], "About Chemvas")
        labels = captured["labels"]
        assert isinstance(labels, list)
        joined = " ".join(labels)
        self.assertIn("Chemvas", labels)
        self.assertIn("Version", joined)
        self.assertIn("MIT", joined)
        self.assertNotIn("RDKit", joined)
        self.assertIn("github.com/dhsohn/Chemvas", joined)
        self.assertIsNotNone(captured["close"])
