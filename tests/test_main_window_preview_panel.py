import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QWidget

from chemvas.ui.main_window_preview_window import build_preview_window


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preview_widget = QWidget()
        self.preview_widget.pause_updates = mock.Mock()


class MainWindowPreviewPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_preview_window_wraps_preview_widget_and_hides_on_close(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_preview_window(
            window,
            preview_widget=window.preview_widget,
            panel_bar=QToolBar(window),
        )

        self.assertIs(window.preview_widget.parent(), assembly.preview_window.widget())
        self.assertEqual(assembly.preview_window.windowTitle(), "Molecule Info")
        self.assertEqual(assembly.preview_window.objectName(), "inspectorDock")
        self.assertIsNone(
            assembly.preview_window.findChild(QWidget, "preview_export_xyz_button")
        )
        window.show()
        assembly.preview_window.show()
        self.app.processEvents()
        self.assertTrue(assembly.preview_window.isVisible())

        self.assertTrue(assembly.preview_window.close())
        self.app.processEvents()
        self.assertFalse(assembly.preview_window.isVisible())
        self.assertTrue(window.preview_widget.pause_updates.called)
