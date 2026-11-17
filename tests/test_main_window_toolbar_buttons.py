import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMetaObject, QPoint, Qt
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget

from chemvas.shell.toolbar_buttons import (
    ActionToolButton,
    ArrowButton,
    CornerMenuButton,
    CornerMenuToolButton,
)


def cpp_toggle(button: ActionToolButton) -> None:
    QMetaObject.invokeMethod(button, "toggle", Qt.ConnectionType.DirectConnection)


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

    def test_action_tool_button_cpp_toggle_triggers_default_action(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        group = QActionGroup(window)
        group.setExclusive(True)
        bond = QAction("Bond", window)
        bond.setCheckable(True)
        bond.setChecked(True)
        group.addAction(bond)
        ring = QAction("Ring", window)
        ring.setCheckable(True)
        group.addAction(ring)
        ring_button = ActionToolButton(window)
        ring_button.setDefaultAction(ring)
        ring_button.setCheckable(True)
        ring_button.show()
        self.app.processEvents()
        triggered = mock.Mock()
        ring.triggered.connect(lambda checked=False: triggered())
        cpp_toggle(ring_button)
        triggered.assert_called_once()
        self.assertTrue(ring.isChecked())

    def test_action_tool_button_cpp_toggle_while_active_stays_checked(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        group = QActionGroup(window)
        group.setExclusive(True)
        action = QAction("Ring", window)
        action.setCheckable(True)
        group.addAction(action)
        button = ActionToolButton(window)
        button.setDefaultAction(action)
        button.setCheckable(True)
        button.show()
        self.app.processEvents()
        action.trigger()
        triggered = mock.Mock()
        action.triggered.connect(lambda checked=False: triggered())
        cpp_toggle(button)
        triggered.assert_called_once()
        self.assertTrue(action.isChecked())
        self.assertTrue(button.isChecked())
        self.assertIs(group.checkedAction(), action)

    def test_action_tool_button_option_cpp_toggle_emits_clicked_once(self) -> None:
        button = ActionToolButton()
        button.setCheckable(True)
        handler = mock.Mock()
        button.clicked.connect(handler)
        cpp_toggle(button)
        handler.assert_called_once_with(True)

    def test_action_tool_button_cpp_toggle_respects_disabled_parent(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)
        button = ActionToolButton(owner)
        button.setCheckable(True)
        handler = mock.Mock()
        button.clicked.connect(handler)
        owner.setEnabled(False)
        button.show()
        self.app.processEvents()
        cpp_toggle(button)
        handler.assert_not_called()

    def test_action_tool_button_blocked_sync_does_not_trigger_action(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        action = QAction("Ring", window)
        action.setCheckable(True)
        button = ActionToolButton(window)
        button.setDefaultAction(action)
        button.setCheckable(True)
        button.show()
        self.app.processEvents()
        triggered = mock.Mock()
        action.triggered.connect(lambda checked=False: triggered())
        button.blockSignals(True)
        button.setChecked(True)
        button.blockSignals(False)
        triggered.assert_not_called()

    def test_action_tool_button_space_triggers_default_action_once(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        action = QAction("Ring", window)
        action.setCheckable(True)
        button = ActionToolButton(window)
        button.setDefaultAction(action)
        button.setCheckable(True)
        button.show()
        self.app.processEvents()
        button.setFocus()
        triggered = mock.Mock()
        action.triggered.connect(lambda checked=False: triggered())
        QTest.keyClick(button, Qt.Key.Key_Space)
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
