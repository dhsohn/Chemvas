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
    from ui.main_window_ports import active_canvas_for_window, services_for_window
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
        self.insert_controller_for_window = mock.Mock(
            return_value=active_canvas_for_window(self.window).services.insert_controller,
        )
        self.tool_mode_controller_for_window = mock.Mock(
            return_value=active_canvas_for_window(self.window).services.tool_mode_controller,
        )
        self.color_mutation_service_for_window = mock.Mock(
            return_value=active_canvas_for_window(self.window).services.canvas_color_mutation_service,
        )
        self.color_tool_for_window = mock.Mock(return_value=None)
        self.selected_scene_items_for_window = mock.Mock(return_value=[])
        self.icon_factory_for_window = mock.Mock(
            side_effect=lambda window: window.ui_references.require_icon_factory(),
        )
        self.tool_state_service = mock.Mock()
        self.context_page_state_service = mock.Mock()
        self.service = MainWindowToolRoutingService(
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            color_mutation_service_for_window=self.color_mutation_service_for_window,
            color_tool_for_window=self.color_tool_for_window,
            selected_scene_items_for_window=self.selected_scene_items_for_window,
            icon_factory_for_window=self.icon_factory_for_window,
            tool_state_service=self.tool_state_service,
            context_page_state_service=self.context_page_state_service,
        )

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()

    def test_template_entries_and_template_menu_preserve_ring_size_and_style(self) -> None:
        with mock.patch.object(active_canvas_for_window(self.window).services.insert_controller, "begin_ring_template_insert") as begin_insert:
            entries = dict(self.service.template_entries(self.window))
            entries["Benzene"]()
            entries["Cyclopropane"]()
            entries["Cycloheptane"]()
            entries["Cyclooctane"]()
            entries["Cyclohexane (Chair)"]()

        self.assertEqual(begin_insert.call_args_list[0].args, (6,))
        self.assertEqual(begin_insert.call_args_list[0].kwargs, {"style": "benzene"})
        self.assertEqual(begin_insert.call_args_list[1].args, (3,))
        self.assertEqual(begin_insert.call_args_list[1].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[2].args, (7,))
        self.assertEqual(begin_insert.call_args_list[2].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[3].args, (8,))
        self.assertEqual(begin_insert.call_args_list[3].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[4].args, (6,))
        self.assertEqual(begin_insert.call_args_list[4].kwargs, {"style": "chair"})

        menu = QMenu()
        self.service.populate_template_menu(self.window, menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            [
                "Benzene",
                "Cyclopropane",
                "Cyclobutane",
                "Cyclopentane",
                "Cyclohexane (Chair)",
                "Cyclohexane (Chair, flipped)",
                "Cycloheptane",
                "Cyclooctane",
            ],
        )
        self.assertEqual(self.insert_controller_for_window.call_count, 2)

    def test_arrow_menu_helpers_route_type_and_preset_through_injected_state_services(self) -> None:
        self.service.activate_arrow_type_from_menu(self.window, "Reaction")
        self.service.activate_arrow_preset_from_menu(self.window, "Bold")
        menu = QMenu()
        self.service.populate_arrow_menu(self.window, menu)
        preset_menu = next(action.menu() for action in menu.actions() if action.menu() is not None)
        menu.actions()[0].trigger()
        preset_menu.actions()[0].trigger()

        self.assertEqual(
            self.context_page_state_service.set_tool_with_status.call_args_list,
            [
                mock.call(self.window, "arrow"),
                mock.call(self.window, "arrow"),
                mock.call(self.window, "arrow"),
                mock.call(self.window, "arrow"),
            ],
        )
        self.assertEqual(
            self.tool_state_service.set_arrow_type.call_args_list,
            [
                mock.call(self.window, "Reaction"),
                mock.call(self.window, "Reaction"),
            ],
        )
        self.assertEqual(
            self.tool_state_service.set_arrow_preset.call_args_list,
            [
                mock.call(self.window, "Bold"),
                mock.call(self.window, "Default"),
            ],
        )
        self.assertNotIn("Settings...", [action.text() for action in menu.actions()])

    def test_palette_menu_and_color_presets_route_selected_items(self) -> None:
        palette_calls = []
        menu = QMenu()
        self.service.populate_palette_menu(self.window, menu, lambda value: palette_calls.append(value))
        palette = self.service.acs_color_palette()
        self.assertEqual([action.text() for action in menu.actions()], [label for label, _ in palette])
        self.assertIn(("Yellow", "#f4d06f"), palette)
        self.assertIn(("Blue", "#2f6ed3"), palette)
        self.assertIn(("Red", "#d84a3a"), palette)
        menu.actions()[0].trigger()
        self.assertEqual(palette_calls, ["#000000"])

        color_tool = SimpleNamespace(set_color=mock.Mock())
        self.color_tool_for_window.return_value = color_tool
        selected_items = [_FakeItem("atom"), _FakeItem("ring"), _FakeItem("note"), _FakeItem("shape")]
        self.selected_scene_items_for_window.return_value = selected_items

        with (
            mock.patch("ui.main_window_tool_routing_service.QTimer.singleShot", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(active_canvas_for_window(self.window).services.tool_mode_controller, "set_tool") as set_tool,
            mock.patch.object(
                active_canvas_for_window(self.window).services.canvas_color_mutation_service,
                "apply_color_to_items",
            ) as apply_color,
            mock.patch.object(
                active_canvas_for_window(self.window).services.canvas_color_mutation_service,
                "apply_ring_fill_color_to_items",
            ) as apply_fill,
        ):
            self.service.apply_color_preset(self.window, "#2f6ed3")
            self.service.apply_ring_fill_preset(self.window, "#f4d06f")

        color_tool.set_color.assert_called_once()
        self.assertEqual(color_tool.set_color.call_args.args[0].name(), "#2f6ed3")
        set_tool.assert_called_once_with("color")
        self.assertEqual(
            [item.data(0) for item in apply_color.call_args.args[0]],
            ["atom", "ring", "note", "shape"],
        )
        self.assertEqual(apply_color.call_args.args[1].name(), "#2f6ed3")
        apply_color.assert_called_once()
        self.assertEqual([item.data(0) for item in apply_fill.call_args.args[0]], ["ring"])
        self.assertEqual(apply_fill.call_args.args[1].name(), "#f4d06f")
        apply_fill.assert_called_once()
        self.color_tool_for_window.assert_called_once_with(self.window)
        self.tool_mode_controller_for_window.assert_called_once_with(self.window)
        self.assertEqual(self.color_mutation_service_for_window.call_count, 2)
        self.assertEqual(
            self.selected_scene_items_for_window.call_args_list,
            [
                mock.call(self.window, excluded_kinds=set()),
                mock.call(self.window, excluded_kinds=set()),
            ],
        )


if __name__ == "__main__":
    unittest.main()
