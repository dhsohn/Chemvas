import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    try:
        from ui.main_window import MainWindow
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
        self.service = MainWindowToolStateService()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def _reset_tool_checks(self) -> None:
        for action in self.window._tool_actions.values():
            action.setChecked(False)

    def test_set_tool_with_status_updates_canvas_status_and_optional_bond_reset(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "set_tool") as set_tool,
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

    def test_sync_tool_actions_from_canvas_follows_active_tool_variants(self) -> None:
        self._reset_tool_checks()
        self.window.canvas.tools.active = SimpleNamespace(name="bond")
        self.window.canvas.active_bond_style = "hash"
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window._tool_actions["bond_hash"].isChecked())

        self._reset_tool_checks()
        self.window.canvas.tools.active = SimpleNamespace(name="mark")
        self.window.canvas.mark_kind = "minus"
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window._tool_actions["mark_minus"].isChecked())

        self._reset_tool_checks()
        self.window.canvas.tools.active = SimpleNamespace(name="perspective")
        self.service.sync_tool_actions_from_canvas(self.window)
        self.assertTrue(self.window._tool_actions["perspective"].isChecked())

    def test_set_bond_style_routes_toolbar_labels_to_canvas(self) -> None:
        with mock.patch.object(self.window.canvas, "set_bond_style") as set_bond_style:
            self.service.set_bond_style(self.window, "Double")
            self.service.set_bond_style(self.window, "Unknown")

        self.assertEqual([call.args for call in set_bond_style.call_args_list], [("double", 2), ("single", 1)])

    def test_set_arrow_and_orbital_variants_route_mapped_values(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "set_arrow_type") as set_arrow_type,
            mock.patch.object(self.window.canvas, "set_orbital_type") as set_orbital_type,
            mock.patch.object(self.window.canvas, "set_orbital_phase_enabled") as set_orbital_phase_enabled,
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

    def test_set_arrow_preset_routes_width_and_head_scale(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "set_arrow_line_width") as set_arrow_line_width,
            mock.patch.object(self.window.canvas, "set_arrow_head_scale") as set_arrow_head_scale,
        ):
            self.service.set_arrow_preset(self.window, "Bold")
            self.service.set_arrow_preset(self.window, "Unknown")

        self.assertEqual([call.args for call in set_arrow_line_width.call_args_list], [(2.2,), (1.2,)])
        self.assertEqual([call.args for call in set_arrow_head_scale.call_args_list], [(0.4,), (0.3,)])


if __name__ == "__main__":
    unittest.main()
