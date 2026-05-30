import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QActionGroup, QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_tool_action_service import MainWindowToolActionService


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.canvas = SimpleNamespace(set_mark_kind=mock.Mock())
        self._set_tool_with_status = mock.Mock()
        self._set_bond_style = mock.Mock()
        self._refresh_status_context = mock.Mock()

    def _show_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _new_tool_action(self, label: str):
        from PyQt6.QtGui import QAction

        return QAction(label, self)

    def _blank_icon(self):
        return QIcon()

    _icon_select = _blank_icon
    _icon_bond = _blank_icon
    _icon_text = _blank_icon
    _icon_ring = _blank_icon
    _icon_arrow = _blank_icon
    _icon_ts_bracket = _blank_icon
    _icon_perspective = _blank_icon
    _icon_bond_bold = _blank_icon
    _icon_bond_wedge = _blank_icon
    _icon_bond_hash = _blank_icon
    _icon_bond_dotted = _blank_icon
    _icon_mark_plus = _blank_icon
    _icon_mark_minus = _blank_icon
    _icon_mark_radical = _blank_icon


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tool action tests")
class MainWindowToolActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.service = MainWindowToolActionService()
        self.window = _HarnessWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_build_checkable_tool_action_uses_late_bound_icon_wrapper(self) -> None:
        tool_group = QActionGroup(self.window)
        callback = mock.Mock()

        with mock.patch.object(self.window, "_icon_select", return_value=QIcon()) as icon_method:
            _, action = self.service.build_checkable_tool_action(
                self.window,
                tool_group,
                key="select",
                label="Select",
                icon_method="_icon_select",
                tooltip="Pick atoms",
                callback=callback,
            )

        icon_method.assert_called_once_with()
        self.assertEqual(action.toolTip(), "Pick atoms")
        self.assertEqual(action.statusTip(), "Pick atoms")
        self.assertTrue(action.isCheckable())
        action.trigger()
        callback.assert_called_once_with()

    def test_activate_bond_style_tool_selects_bond_and_applies_style(self) -> None:
        self.service.activate_bond_style_tool(self.window, "Hash")

        self.window._set_tool_with_status.assert_called_once_with("bond", reset_bond_style=False)
        self.window._set_bond_style.assert_called_once_with("Hash")

    def test_activate_mark_tool_updates_canvas_and_status_message(self) -> None:
        self.service.activate_mark_tool(self.window, "minus")

        self.window.canvas.set_mark_kind.assert_called_once_with("minus")
        self.assertEqual(self.window.statusBar().currentMessage(), "Mark Tool")

    def test_build_tool_actions_wires_tool_bond_and_mark_callbacks(self) -> None:
        actions = self.service.build_tool_actions(self.window, QActionGroup(self.window))

        actions["select"].trigger()
        actions["bond_hash"].trigger()
        actions["mark_minus"].trigger()

        self.window._set_tool_with_status.assert_any_call("select")
        self.window._set_tool_with_status.assert_any_call("bond", reset_bond_style=False)
        self.window._set_bond_style.assert_called_once_with("Hash")
        self.window.canvas.set_mark_kind.assert_called_once_with("minus")


if __name__ == "__main__":
    unittest.main()
