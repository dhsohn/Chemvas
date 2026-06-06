import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QApplication, QMainWindow
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_config import LEFT_TOOLBAR_ACTION_ORDER
    from ui.main_window_left_toolbar import build_left_toolbar
    from ui.main_window_theme import TOOLBAR_THICKNESS


class _HarnessWindow(QMainWindow):
    pass


def _build_tool_actions(window, tool_group) -> dict[str, QAction]:
    actions: dict[str, QAction] = {}
    for key in LEFT_TOOLBAR_ACTION_ORDER:
        action = QAction(key, window)
        action.setCheckable(True)
        tool_group.addAction(action)
        actions[key] = action
    return actions


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for left toolbar tests")
class MainWindowLeftToolbarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_left_toolbar_creates_compact_grouped_tool_actions(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_left_toolbar(window, build_tool_actions=_build_tool_actions)
        actions = [action for action in assembly.left_bar.actions() if not action.isSeparator()]

        self.assertEqual([action.text() for action in actions], LEFT_TOOLBAR_ACTION_ORDER)
        self.assertEqual(
            sum(1 for action in assembly.left_bar.actions() if action.isSeparator()),
            3,
        )
        self.assertEqual(assembly.left_bar.iconSize().width(), 18)
        self.assertEqual(assembly.left_bar.iconSize().height(), 18)
        self.assertEqual(assembly.left_bar.maximumWidth(), TOOLBAR_THICKNESS)
        self.assertTrue(assembly.tool_actions["bond"].isChecked())
        self.assertTrue(actions[0].actionGroup().isExclusive())
        for action_key in ("select", "perspective"):
            with self.subTest(action_key=action_key):
                action = assembly.tool_actions[action_key]
                widget = assembly.left_bar.widgetForAction(action)
                self.assertIsNotNone(widget)
                self.assertEqual(widget.objectName(), f"leftToolButton_{action_key}")
                self.assertEqual(widget.toolButtonStyle(), assembly.left_bar.toolButtonStyle())
                self.assertEqual(widget.iconSize(), assembly.left_bar.iconSize())


if __name__ == "__main__":
    unittest.main()
