from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
except ModuleNotFoundError:
    QApplication = None
    QMainWindow = None
    QTabWidget = None

if QApplication is not None:
    from chemvas.ui.main_window_tab_setup import build_canvas_tab_assembly


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for tab setup tests")
class MainWindowTabSetupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_canvas_tab_assembly_wires_document_tab_controls(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        assembly = build_canvas_tab_assembly(
            window,
            on_canvas_tab_moved=mock.Mock(),
            on_canvas_tab_changed=mock.Mock(),
            on_canvas_tab_close_requested=mock.Mock(),
        )

        self.assertEqual(assembly.canvas_tabs.objectName(), "canvasTabs")
        self.assertIs(assembly.canvas_tabs.parent(), window)
        self.assertFalse(hasattr(assembly, "sheet_add_tab"))
        self.assertEqual(
            assembly.canvas_tabs.tabPosition(), QTabWidget.TabPosition.South
        )
        self.assertFalse(assembly.canvas_tabs.documentMode())
        self.assertTrue(assembly.canvas_tabs.isMovable())
        self.assertTrue(assembly.canvas_tabs.tabsClosable())
        self.assertFalse(assembly.canvas_tabs.tabBar().expanding())
        self.assertFalse(assembly.canvas_tabs.tabBar().drawBase())
        self.assertTrue(assembly.canvas_tabs.tabBar().isHidden())


if __name__ == "__main__":
    unittest.main()
