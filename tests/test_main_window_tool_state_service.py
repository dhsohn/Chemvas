import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    try:
        from ui.canvas_tool_settings_state import (
            set_tool_setting_for,
            tool_settings_state_for,
        )
        from ui.main_window import MainWindow
        from ui.main_window_canvas_ports import active_canvas_for_window
        from ui.main_window_service_ports import services_for_window
        from ui.main_window_tool_state_service import MainWindowToolStateService
    except SyntaxError:
        MainWindow = None
        MainWindowToolStateService = None
else:
    MainWindow = None
    MainWindowToolStateService = None


@unittest.skipUnless(
    QApplication is not None and MainWindow is not None and MainWindowToolStateService is not None,
    "PyQt6 and an importable MainWindow tool state surface are required for tests",
)
class MainWindowToolStateServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.tool_mode_controller_for_window = mock.Mock(
            return_value=active_canvas_for_window(self.window).services.tool_mode_controller,
        )
        self.active_tool_name_for_window = mock.Mock(
            side_effect=lambda window: self._active_tool_name_for_canvas(active_canvas_for_window(window)),
        )
        self.tool_settings_for_window = mock.Mock(
            side_effect=lambda window: tool_settings_state_for(active_canvas_for_window(window)),
        )
        self.tool_actions_for_window = mock.Mock(
            side_effect=lambda window: window.ui_references.tool_actions,
        )
        self.tool_action_for_window = mock.Mock(
            side_effect=lambda window, action_key: window.ui_references.tool_action_for_key(action_key),
        )
        self.status_service = mock.Mock(wraps=services_for_window(self.window).status_service)
        self.service = MainWindowToolStateService(
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            active_tool_name_for_window=self.active_tool_name_for_window,
            tool_settings_for_window=self.tool_settings_for_window,
            tool_actions_for_window=self.tool_actions_for_window,
            tool_action_for_window=self.tool_action_for_window,
            status_service=self.status_service,
        )

    def _active_tool_name_for_canvas(self, canvas) -> str | None:
        active_tool = getattr(canvas.services.tools, "active", None)
        name = getattr(active_tool, "name", None)
        return str(name) if name else None

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _reset_tool_checks(self) -> None:
        for action in self.window.ui_references.tool_actions.values():
            action.setChecked(False)

    def test_set_tool_with_status_updates_canvas_status_and_optional_bond_reset(self) -> None:
        with (
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_tool") as set_tool,
            mock.patch.object(self.service, "set_bond_style") as set_bond_style,
        ):
            self.service.set_tool_with_status(self.window, "bond")
            self.assertEqual(self.window.statusBar().currentMessage(), "Bond Tool")

            self.service.set_tool_with_status(self.window, "bond", reset_bond_style=False)
            self.assertEqual(self.window.statusBar().currentMessage(), "Bond Tool")

            self.service.set_tool_with_status(self.window, "select")
            self.assertEqual(self.window.statusBar().currentMessage(), "Select Tool")

        self.assertEqual([call.args for call in set_tool.call_args_list], [("bond",), ("bond",), ("select",)])
        set_bond_style.assert_called_once_with(self.window, "Single")
        self.assertEqual(self.tool_mode_controller_for_window.call_count, 3)
        self.assertEqual(self.status_service.refresh_status_context.call_count, 3)

    def test_set_tool_with_status_refreshes_structured_tool_state(self) -> None:
        self.service.set_tool_with_status(self.window, "select")

        self.assertEqual(self.window.statusBar().currentMessage(), "Select Tool")
        self.assertEqual(self.status_service.status_context_texts()["tool"], "Tool: Select")

    def test_sync_tool_actions_from_canvas_follows_active_tool_variants(self) -> None:
        self._reset_tool_checks()
        active_canvas_for_window(self.window).services.tools.active = SimpleNamespace(name="bond")
        set_tool_setting_for(active_canvas_for_window(self.window), "active_bond_style", "hash")
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window.ui_references.tool_actions["bond"].isChecked())

        self._reset_tool_checks()
        active_canvas_for_window(self.window).services.tools.active = SimpleNamespace(name="mark")
        set_tool_setting_for(active_canvas_for_window(self.window), "mark_kind", "minus")
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window.ui_references.tool_actions["mark_minus"].isChecked())

        self._reset_tool_checks()
        active_canvas_for_window(self.window).services.tools.active = SimpleNamespace(name="perspective")
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window.ui_references.tool_actions["perspective"].isChecked())
        self.assertEqual(self.active_tool_name_for_window.call_count, 3)
        self.assertEqual(self.tool_settings_for_window.call_count, 3)
        self.assertEqual(self.tool_actions_for_window.call_count, 3)
        self.assertEqual(self.tool_action_for_window.call_count, 3)

    def test_set_bond_style_routes_toolbar_labels_to_canvas(self) -> None:
        with mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_bond_style") as set_bond_style:
            self.service.set_bond_style(self.window, "Double")
            self.service.set_bond_style(self.window, "Unknown")

        self.assertEqual([call.args for call in set_bond_style.call_args_list], [("double", 2), ("single", 1)])
        self.assertEqual(self.tool_mode_controller_for_window.call_count, 2)

    def test_set_arrow_and_orbital_variants_route_mapped_values(self) -> None:
        with (
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_arrow_type") as set_arrow_type,
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_orbital_type") as set_orbital_type,
            mock.patch.object(
                active_canvas_for_window(self.window).services.tool_mode_controller,
                "set_orbital_phase_enabled",
            ) as set_orbital_phase_enabled,
        ):
            self.service.set_arrow_type(self.window, "Curved Double")
            self.service.set_arrow_type(self.window, "Unknown")
            self.service.set_orbital_type(self.window, "MO antibonding")
            self.service.set_orbital_type(self.window, "Unknown")
            self.service.set_orbital_phase(self.window, "Phase On")
            self.service.set_orbital_phase(self.window, "Phase Off")

        self.assertEqual([call.args for call in set_arrow_type.call_args_list], [("curved_double",), ("reaction",)])
        self.assertEqual([call.args for call in set_orbital_type.call_args_list], [("mo_antibonding",), ("s",)])
        self.assertEqual([call.args for call in set_orbital_phase_enabled.call_args_list], [(True,), (False,)])
        self.assertEqual(self.tool_mode_controller_for_window.call_count, 6)

    def test_set_arrow_preset_routes_width_and_head_scale(self) -> None:
        with (
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_arrow_line_width") as set_arrow_line_width,
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_arrow_head_scale") as set_arrow_head_scale,
        ):
            self.service.set_arrow_preset(self.window, "Bold")
            self.service.set_arrow_preset(self.window, "Unknown")

        self.assertEqual([call.args for call in set_arrow_line_width.call_args_list], [(2.2,), (1.2,)])
        self.assertEqual([call.args for call in set_arrow_head_scale.call_args_list], [(0.4,), (0.3,)])
        self.assertEqual(self.tool_mode_controller_for_window.call_count, 2)


if __name__ == "__main__":
    unittest.main()
