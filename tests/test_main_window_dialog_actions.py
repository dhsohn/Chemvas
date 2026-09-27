import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.window.main_window_ports import active_canvas_for_window


class MainWindowDialogActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_zoom_label_double_click_applies_typed_percent(self) -> None:
        status_service = self.window.services.status_service
        with mock.patch(
            "chemvas.ui.window.main_window_status_service.prompt_zoom_percent",
            return_value=250,
        ):
            status_service._prompt_zoom(self.window)

        self.assertEqual(status_service.zoom_label.text(), "250%")

    def test_zoom_label_double_click_cancel_leaves_zoom_unchanged(self) -> None:
        status_service = self.window.services.status_service
        before = status_service.zoom_label.text()
        with mock.patch(
            "chemvas.ui.window.main_window_status_service.prompt_zoom_percent",
            return_value=None,
        ):
            status_service._prompt_zoom(self.window)

        self.assertEqual(status_service.zoom_label.text(), before)

    def test_canvas_name_helpers_cover_missing_active_canvas_paths(self) -> None:
        with mock.patch.object(
            type(self.window.tab_references), "active_canvas_or_none", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "No active canvas."):
                _ = active_canvas_for_window(self.window)

        with mock.patch.object(
            type(self.window.tab_references), "active_canvas_tab_index", return_value=-1
        ):
            self.assertEqual(
                self.window.tab_references.active_canvas_name(
                    active_canvas_for_window(self.window)
                ),
                "",
            )

        self.assertFalse(hasattr(self.window.runtime_state, "next_result_canvas_name"))

    def test_icon_helpers_stay_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "_icon_add_canvas"))

    def test_status_bar_exposes_structured_context_and_transient_messages(self) -> None:
        status_service = self.window.services.status_service

        self.assertEqual(
            status_service.status_context_texts(),
            {
                "tool": "Tool: Bond",
                "sheet": "Canvas: Canvas 1",
                "selection": "Selection: 0",
                "zoom_caption": "Zoom",
                "zoom": "100%",
            },
        )

        self.assertFalse(hasattr(self.window, "zoom_status_tip"))
        status_service.update_zoom_label(175)
        self.assertEqual(status_service.status_context_texts()["zoom"], "175%")

        self.window.statusBar().showMessage("Saved")
        self.assertEqual(self.window.statusBar().currentMessage(), "Saved")
