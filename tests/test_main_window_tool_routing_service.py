import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

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
        if not sip.isdeleted(self.window) and not self.window.is_closing:
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
            _FakeItem("mark"),
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
        set_tool.assert_not_called()
        self.context_page_state_service.set_tool_with_status.assert_called_once_with(
            self.window, "color"
        )
        self.assertEqual(
            [item.data(0) for item in apply_color.call_args.args[0]],
            ["atom", "ring", "note", "shape", "mark"],
        )
        self.assertEqual(apply_color.call_args.args[1].name(), "#2f6ed3")
        apply_color.assert_called_once()
        self.assertEqual(
            [item.data(0) for item in apply_fill.call_args.args[0]], ["atom", "ring"]
        )
        self.assertEqual(apply_fill.call_args.args[1].name(), "#f4d06f")
        apply_fill.assert_called_once()
        self.assertEqual(
            self.color_tool_for_window.call_args_list,
            [mock.call(self.window), mock.call(self.window)],
        )
        self.tool_mode_controller_for_window.assert_not_called()
        self.assertEqual(self.color_mutation_service_for_window.call_count, 3)
        self.assertEqual(
            self.selected_scene_items_for_window.call_args_list,
            [
                mock.call(self.window, excluded_kinds=set()),
                mock.call(self.window, excluded_kinds=set()),
            ],
        )

    def test_deferred_ring_fill_rejects_a_changed_canvas(self) -> None:
        callbacks = []
        timer = SimpleNamespace(
            singleShot=lambda _delay, callback: callbacks.append(callback)
        )
        original_service = mock.Mock()
        next_service = mock.Mock()
        self.color_mutation_service_for_window.return_value = original_service
        self.service.apply_ring_fill_preset(self.window, "#f4d06f", qtimer=timer)
        self.color_mutation_service_for_window.return_value = next_service
        callbacks.pop()()
        original_service.apply_ring_fill_color_to_items.assert_not_called()
        next_service.apply_ring_fill_color_to_items.assert_not_called()
        self.selected_scene_items_for_window.assert_not_called()
        self.assertIn("active canvas changed", self.window.statusBar().currentMessage())

    def test_deferred_ring_fill_ignores_a_destroyed_window(self) -> None:
        callbacks = []
        timer = SimpleNamespace(
            singleShot=lambda _delay, callback: callbacks.append(callback)
        )
        window = QObject()
        color_service = mock.Mock()
        self.color_mutation_service_for_window.return_value = color_service
        self.service.apply_ring_fill_preset(window, "#f4d06f", qtimer=timer)
        sip.delete(window)
        callbacks.pop()()
        color_service.apply_ring_fill_color_to_items.assert_not_called()
        self.selected_scene_items_for_window.assert_not_called()

    def test_deferred_presets_do_not_run_after_close_is_accepted(self) -> None:
        color_service = mock.Mock()
        self.color_mutation_service_for_window.return_value = color_service
        self.service.apply_color_preset(self.window, "#123456")
        self.service.apply_ring_fill_preset(self.window, "#f4d06f")
        self.assertTrue(self.window.close())
        self.app.processEvents()
        color_service.apply_color_to_items.assert_not_called()
        color_service.apply_ring_fill_color_to_items.assert_not_called()
        self.selected_scene_items_for_window.assert_not_called()
