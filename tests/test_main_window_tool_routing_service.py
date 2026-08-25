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
    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.ui.main_window_ports import (
        active_canvas_for_window,
        services_for_window,
    )
    from chemvas.ui.main_window_tool_routing_service import MainWindowToolRoutingService


class _FakeItem:
    def __init__(self, kind: str) -> None:
        self._kind = kind

    def data(self, key):
        if key == 0:
            return self._kind
        return None


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for main window tool routing tests"
)
class MainWindowToolRoutingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.tool_mode_controller_for_window = mock.Mock(
            return_value=active_canvas_for_window(
                self.window
            ).services.input.tool_mode_controller,
        )
        self.color_mutation_service_for_window = mock.Mock(
            return_value=active_canvas_for_window(
                self.window
            ).services.scene_operations.canvas_color_mutation_service,
        )
        self.color_tool_for_window = mock.Mock(return_value=None)
        self.selected_scene_items_for_window = mock.Mock(return_value=[])
        self.tool_state_service = mock.Mock()
        self.context_page_state_service = mock.Mock()
        self.service = MainWindowToolRoutingService(
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            color_mutation_service_for_window=self.color_mutation_service_for_window,
            color_tool_for_window=self.color_tool_for_window,
            selected_scene_items_for_window=self.selected_scene_items_for_window,
            tool_state_service=self.tool_state_service,
            context_page_state_service=self.context_page_state_service,
        )

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()

    def test_color_and_ring_fill_presets_route_selected_items(self) -> None:
        color_tool = SimpleNamespace(set_color=mock.Mock())
        self.color_tool_for_window.return_value = color_tool
        selected_items = [
            _FakeItem("atom"),
            _FakeItem("ring"),
            _FakeItem("note"),
            _FakeItem("shape"),
        ]
        self.selected_scene_items_for_window.return_value = selected_items

        with (
            mock.patch(
                "chemvas.ui.main_window_tool_routing_service.QTimer.singleShot",
                side_effect=lambda _delay, callback: callback(),
            ),
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.input.tool_mode_controller,
                "set_tool",
            ) as set_tool,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.canvas_color_mutation_service,
                "apply_color_to_items",
            ) as apply_color,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.canvas_color_mutation_service,
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
        self.assertEqual(
            [item.data(0) for item in apply_fill.call_args.args[0]], ["ring"]
        )
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
