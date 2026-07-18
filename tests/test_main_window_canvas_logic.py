import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import history_state_for
from chemvas.ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from chemvas.ui.canvas_tool_settings_state import (
    set_tool_setting_for,
    tool_settings_state_for,
)
from chemvas.ui.main_window_canvas_logic import (
    active_canvas_index,
    active_canvas_tab_index,
    bind_active_canvas_callbacks,
    canvas_name_counter,
    copy_canvas_template_settings,
    resolve_active_canvas,
)
from chemvas.ui.selection_info_state import selection_info_state_for


class MainWindowCanvasLogicTest(unittest.TestCase):
    @staticmethod
    def _canvas_with_history() -> SimpleNamespace:
        canvas = SimpleNamespace()
        canvas.runtime_state = SimpleNamespace(
            history_service=CanvasHistoryService(canvas, history_state_for(canvas))
        )
        return canvas

    def test_resolve_active_canvas_prefers_current_then_last_then_first(self) -> None:
        canvas_a = object()
        canvas_b = object()
        entries = [(0, canvas_a), (2, canvas_b)]

        self.assertIs(resolve_active_canvas(canvas_b, 0, entries), canvas_b)
        self.assertIs(resolve_active_canvas(object(), 2, entries), canvas_b)
        self.assertIs(resolve_active_canvas(object(), 99, entries), canvas_a)
        self.assertIsNone(resolve_active_canvas(object(), 0, ()))

    def test_active_canvas_index_helpers_return_expected_positions(self) -> None:
        canvas_a = object()
        canvas_b = object()
        entries = [(1, canvas_a), (3, canvas_b)]

        self.assertEqual(active_canvas_tab_index(entries, None), -1)
        self.assertEqual(active_canvas_tab_index(entries, canvas_b), 3)
        self.assertEqual(active_canvas_tab_index(entries, object()), -1)
        self.assertEqual(active_canvas_index(entries, None), 0)
        self.assertEqual(active_canvas_index(entries, canvas_b), 1)
        self.assertEqual(active_canvas_index(entries, object()), 0)

    def test_copy_canvas_template_settings_copies_known_fields(self) -> None:
        target = SimpleNamespace(
            renderer=SimpleNamespace(set_bond_length=mock.Mock()),
            sheet_size="Letter",
            sheet_orientation="landscape",
            setSceneRect=mock.Mock(),
            viewport=lambda: SimpleNamespace(update=mock.Mock()),
        )
        template = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=24.0)),
            sheet_size="A4",
            sheet_orientation="portrait",
        )
        set_tool_setting_for(template, "arrow_line_width", 2.5)
        set_tool_setting_for(template, "arrow_head_scale", 0.35)
        set_tool_setting_for(template, "orbital_phase_enabled", True)
        set_tool_setting_for(template, "mark_kind", "minus")
        set_text_style_for(template, "text_font_size", 14)
        set_text_style_for(template, "text_font_weight", 600)
        set_text_style_for(template, "text_italic", True)

        copy_canvas_template_settings(target, template)
        copy_canvas_template_settings(target, None)

        target.renderer.set_bond_length.assert_called_once_with(24.0)
        self.assertEqual(target.sheet_size, "A4")
        self.assertEqual(target.sheet_orientation, "portrait")
        target.setSceneRect.assert_called_once()
        tool_settings = tool_settings_state_for(target)
        self.assertEqual(tool_settings.arrow_line_width, 2.5)
        self.assertEqual(tool_settings.arrow_head_scale, 0.35)
        self.assertTrue(tool_settings.orbital_phase_enabled)
        text_style = text_style_state_for(target)
        self.assertEqual(text_style.text_font_size, 14)
        self.assertEqual(text_style.text_font_weight, 600)
        self.assertTrue(text_style.text_italic)
        self.assertEqual(tool_settings.mark_kind, "minus")

    def test_bind_active_canvas_callbacks_assigns_only_active_canvas(self) -> None:
        active_canvas = self._canvas_with_history()
        inactive_canvas = self._canvas_with_history()
        selection_info_callback = object()
        tool_change_callback = object()
        zoom_callback = object()
        history_change_callback = object()

        bind_active_canvas_callbacks(
            [inactive_canvas, active_canvas],
            active_canvas,
            selection_info_callback=selection_info_callback,
            tool_change_callback=tool_change_callback,
            zoom_callback=zoom_callback,
            history_change_callback=history_change_callback,
        )

        self.assertIs(
            selection_info_state_for(active_canvas).callback, selection_info_callback
        )
        self.assertIsNone(callback_state_for(active_canvas).error)
        self.assertIs(
            callback_state_for(active_canvas).tool_change, tool_change_callback
        )
        self.assertIs(callback_state_for(active_canvas).zoom, zoom_callback)
        self.assertIs(
            history_state_for(active_canvas).change_callback, history_change_callback
        )
        self.assertIsNone(selection_info_state_for(inactive_canvas).callback)
        self.assertIsNone(callback_state_for(inactive_canvas).error)
        self.assertIsNone(callback_state_for(inactive_canvas).tool_change)
        self.assertIsNone(callback_state_for(inactive_canvas).zoom)
        self.assertIsNone(history_state_for(inactive_canvas).change_callback)

    def test_canvas_name_counter_tracks_default_canvas_names(self) -> None:
        self.assertEqual(canvas_name_counter([]), 0)
        self.assertEqual(
            canvas_name_counter(["Canvas draft", "Canvas 2", "Canvas 9"]), 9
        )
        self.assertEqual(canvas_name_counter(["Reactant", "Canvas 2", "Canvas 9"]), 9)
        self.assertEqual(canvas_name_counter(["Result 1"], prefix="Result"), 1)


if __name__ == "__main__":
    unittest.main()
