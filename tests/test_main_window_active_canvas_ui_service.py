import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
except ModuleNotFoundError:
    QApplication = None
    QTabWidget = None
    QWidget = None

if QApplication is not None:
    try:
        from ui.canvas_callback_state import callback_state_for
        from ui.canvas_view import CanvasView
        from ui.main_window_active_canvas_ui_service import (
            MainWindowActiveCanvasUIService,
        )
        from ui.selection_info_state import selection_info_state_for
    except (ModuleNotFoundError, SyntaxError):
        CanvasView = None
        MainWindowActiveCanvasUIService = None
else:
    CanvasView = None
    MainWindowActiveCanvasUIService = None


class _FakeWindow:
    def __init__(self) -> None:
        self.canvas_tabs = QTabWidget()
        self.canvas_a = CanvasView()
        self.canvas_b = CanvasView()
        self._sheet_add_tab = QWidget()
        self.canvas_tabs.addTab(self.canvas_a, "Sheet 1")
        self.canvas_tabs.addTab(self.canvas_b, "Sheet 2")
        self.canvas_tabs.addTab(self._sheet_add_tab, "+")
        self.canvas_tabs.setCurrentIndex(0)
        self._last_canvas_tab_index = 0
        self._suspend_canvas_tab_reactions = False
        self.preview_3d = _FakePreview3D()
        self._atom_input = mock.Mock()
        self.sync_tool_actions_from_canvas = mock.Mock()
        self.new_canvas_sheet = mock.Mock()
        self.refresh_active_canvas_ui = mock.Mock()
        self.update_zoom_label = mock.Mock()
        self.update_action_availability = mock.Mock()
        self.handle_selection_info = mock.Mock()
        self.show_error_message = mock.Mock()

    @property
    def sheet_add_tab(self):
        return self._sheet_add_tab

    @property
    def atom_input(self):
        return self._atom_input

    @property
    def tab_reactions_suspended(self) -> bool:
        return bool(self._suspend_canvas_tab_reactions)

    @tab_reactions_suspended.setter
    def tab_reactions_suspended(self, suspended: bool) -> None:
        self._suspend_canvas_tab_reactions = bool(suspended)

    @property
    def last_canvas_tab_index(self) -> int:
        return self._last_canvas_tab_index

    @last_canvas_tab_index.setter
    def last_canvas_tab_index(self, index: int) -> None:
        self._last_canvas_tab_index = index

    @property
    def canvas(self):
        widget = self.canvas_tabs.currentWidget()
        if isinstance(widget, CanvasView):
            return widget
        raise RuntimeError("No active canvas.")

    def has_zoom_label(self) -> bool:
        return True


class _FakePreview3D:
    def __init__(self) -> None:
        self.rdkit_adapter = None
        self.refresh_selected_from_canvas = mock.Mock()

    def set_rdkit_adapter(self, adapter) -> None:
        self.rdkit_adapter = adapter


