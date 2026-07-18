import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QActionGroup, QIcon, QPixmap
    from PyQt6.QtWidgets import QApplication, QMainWindow
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_tool_action_service import MainWindowToolActionService


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.tool_mode_controller = SimpleNamespace(set_mark_kind=mock.Mock())
        self.canvas = SimpleNamespace(
            services=SimpleNamespace(tool_mode_controller=self.tool_mode_controller)
        )
        self._icon_factory = SimpleNamespace(
            icon_select=self._blank_icon,
            icon_bond=self._blank_icon,
            icon_text=self._blank_icon,
            icon_note=self._blank_icon,
            icon_mark=self._blank_icon,
            icon_ring=self._blank_icon,
            icon_arrow=self._blank_icon,
            icon_ts_bracket=self._blank_icon,
            icon_shape=self._blank_icon,
            icon_perspective=self._blank_icon,
            icon_color=self._blank_icon,
            icon_ring_fill=self._blank_icon,
            icon_orbital=self._blank_icon,
            icon_bond_bold=self._blank_icon,
            icon_bond_wedge=self._blank_icon,
            icon_bond_hash=self._blank_icon,
            icon_bond_dotted=self._blank_icon,
            icon_mark_plus=self._blank_icon,
            icon_mark_minus=self._blank_icon,
            icon_mark_radical=self._blank_icon,
        )

    def show_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _blank_icon(self):
        return QIcon()


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for main window tool action tests"
)
class MainWindowToolActionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = _HarnessWindow()
        self.tool_mode_controller_for_window = mock.Mock(
            return_value=self.window.tool_mode_controller
        )
        self.tool_state_service = mock.Mock()
        self.context_page_state_service = mock.Mock()
        self.icon_factory_for_window = mock.Mock(return_value=self.window._icon_factory)
        self.status_service = mock.Mock()
        self.service = MainWindowToolActionService(
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            tool_state_service=self.tool_state_service,
            context_page_state_service=self.context_page_state_service,
            icon_factory_for_window=self.icon_factory_for_window,
            status_service=self.status_service,
        )

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_build_checkable_tool_action_uses_late_bound_icon_factory(self) -> None:
        tool_group = QActionGroup(self.window)
        callback = mock.Mock()
        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.GlobalColor.black)
        icon = QIcon(pixmap)

        with mock.patch.object(
            self.icon_factory_for_window.return_value, "icon_select", return_value=icon
        ) as icon_method:
            _, action = self.service.build_checkable_tool_action(
                self.window,
                tool_group,
                key="select",
                label="Select",
                icon_method="icon_select",
                tooltip="Pick atoms",
                callback=callback,
            )

        icon_method.assert_called_once_with()
        self.icon_factory_for_window.assert_called_once_with(self.window)
        self.assertFalse(action.icon().isNull())
        self.assertEqual(action.toolTip(), "Pick atoms")
        self.assertEqual(action.statusTip(), "Pick atoms")
        self.assertTrue(action.isCheckable())
        action.trigger()
        callback.assert_called_once_with()

    def test_activate_bond_style_tool_selects_bond_and_applies_style(self) -> None:
        self.service.activate_bond_style_tool(self.window, "Hash")

        self.context_page_state_service.set_tool_with_status.assert_called_once_with(
            self.window,
            "bond",
            reset_bond_style=False,
        )
        self.tool_state_service.set_bond_style.assert_called_once_with(
            self.window, "Hash"
        )

    def test_activate_ring_fill_tool_shows_ring_fill_context(self) -> None:
        self.service.activate_ring_fill_tool(self.window)

        self.context_page_state_service.show_context_page.assert_called_once_with(
            self.window, "ring_fill"
        )
        self.status_service.refresh_status_context.assert_called_once_with(self.window)

    def test_build_tool_actions_wires_tool_bond_and_mark_callbacks(self) -> None:
        actions = self.service.build_tool_actions(
            self.window, QActionGroup(self.window)
        )

        actions["select"].trigger()
        actions["color"].trigger()
        actions["ring_fill"].trigger()
        actions["bond_hash"].trigger()
        actions["mark"].trigger()

        self.assertNotIn("template", actions)
        self.assertNotIn("mark_plus", actions)
        self.assertNotIn("mark_minus", actions)
        self.assertNotIn("mark_radical", actions)
        self.context_page_state_service.set_tool_with_status.assert_any_call(
            self.window, "select"
        )
        self.context_page_state_service.set_tool_with_status.assert_any_call(
            self.window, "color"
        )
        self.context_page_state_service.set_tool_with_status.assert_any_call(
            self.window, "mark"
        )
        self.context_page_state_service.set_tool_with_status.assert_any_call(
            self.window,
            "bond",
            reset_bond_style=False,
        )
        self.context_page_state_service.show_context_page.assert_any_call(
            self.window, "ring_fill"
        )
        self.assertEqual(
            self.context_page_state_service.show_context_page.call_count, 1
        )
        self.tool_state_service.set_bond_style.assert_called_once_with(
            self.window, "Hash"
        )


if __name__ == "__main__":
    unittest.main()
