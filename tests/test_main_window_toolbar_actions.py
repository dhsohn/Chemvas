import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QMenu
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow


class _FakeItem:
    def __init__(self, kind: str) -> None:
        self._kind = kind

    def data(self, key):
        if key == 0:
            return self._kind
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tests")
class MainWindowToolbarActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_template_entries_and_template_menu_preserve_ring_size_and_style(self) -> None:
        with mock.patch.object(self.window.canvas, "begin_ring_template_insert") as begin_insert:
            entries = dict(self.window._template_entries())
            entries["Cyclopropane"]()
            entries["Cyclohexane (Chair)"]()

        self.assertEqual(begin_insert.call_args_list[0].args, (3,))
        self.assertEqual(begin_insert.call_args_list[0].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[1].args, (6,))
        self.assertEqual(begin_insert.call_args_list[1].kwargs, {"style": "chair"})

        menu = QMenu()
        self.window._populate_template_menu(menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            ["Cyclopropane", "Cyclobutane", "Cyclopentane", "Cyclohexane (Chair)"],
        )

    def test_set_tool_with_status_and_sync_tool_actions_follow_canvas_state(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "set_tool") as set_tool,
            mock.patch.object(self.window, "_set_bond_style") as set_bond_style,
        ):
            self.window._set_tool_with_status("bond")
            self.assertEqual(self.window.statusBar().currentMessage(), "Bond Tool")
            set_tool.assert_called_once_with("bond")
            set_bond_style.assert_called_once_with("Single")

        for action in self.window._tool_actions.values():
            action.setChecked(False)

        self.window.canvas.tools.active = SimpleNamespace(name="bond")
        self.window.canvas.active_bond_style = "hash"
        self.window._sync_tool_actions_from_canvas()
        self.assertTrue(self.window._tool_actions["bond_hash"].isChecked())

        for action in self.window._tool_actions.values():
            action.setChecked(False)

        self.window.canvas.tools.active = SimpleNamespace(name="mark")
        self.window.canvas.mark_kind = "minus"
        self.window._sync_tool_actions_from_canvas()
        self.assertTrue(self.window._tool_actions["mark_minus"].isChecked())

        for action in self.window._tool_actions.values():
            action.setChecked(False)

        self.window.canvas.tools.active = SimpleNamespace(name="perspective")
        self.window._sync_tool_actions_from_canvas()
        self.assertTrue(self.window._tool_actions["perspective"].isChecked())

    def test_arrow_menu_helpers_route_type_and_preset_through_existing_methods(self) -> None:
        with mock.patch.object(self.window.canvas, "set_arrow_type") as set_arrow_type:
            self.window._set_arrow_type("Curved Double")
            self.window._set_arrow_type("Unknown")

        self.assertEqual(
            [call.args[0] for call in set_arrow_type.call_args_list],
            ["curved_double", "reaction"],
        )

        with (
            mock.patch.object(self.window, "_set_tool_with_status") as set_tool,
            mock.patch.object(self.window, "_set_arrow_type") as set_type,
            mock.patch.object(self.window, "_set_arrow_preset") as set_preset,
            mock.patch.object(self.window, "_open_arrow_settings") as open_settings,
        ):
            self.window._activate_arrow_type_from_menu("Reaction")
            self.window._activate_arrow_preset_from_menu("Bold")
            menu = QMenu()
            self.window._populate_arrow_menu(menu)
            preset_menu = next(action.menu() for action in menu.actions() if action.menu() is not None)
            menu.actions()[0].trigger()
            preset_menu.actions()[0].trigger()
            menu.actions()[-1].trigger()

        self.assertEqual(set_tool.call_args_list[0].args, ("arrow",))
        self.assertEqual(set_tool.call_args_list[1].args, ("arrow",))
        self.assertTrue(any(call.args == ("Reaction",) for call in set_type.call_args_list))
        self.assertTrue(any(call.args == ("Default",) for call in set_preset.call_args_list))
        open_settings.assert_called_once_with()

    def test_text_preset_and_palette_menu_helpers_delegate_correctly(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "apply_text_preset_acs") as acs,
            mock.patch.object(self.window.canvas, "apply_text_preset_paper_thin") as paper_thin,
            mock.patch.object(self.window.canvas, "apply_text_preset_paper_bold") as paper_bold,
        ):
            self.window._set_text_preset("ACS")
            self.window._set_text_preset("Paper Thin")
            self.window._set_text_preset("Paper Bold")
            self.window._set_text_preset("Unknown")

        acs.assert_called_once_with()
        paper_thin.assert_called_once_with()
        paper_bold.assert_called_once_with()

        palette_calls = []
        menu = QMenu()
        self.window._populate_palette_menu(menu, lambda value: palette_calls.append(value))
        self.assertEqual([action.text() for action in menu.actions()], [label for label, _ in self.window._acs_color_palette()])
        menu.actions()[0].trigger()
        self.assertEqual(palette_calls, ["#000000"])

    def test_apply_color_and_ring_fill_presets_filter_selected_items_and_update_color_tool(self) -> None:
        color_tool = SimpleNamespace(_last_color=None)
        self.window.canvas.tools.tools["color"] = color_tool
        selected_items = [_FakeItem("atom"), _FakeItem("ring"), _FakeItem("note")]
        scene = SimpleNamespace(selectedItems=lambda: selected_items)

        with (
            mock.patch("ui.main_window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.window.canvas, "scene", return_value=scene),
            mock.patch.object(self.window.canvas, "set_tool") as set_tool,
            mock.patch.object(self.window.canvas, "apply_color_to_item") as apply_color,
            mock.patch.object(self.window.canvas, "apply_ring_fill_color") as apply_fill,
        ):
            self.window._apply_color_preset("#1f5eff")
            self.window._apply_ring_fill_preset("#c77c00")

        self.assertEqual(color_tool._last_color, "#1f5eff")
        set_tool.assert_called_once_with("color")
        self.assertEqual([call.args[0].data(0) for call in apply_color.call_args_list], ["atom", "ring"])
        self.assertEqual([call.args[1].name() for call in apply_color.call_args_list], ["#1f5eff", "#1f5eff"])
        self.assertEqual([call.args[0].data(0) for call in apply_fill.call_args_list], ["ring"])
        self.assertEqual([call.args[1].name() for call in apply_fill.call_args_list], ["#c77c00"])


if __name__ == "__main__":
    unittest.main()