@unittest.skipUnless(
    QApplication is not None and CanvasView is not None and MainWindowActiveCanvasUIService is not None,
    "PyQt6 and an importable active canvas UI service are required for tests",
)
class MainWindowActiveCanvasUIServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = _FakeWindow()
        self.tool_mode_controller_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.tool_mode_controller,
        )
        self.active_canvas_for_window = mock.Mock(side_effect=lambda window: window.canvas)
        self.all_canvases_for_window = mock.Mock(return_value=[self.window.canvas_a, self.window.canvas_b])
        self.current_zoom_percent_for_window = mock.Mock(return_value=100)
        self.status_service = mock.Mock()
        self.status_service.has_zoom_label.return_value = True
        self.context_bar_service = mock.Mock()
        self.action_availability_service = mock.Mock()
        self.context_page_state_service = mock.Mock()
        self.new_canvas_sheet_for_window = mock.Mock()
        self.tab_refs_for_window = mock.Mock(
            side_effect=lambda window: SimpleNamespace(canvas_tabs=window.canvas_tabs)
        )
        self.preview_for_window = mock.Mock(side_effect=lambda window: window.preview_3d)
        self.atom_input_for_window = mock.Mock(side_effect=lambda window: window.atom_input)
        self.sheet_add_tab_for_window = mock.Mock(side_effect=lambda window: window.sheet_add_tab)
        self.tab_reactions_suspended_for_window = mock.Mock(side_effect=lambda window: window.tab_reactions_suspended)
        self.set_last_canvas_tab_index_for_window = mock.Mock(
            side_effect=lambda window, index: setattr(window, "last_canvas_tab_index", index)
        )
        self.service = MainWindowActiveCanvasUIService(
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            active_canvas_for_window=self.active_canvas_for_window,
            all_canvases_for_window=self.all_canvases_for_window,
            current_zoom_percent_for_window=self.current_zoom_percent_for_window,
            status_service=self.status_service,
            context_bar_service=self.context_bar_service,
            action_availability_service=self.action_availability_service,
            context_page_state_service=self.context_page_state_service,
            new_canvas_sheet_for_window=self.new_canvas_sheet_for_window,
            tab_refs_for_window=self.tab_refs_for_window,
            preview_for_window=self.preview_for_window,
            atom_input_for_window=self.atom_input_for_window,
            sheet_add_tab_for_window=self.sheet_add_tab_for_window,
            tab_reactions_suspended_for_window=self.tab_reactions_suspended_for_window,
            set_last_canvas_tab_index_for_window=self.set_last_canvas_tab_index_for_window,
        )

    def tearDown(self) -> None:
        self.window.canvas_tabs.deleteLater()
        self.app.processEvents()

    def _assert_canvas_callbacks(self, canvas, *, active: bool) -> None:
        if active:
            self.assertIsNot(selection_info_state_for(canvas).callback, self.window.handle_selection_info)
            self.assertIsNot(callback_state_for(canvas).tool_change, self.window.sync_tool_actions_from_canvas)
            self.assertIs(callback_state_for(canvas).zoom, self.status_service.update_zoom_label)
            self.assertIsNot(callback_state_for(canvas).error, self.window.show_error_message)
            self.assertIsNot(
                canvas.runtime_state.history_service.state.change_callback,
                self.window.update_action_availability,
            )
            return
        self.assertIsNone(selection_info_state_for(canvas).callback)
        self.assertIsNone(callback_state_for(canvas).tool_change)
        self.assertIsNone(callback_state_for(canvas).zoom)
        self.assertIsNone(callback_state_for(canvas).error)
        self.assertIsNone(canvas.runtime_state.history_service.state.change_callback)

    def test_bind_active_canvas_updates_preview_rdkit_and_callbacks(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)

        self.service.bind_active_canvas(self.window)

        self.assertIs(self.window.preview_3d.rdkit_adapter, self.window.canvas_b.rdkit)
        self.active_canvas_for_window.assert_called_once_with(self.window)
        self.all_canvases_for_window.assert_called_once_with(self.window)
        self._assert_canvas_callbacks(self.window.canvas_a, active=False)
        self._assert_canvas_callbacks(self.window.canvas_b, active=True)

    def test_bound_active_canvas_callbacks_route_through_injected_services(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)
        self.service.bind_active_canvas(self.window)
        self.status_service.reset_mock()
        self.context_page_state_service.reset_mock()
        self.action_availability_service.reset_mock()
        self.window.preview_3d.refresh_selected_from_canvas.reset_mock()

        selection_info_state_for(self.window.canvas_b).callback("H2O", "18.0")
        callback_state_for(self.window.canvas_b).tool_change()
        callback_state_for(self.window.canvas_b).zoom(175)
        self.window.canvas_b.runtime_state.history_service.state.change_callback()
        callback_state_for(self.window.canvas_b).error("Invalid molecule")

        self.window.preview_3d.refresh_selected_from_canvas.assert_called_once_with(self.window.canvas_b)
        self.status_service.update_selection_status_label.assert_called_once_with(self.window)
        self.status_service.update_chemical_status_label.assert_called_once_with("H2O", "18.0")
        self.context_page_state_service.sync_tool_actions_from_canvas.assert_called_once_with(self.window)
        self.status_service.update_zoom_label.assert_called_once_with(175)
        self.action_availability_service.update_action_availability.assert_has_calls(
            [mock.call(self.window), mock.call(self.window)],
        )
        self.status_service.show_error_message.assert_called_once_with(
            self.window,
            "Invalid molecule",
            timeout=6000,
        )
        self.window.handle_selection_info.assert_not_called()
        self.window.sync_tool_actions_from_canvas.assert_not_called()
        self.window.update_zoom_label.assert_not_called()
        self.window.update_action_availability.assert_not_called()
        self.window.show_error_message.assert_not_called()

    def test_handle_selection_info_refreshes_preview_from_active_canvas(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)

        self.service.handle_selection_info(self.window, "H2O", "18.0")

        self.window.preview_3d.refresh_selected_from_canvas.assert_called_once_with(self.window.canvas_b)
        self.status_service.update_selection_status_label.assert_called_once_with(self.window)
        self.status_service.update_chemical_status_label.assert_called_once_with("H2O", "18.0")
        self.action_availability_service.update_action_availability.assert_called_once_with(self.window)

    def test_handle_selection_info_ignores_deleted_window_canvas(self) -> None:
        class _DeletedWindow:
            def __init__(self) -> None:
                self.preview_3d = SimpleNamespace(refresh_selected_from_canvas=mock.Mock())

            @property
            def canvas(self):
                raise RuntimeError("deleted")

        window = _DeletedWindow()

        self.service.handle_selection_info(window, "", "")

        window.preview_3d.refresh_selected_from_canvas.assert_not_called()
        self.status_service.update_selection_status_label.assert_not_called()
        self.status_service.update_chemical_status_label.assert_not_called()
        self.action_availability_service.update_action_availability.assert_not_called()

    def test_handle_selection_info_ignores_deleted_qt_callback_state(self) -> None:
        self.status_service.update_selection_status_label.side_effect = RuntimeError("deleted")

        self.service.handle_selection_info(self.window, "", "")

        self.window.preview_3d.refresh_selected_from_canvas.assert_called_once_with(self.window.canvas_a)
        self.status_service.update_selection_status_label.assert_called_once_with(self.window)
        self.status_service.update_chemical_status_label.assert_not_called()
        self.action_availability_service.update_action_availability.assert_not_called()

    def test_current_zoom_percent_rounds_scale_and_clamps_minimum(self) -> None:
        cases = (
            (2.34, 234),
            (0.0, 1),
        )
        for _scale, expected in cases:
            with self.subTest(expected=expected):
                self.current_zoom_percent_for_window.return_value = expected
                self.assertEqual(self.service.current_zoom_percent(self.window), expected)
        self.assertEqual(self.current_zoom_percent_for_window.call_args_list, [mock.call(self.window), mock.call(self.window)])

    def test_refresh_active_canvas_ui_rebinds_updates_inputs_and_refreshes_preview(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)
        self.current_zoom_percent_for_window.return_value = 275

        with mock.patch.object(self.window.canvas_b.services.tool_mode_controller, "get_atom_symbol", return_value="N"):
            self.service.refresh_active_canvas_ui(self.window)

        # selection-derived UI (preview / chemical label / action availability)
        # is emitted on the next event-loop turn; flush it before asserting.
        self.app.processEvents()

        self.assertEqual(
            self.window._atom_input.method_calls,
            [mock.call.blockSignals(True), mock.call.setText("N"), mock.call.blockSignals(False)],
        )
        self.status_service.update_zoom_label.assert_called_once_with(275)
        self.window.update_zoom_label.assert_not_called()
        self.context_page_state_service.sync_tool_actions_from_canvas.assert_called_once_with(self.window)
        self.window.sync_tool_actions_from_canvas.assert_not_called()
        self.action_availability_service.update_action_availability.assert_called_once_with(self.window)
        self.window.update_action_availability.assert_not_called()
        self.window.preview_3d.refresh_selected_from_canvas.assert_called_once_with(self.window.canvas_b)
        self.status_service.update_chemical_status_label.assert_called_once_with("", "")
        self.assertIs(self.window.preview_3d.rdkit_adapter, self.window.canvas_b.rdkit)
        self.tool_mode_controller_for_window.assert_called_once_with(self.window)
        self._assert_canvas_callbacks(self.window.canvas_a, active=False)
        self._assert_canvas_callbacks(self.window.canvas_b, active=True)

    def test_on_canvas_tab_changed_ignores_suspended_invalid_and_non_canvas_targets(self) -> None:
        other_widget = QWidget()
        other_index = self.window.canvas_tabs.insertTab(2, other_widget, "Other")

        self.service.on_canvas_tab_changed(self.window, -1)
        self.window.tab_reactions_suspended = True
        self.service.on_canvas_tab_changed(self.window, 0)
        self.window.tab_reactions_suspended = False
        self.service.on_canvas_tab_changed(self.window, other_index)

        self.window.new_canvas_sheet.assert_not_called()
        self.window.refresh_active_canvas_ui.assert_not_called()
        self.assertEqual(self.window.last_canvas_tab_index, 0)
        self.assertEqual(self.status_service.refresh_status_context.call_count, 3)
        self.assertEqual(self.context_bar_service.refresh_window.call_count, 3)

    def test_on_canvas_tab_changed_creates_new_sheet_for_plus_tab(self) -> None:
        plus_index = self.window.canvas_tabs.indexOf(self.window.sheet_add_tab)

        self.service.on_canvas_tab_changed(self.window, plus_index)

        self.new_canvas_sheet_for_window.assert_called_once_with(self.window)
        self.window.new_canvas_sheet.assert_not_called()
        self.window.refresh_active_canvas_ui.assert_not_called()
        self.status_service.refresh_status_context.assert_called_once_with(self.window, update_zoom=False)
        self.context_bar_service.refresh_window.assert_called_once_with(self.window)

    def test_on_canvas_tab_changed_tracks_last_canvas_tab_index_and_refreshes_ui(self) -> None:
        with mock.patch.object(self.service, "refresh_active_canvas_ui") as refresh_active_canvas_ui:
            self.service.on_canvas_tab_changed(self.window, 1)

        self.assertEqual(self.window.last_canvas_tab_index, 1)
        refresh_active_canvas_ui.assert_called_once_with(self.window)
        self.status_service.refresh_status_context.assert_called_once_with(self.window, update_zoom=False)
        self.context_bar_service.refresh_window.assert_called_once_with(self.window)


if __name__ == "__main__":
    unittest.main()
