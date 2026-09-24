import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QActionGroup, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow

from chemvas.ui.window.main_window_tool_action_service import (
    MainWindowToolActionService,
)


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.tool_mode_controller = SimpleNamespace(set_mark_kind=mock.Mock())
        self.canvas = SimpleNamespace(
            services=canvas_runtime_services(
                tool_mode_controller=self.tool_mode_controller
            )
        )
        self._icon_factory = SimpleNamespace(
            icon_select=self._blank_icon,
            icon_bond=self._blank_icon,
            icon_text=self._blank_icon,
            icon_note=self._blank_icon,
            icon_mark=self._blank_icon,
            icon_ring=self._blank_icon,
            icon_arrow=self._blank_icon,
            icon_line=self._blank_icon,
            icon_ts_bracket=self._blank_icon,
            icon_eraser=self._blank_icon,
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
        self.ui_references = SimpleNamespace(
            require_icon_factory=mock.Mock(return_value=self._icon_factory)
        )

    def show_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _blank_icon(self):
        return QIcon()


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
        self.require_icon_factory = self.window.ui_references.require_icon_factory
        self.status_service = mock.Mock()
        self.service = MainWindowToolActionService(
            tool_state_service=self.tool_state_service,
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
            self.require_icon_factory.return_value, "icon_select", return_value=icon
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
        self.require_icon_factory.assert_called_once_with()
        self.assertFalse(action.icon().isNull())
        self.assertEqual(action.toolTip(), "Pick atoms")
        self.assertEqual(action.statusTip(), "Pick atoms")
        self.assertTrue(action.isCheckable())
        action.trigger()
        callback.assert_called_once_with()

    def test_activate_ring_fill_tool_shows_ring_fill_context(self) -> None:
        self.service.activate_ring_fill_tool(self.window)

        self.tool_state_service.set_tool_with_status.assert_called_once_with(
            self.window, "select"
        )
        self.tool_state_service.show_context_page.assert_called_once_with(
            self.window, "ring_fill"
        )

    def test_build_tool_actions_wires_tool_bond_and_mark_callbacks(self) -> None:
        tool_group = QActionGroup(self.window)
        actions = self.service.build_tool_actions(self.window, tool_group)
        self.assertFalse(actions["ring_fill"].isCheckable())
        self.assertNotIn(actions["ring_fill"], tool_group.actions())

        actions["select"].trigger()
        actions["color"].trigger()
        actions["ring_fill"].trigger()
        actions["bond_hash"].trigger()
        actions["mark"].trigger()

        self.assertNotIn("template", actions)
        self.assertNotIn("mark_plus", actions)
        self.assertNotIn("mark_minus", actions)
        self.assertNotIn("mark_radical", actions)
        self.tool_state_service.set_tool_with_status.assert_any_call(
            self.window, "select"
        )
        self.tool_state_service.set_tool_with_status.assert_any_call(
            self.window, "color"
        )
        self.tool_state_service.set_tool_with_status.assert_any_call(
            self.window, "mark"
        )
        self.tool_state_service.show_context_page.assert_any_call(
            self.window, "ring_fill"
        )
        self.assertEqual(self.tool_state_service.show_context_page.call_count, 1)
        self.tool_state_service.set_bond_style.assert_called_once_with(
            self.window, "Hash"
        )
