import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_toolbar_buttons import (
        ArrowButton,
        CornerMenuButton,
        CornerMenuToolButton,
        MainWindowToolbarButtonFactory,
    )


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for toolbar button tests"
)
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

    def test_custom_buttons_paint(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)

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
