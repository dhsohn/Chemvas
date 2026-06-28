import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QToolButton, QWidget
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_toolbar_buttons import (
        ArrowButton,
        CornerMenuButton,
        CornerMenuToolButton,
        MainWindowToolbarButtonFactory,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for toolbar button tests")
class MainWindowToolbarButtonsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def _filled_icon(self) -> QIcon:
        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.GlobalColor.black)
        return QIcon(pixmap)

    def test_corner_menu_tool_button_opens_menu_only_in_bottom_right_corner(self) -> None:
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

    def test_create_toolbar_button_sets_properties_and_callback(self) -> None:
        callback = mock.Mock()
        shortcut = QKeySequence("Ctrl+L")
        factory = MainWindowToolbarButtonFactory()

        button = factory.create_toolbar_button(
            icon=QIcon(),
            tooltip="Load",
            callback=callback,
            shortcut=shortcut,
            text="Load",
            object_name="load_button",
            style_sheet="color: red;",
            auto_raise=False,
            cursor=Qt.CursorShape.PointingHandCursor,
        )

        self.assertEqual(button.toolTip(), "Load")
        self.assertEqual(button.statusTip(), "Load")
        self.assertEqual(button.text(), "Load")
        self.assertEqual(button.objectName(), "load_button")
        self.assertEqual(button.styleSheet(), "color: red;")
        self.assertFalse(button.autoRaise())
        self.assertEqual(button.cursor().shape(), Qt.CursorShape.PointingHandCursor)

        button.click()
        callback.assert_called_once_with(False)

    def test_corner_and_file_menu_buttons_build_menus(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        factory = MainWindowToolbarButtonFactory()
        save_action = QAction("Save", owner)
        save_as_action = QAction("Save As...", owner)
        load_action = QAction("Load", owner)
        export_action = QAction("Export Figure...", owner)

        save_button = factory.create_save_menu_button(save_action, save_as_action)
        file_button = factory.create_file_project_menu_button(
            save_action,
            load_action,
            save_as_action,
            export_action,
        )

        self.assertIs(save_button.defaultAction(), save_action)
        self.assertEqual(save_button.menu().actions(), [save_as_action])
        self.assertIs(file_button.defaultAction(), save_action)
        non_separator = [action for action in file_button.menu().actions() if not action.isSeparator()]
        self.assertEqual(non_separator, [load_action, save_action, save_as_action, export_action])
        self.assertEqual(sum(1 for action in file_button.menu().actions() if action.isSeparator()), 1)

    def test_custom_buttons_paint_and_corner_menu_allows_no_default_action(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)
        factory = MainWindowToolbarButtonFactory()
        icon = self._filled_icon()

        corner_button = factory.create_corner_menu_button(
            icon=icon,
            tooltip="Palette",
            style_sheet="padding: 1px;",
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=lambda menu: menu.addAction("Pick"),
        )
        self.assertIsInstance(corner_button, CornerMenuButton)
        self.assertIsNone(corner_button.defaultAction())
        self.assertFalse(corner_button.icon().isNull())
        self.assertEqual([action.text() for action in corner_button.menu().actions()], ["Pick"])

        for widget, size in (
            (ArrowButton("up", owner), (8, 6)),
            (ArrowButton("down", owner), (20, 20)),
            (CornerMenuButton(owner), (18, 18)),
        ):
            widget.resize(*size)
            widget.show()
            self.app.processEvents()
            pixmap = widget.grab()
            self.assertFalse(pixmap.isNull())


if __name__ == "__main__":
    unittest.main()
