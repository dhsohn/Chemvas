import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget

from chemvas.shell.toolbar_buttons import (
    ArrowButton,
    CornerMenuButton,
    CornerMenuToolButton,
)


class MainWindowToolbarButtonsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_corner_menu_tool_button_opens_menu_only_in_bottom_right_corner(
        self,
    ) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        action = QAction("Tool", window)
        triggered = mock.Mock()
        action.triggered.connect(lambda checked=False: triggered())
        button = CornerMenuToolButton(window)
        button.setDefaultAction(action)
        menu = QMenu(button)
        menu.addAction("Arial")
        button.setMenu(menu)
        button.setFixedSize(30, 30)
        button.show()
        self.app.processEvents()

        with mock.patch.object(button, "showMenu") as show_menu:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(27, 27))
            show_menu.assert_called_once()
            triggered.assert_not_called()

        triggered.reset_mock()
        with mock.patch.object(button, "showMenu") as show_menu:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(13, 13))
            show_menu.assert_not_called()
            triggered.assert_called_once()

    def test_custom_buttons_paint(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)

        up_button = ArrowButton("up", owner)
        self.assertTrue(up_button.autoRaise())
        self.assertEqual(up_button.focusPolicy(), Qt.FocusPolicy.NoFocus)

        for widget, size in (
            (up_button, (8, 6)),
            (ArrowButton("down", owner), (20, 20)),
            (CornerMenuButton(owner), (18, 18)),
        ):
            widget.resize(*size)
            widget.show()
            self.app.processEvents()
            pixmap = widget.grab()
            self.assertFalse(pixmap.isNull())
