import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QLabel, QTabWidget, QWidget
except ModuleNotFoundError:
    QApplication = None
    QLabel = None
    QTabWidget = None
    QWidget = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    try:
        from ui.canvas_view import CanvasView
        from ui.main_window_active_canvas_ui_service import MainWindowActiveCanvasUIService
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
        self.preview_3d = SimpleNamespace(_rdkit=None, refresh_from_canvas=mock.Mock())
        self._atom_input = mock.Mock()
        self._zoom_label = QLabel("100%")
        self._sync_tool_actions_from_canvas = mock.Mock()
        self._new_canvas_sheet = mock.Mock()
        self._refresh_active_canvas_ui = mock.Mock()
        self._update_zoom_label = mock.Mock()
        self._handle_selection_info = mock.Mock()

    @property
    def canvas(self):
        widget = self.canvas_tabs.currentWidget()
        if isinstance(widget, CanvasView):
            return widget
        raise RuntimeError("No active canvas.")

    def _all_canvases(self) -> list[CanvasView]:
        return [self.canvas_a, self.canvas_b]


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
        self.service = MainWindowActiveCanvasUIService()

    def tearDown(self) -> None:
        self.window.canvas_tabs.deleteLater()
        self.app.processEvents()

    def test_bind_active_canvas_updates_preview_rdkit_and_callbacks(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)

        with (
            mock.patch.object(self.window.canvas_a, "set_selection_info_callback") as inactive_selection,
            mock.patch.object(self.window.canvas_a, "set_tool_change_callback") as inactive_tool_change,
            mock.patch.object(self.window.canvas_a, "set_zoom_callback") as inactive_zoom,
            mock.patch.object(self.window.canvas_b, "set_selection_info_callback") as active_selection,
            mock.patch.object(self.window.canvas_b, "set_tool_change_callback") as active_tool_change,
            mock.patch.object(self.window.canvas_b, "set_zoom_callback") as active_zoom,
        ):
            self.service.bind_active_canvas(self.window)

        self.assertIs(self.window.preview_3d._rdkit, self.window.canvas_b.rdkit)
        active_selection.assert_called_once_with(self.window._handle_selection_info)
        active_tool_change.assert_called_once_with(self.window._sync_tool_actions_from_canvas)
        active_zoom.assert_called_once_with(self.window._update_zoom_label)
        inactive_selection.assert_called_once_with(None)
        inactive_tool_change.assert_called_once_with(None)
        inactive_zoom.assert_called_once_with(None)

    def test_handle_selection_info_refreshes_preview_from_active_canvas(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)

        self.service.handle_selection_info(self.window, "H2O", "18.0")

        self.window.preview_3d.refresh_from_canvas.assert_called_once_with(self.window.canvas_b)

    def test_current_zoom_percent_rounds_scale_and_clamps_minimum(self) -> None:
        cases = (
            (2.34, 234),
            (0.0, 1),
        )
        for scale, expected in cases:
            with self.subTest(scale=scale):
                transform = SimpleNamespace(m11=lambda scale=scale: scale)
                with mock.patch.object(self.window.canvas_a, "transform", return_value=transform):
                    self.assertEqual(self.service.current_zoom_percent(self.window), expected)

    def test_refresh_active_canvas_ui_rebinds_updates_inputs_and_refreshes_preview(self) -> None:
        self.window.canvas_tabs.setCurrentWidget(self.window.canvas_b)
        transform = SimpleNamespace(m11=lambda: 2.75)

        with (
            mock.patch.object(self.window.canvas_a, "set_selection_info_callback") as inactive_selection,
            mock.patch.object(self.window.canvas_a, "set_tool_change_callback") as inactive_tool_change,
            mock.patch.object(self.window.canvas_a, "set_zoom_callback") as inactive_zoom,
            mock.patch.object(self.window.canvas_b, "set_selection_info_callback") as active_selection,
            mock.patch.object(self.window.canvas_b, "set_tool_change_callback") as active_tool_change,
            mock.patch.object(self.window.canvas_b, "set_zoom_callback") as active_zoom,
            mock.patch.object(self.window.canvas_b, "transform", return_value=transform),
            mock.patch.object(self.window.canvas_b, "get_atom_symbol", return_value="N"),
        ):
            self.service.refresh_active_canvas_ui(self.window)

        self.assertEqual(
            self.window._atom_input.method_calls,
            [mock.call.blockSignals(True), mock.call.setText("N"), mock.call.blockSignals(False)],
        )
        self.window._update_zoom_label.assert_called_once_with(275)
        self.window._sync_tool_actions_from_canvas.assert_called_once_with()
        self.window.preview_3d.refresh_from_canvas.assert_called_once_with(self.window.canvas_b)
        self.assertIs(self.window.preview_3d._rdkit, self.window.canvas_b.rdkit)
        active_selection.assert_called_once_with(self.window._handle_selection_info)
        active_tool_change.assert_called_once_with(self.window._sync_tool_actions_from_canvas)
        active_zoom.assert_called_once_with(self.window._update_zoom_label)
        inactive_selection.assert_called_once_with(None)
        inactive_tool_change.assert_called_once_with(None)
        inactive_zoom.assert_called_once_with(None)

    def test_on_canvas_tab_changed_ignores_suspended_invalid_and_non_canvas_targets(self) -> None:
        other_widget = QWidget()
        other_index = self.window.canvas_tabs.insertTab(2, other_widget, "Other")

        self.service.on_canvas_tab_changed(self.window, -1)
        self.window._suspend_canvas_tab_reactions = True
        self.service.on_canvas_tab_changed(self.window, 0)
        self.window._suspend_canvas_tab_reactions = False
        self.service.on_canvas_tab_changed(self.window, other_index)

        self.window._new_canvas_sheet.assert_not_called()
        self.window._refresh_active_canvas_ui.assert_not_called()
        self.assertEqual(self.window._last_canvas_tab_index, 0)

    def test_on_canvas_tab_changed_creates_new_sheet_for_plus_tab(self) -> None:
        plus_index = self.window.canvas_tabs.indexOf(self.window._sheet_add_tab)

        self.service.on_canvas_tab_changed(self.window, plus_index)

        self.window._new_canvas_sheet.assert_called_once_with()
        self.window._refresh_active_canvas_ui.assert_not_called()

    def test_on_canvas_tab_changed_tracks_last_canvas_tab_index_and_refreshes_ui(self) -> None:
        with mock.patch.object(self.service, "refresh_active_canvas_ui") as refresh_active_canvas_ui:
            self.service.on_canvas_tab_changed(self.window, 1)

        self.assertEqual(self.window._last_canvas_tab_index, 1)
        refresh_active_canvas_ui.assert_called_once_with(self.window)


if __name__ == "__main__":
    unittest.main()
