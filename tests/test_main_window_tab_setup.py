from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
except ModuleNotFoundError:
    QApplication = None
    QSize = None
    QMainWindow = None
    QTabWidget = None

if QApplication is not None:
    from ui.main_window_tab_setup import SheetTabBar, build_canvas_tab_assembly


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for tab setup tests")
class MainWindowTabSetupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_sheet_tab_bar_uses_compact_plus_tab_size(self) -> None:
        tab_bar = SheetTabBar()
        self.addCleanup(tab_bar.close)
        tab_bar.addTab("Sheet 1")
        tab_bar.addTab("+")

        normal_hint = tab_bar.tabSizeHint(0)
        tab_bar.set_add_tab_index(1)
        plus_hint = tab_bar.tabSizeHint(1)

        self.assertIsInstance(normal_hint, QSize)
        self.assertEqual(plus_hint.width(), 28)
        self.assertEqual(plus_hint.height(), normal_hint.height())
        self.assertFalse(tab_bar.expanding())
        self.assertFalse(tab_bar.drawBase())

    def test_build_canvas_tab_assembly_wires_window_tab_controls(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        assembly = build_canvas_tab_assembly(
            window,
            show_canvas_tab_context_menu=mock.Mock(),
            on_canvas_tab_moved=mock.Mock(),
            on_canvas_tab_changed=mock.Mock(),
        )

        self.assertEqual(assembly.canvas_tabs.objectName(), "canvasTabs")
        self.assertIs(assembly.canvas_tabs.parent(), window)
        self.assertIs(assembly.sheet_add_tab.parent(), window)
        self.assertIs(assembly.canvas_tabs.tabBar(), assembly.sheet_tab_bar)
        self.assertIsInstance(assembly.sheet_tab_bar, SheetTabBar)
        self.assertFalse(assembly.sheet_tab_bar.expanding())
        self.assertFalse(assembly.sheet_tab_bar.drawBase())
        self.assertEqual(assembly.canvas_tabs.tabPosition(), QTabWidget.TabPosition.South)
        self.assertFalse(assembly.canvas_tabs.documentMode())
        self.assertTrue(assembly.canvas_tabs.isMovable())
        self.assertFalse(assembly.canvas_tabs.tabsClosable())


if __name__ == "__main__":
    unittest.main()
