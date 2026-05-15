import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QMenu
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_tool_routing_service import MainWindowToolRoutingService


class _FakeItem:
    def __init__(self, kind: str) -> None:
        self._kind = kind

    def data(self, key):
        if key == 0:
            return self._kind
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tool routing tests")
class MainWindowToolRoutingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.service = MainWindowToolRoutingService()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_template_entries_and_template_menu_preserve_ring_size_and_style(self) -> None:
        with mock.patch.object(self.window.canvas, "begin_ring_template_insert") as begin_insert:
            entries = dict(self.service.template_entries(self.window))
            entries["Cyclopropane"]()
            entries["Cycloheptane"]()
            entries["Cyclooctane"]()
            entries["Cyclohexane (Chair)"]()

        self.assertEqual(begin_insert.call_args_list[0].args, (3,))
        self.assertEqual(begin_insert.call_args_list[0].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[1].args, (7,))
        self.assertEqual(begin_insert.call_args_list[1].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[2].args, (8,))
        self.assertEqual(begin_insert.call_args_list[2].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[3].args, (6,))
        self.assertEqual(begin_insert.call_args_list[3].kwargs, {"style": "chair"})

        menu = QMenu()
        self.service.populate_template_menu(self.window, menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            [
                "Cyclopropane",
                "Cyclobutane",
                "Cyclopentane",
                "Cyclohexane (Chair)",
                "Cycloheptane",
                "Cyclooctane",
            ],
        )

    def test_arrow_menu_helpers_route_type_and_preset_through_existing_window_methods(self) -> None:
        with (
            mock.patch.object(self.window, "_set_tool_with_status") as set_tool,
            mock.patch.object(self.window, "_set_arrow_type") as set_type,
            mock.patch.object(self.window, "_set_arrow_preset") as set_preset,
            mock.patch.object(self.window, "_open_arrow_settings") as open_settings,
        ):
            self.service.activate_arrow_type_from_menu(self.window, "Reaction")
            self.service.activate_arrow_preset_from_menu(self.window, "Bold")
            menu = QMenu()
            self.service.populate_arrow_menu(self.window, menu)
            preset_menu = next(action.menu() for action in menu.actions() if action.menu() is not None)
            menu.actions()[0].trigger()
            preset_menu.actions()[0].trigger()
            menu.actions()[-1].trigger()

        self.assertEqual(set_tool.call_args_list[0].args, ("arrow",))
        self.assertEqual(set_tool.call_args_list[1].args, ("arrow",))
        self.assertTrue(any(call.args == ("Reaction",) for call in set_type.call_args_list))
        self.assertTrue(any(call.args == ("Default",) for call in set_preset.call_args_list))
        open_settings.assert_called_once_with()

    def test_palette_menu_and_color_presets_route_selected_items(self) -> None:
        palette_calls = []
        menu = QMenu()
        self.service.populate_palette_menu(self.window, menu, lambda value: palette_calls.append(value))
        self.assertEqual([action.text() for action in menu.actions()], [label for label, _ in self.service.acs_color_palette()])
        menu.actions()[0].trigger()
        self.assertEqual(palette_calls, ["#000000"])

        color_tool = SimpleNamespace(_last_color=None)
        self.window.canvas.tools.tools["color"] = color_tool
        selected_items = [_FakeItem("atom"), _FakeItem("ring"), _FakeItem("note")]
        scene = SimpleNamespace(selectedItems=lambda: selected_items)

        with (
            mock.patch("ui.main_window_tool_routing_service.QTimer.singleShot", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.window.canvas, "scene", return_value=scene),
            mock.patch.object(self.window.canvas, "set_tool") as set_tool,
            mock.patch.object(self.window.canvas, "apply_color_to_item") as apply_color,
            mock.patch.object(self.window.canvas, "apply_ring_fill_color") as apply_fill,
        ):
            self.service.apply_color_preset(self.window, "#1f5eff")
            self.service.apply_ring_fill_preset(self.window, "#c77c00")

        self.assertEqual(color_tool._last_color, "#1f5eff")
        set_tool.assert_called_once_with("color")
        self.assertEqual([call.args[0].data(0) for call in apply_color.call_args_list], ["atom", "ring"])
        self.assertEqual([call.args[1].name() for call in apply_color.call_args_list], ["#1f5eff", "#1f5eff"])
        self.assertEqual([call.args[0].data(0) for call in apply_fill.call_args_list], ["ring"])
        self.assertEqual([call.args[1].name() for call in apply_fill.call_args_list], ["#c77c00"])


if __name__ == "__main__":
    unittest.main()
