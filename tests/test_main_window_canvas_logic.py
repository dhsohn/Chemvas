import unittest
from types import SimpleNamespace
from unittest import mock

from ui.main_window_canvas_logic import (
    RestorableCanvasSheet,
    active_canvas_sheet_index,
    active_canvas_tab_index,
    bind_active_canvas_callbacks,
    build_workbook_sheet_states,
    canvas_sheet_name_counter,
    copy_canvas_template_settings,
    resolve_active_canvas,
    restorable_canvas_sheets,
)


class MainWindowCanvasLogicTest(unittest.TestCase):
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
        self.assertEqual(active_canvas_sheet_index(entries, None), 0)
        self.assertEqual(active_canvas_sheet_index(entries, canvas_b), 1)
        self.assertEqual(active_canvas_sheet_index(entries, object()), 0)

    def test_copy_canvas_template_settings_copies_known_fields(self) -> None:
        target = SimpleNamespace(
            renderer=SimpleNamespace(set_bond_length=mock.Mock()),
            set_sheet_setup=mock.Mock(),
        )
        template = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=24.0)),
            sheet_size="A4",
            sheet_orientation="portrait",
            arrow_line_width=2.5,
            arrow_head_scale=0.35,
            orbital_phase_enabled=True,
            text_font_size=14,
            text_font_weight=600,
            text_italic=True,
            mark_kind="minus",
        )

        copy_canvas_template_settings(target, template)
        copy_canvas_template_settings(target, None)

        target.renderer.set_bond_length.assert_called_once_with(24.0)
        target.set_sheet_setup.assert_called_once_with("A4", "portrait")
        self.assertEqual(target.arrow_line_width, 2.5)
        self.assertEqual(target.arrow_head_scale, 0.35)
        self.assertTrue(target.orbital_phase_enabled)
        self.assertEqual(target.text_font_size, 14)
        self.assertEqual(target.text_font_weight, 600)
        self.assertTrue(target.text_italic)
        self.assertEqual(target.mark_kind, "minus")

    def test_bind_active_canvas_callbacks_assigns_only_active_canvas(self) -> None:
        active_canvas = SimpleNamespace(
            set_selection_info_callback=mock.Mock(),
            set_error_callback=mock.Mock(),
            set_tool_change_callback=mock.Mock(),
            set_zoom_callback=mock.Mock(),
            set_history_change_callback=mock.Mock(),
        )
        inactive_canvas = SimpleNamespace(
            set_selection_info_callback=mock.Mock(),
            set_error_callback=mock.Mock(),
            set_tool_change_callback=mock.Mock(),
            set_zoom_callback=mock.Mock(),
            set_history_change_callback=mock.Mock(),
        )
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

        active_canvas.set_selection_info_callback.assert_called_once_with(selection_info_callback)
        active_canvas.set_error_callback.assert_called_once_with(None)
        active_canvas.set_tool_change_callback.assert_called_once_with(tool_change_callback)
        active_canvas.set_zoom_callback.assert_called_once_with(zoom_callback)
        active_canvas.set_history_change_callback.assert_called_once_with(history_change_callback)
        inactive_canvas.set_selection_info_callback.assert_called_once_with(None)
        inactive_canvas.set_error_callback.assert_called_once_with(None)
        inactive_canvas.set_tool_change_callback.assert_called_once_with(None)
        inactive_canvas.set_zoom_callback.assert_called_once_with(None)
        inactive_canvas.set_history_change_callback.assert_called_once_with(None)

    def test_build_workbook_sheet_states_uses_tab_names_or_sheet_fallback(self) -> None:
        canvas_a = SimpleNamespace(snapshot_state=mock.Mock(return_value={"atoms": [1]}))
        canvas_b = SimpleNamespace(snapshot_state=mock.Mock(return_value={"atoms": [2]}))

        sheets = build_workbook_sheet_states(
            [(0, canvas_a), (4, canvas_b)],
            tab_text_at=lambda index: {0: "Reactant", 4: ""}[index],
        )

        self.assertEqual(
            sheets,
            [
                {"name": "Reactant", "kind": "canvas", "content": {"atoms": [1]}},
                {"name": "Sheet 2", "kind": "canvas", "content": {"atoms": [2]}},
            ],
        )

    def test_restorable_canvas_sheets_returns_canvas_payloads(self) -> None:
        sheets = restorable_canvas_sheets(
            [
                {"name": "Reactant", "kind": "canvas", "content": {"atoms": [1]}},
                {"name": "Product", "kind": "canvas", "content": {"atoms": [2]}},
            ],
        )

        self.assertEqual(
            sheets,
            [
                RestorableCanvasSheet(name="Reactant", content={"atoms": [1]}),
                RestorableCanvasSheet(name="Product", content={"atoms": [2]}),
            ],
        )

    def test_restorable_canvas_sheets_rejects_invalid_entries(self) -> None:
        invalid_sheet_groups = (
            ["skip-me"],
            [{"name": "Summary", "kind": "result", "content": {"atoms": [9]}}],
            [{"kind": "canvas", "content": {"atoms": [2]}}],
            [{"name": "Broken", "kind": "canvas", "content": "not-a-dict"}],
        )

        for sheet_states in invalid_sheet_groups:
            with self.subTest(sheet_states=sheet_states):
                with self.assertRaises((KeyError, ValueError)):
                    restorable_canvas_sheets(sheet_states)

    def test_canvas_sheet_name_counter_tracks_default_sheet_names(self) -> None:
        self.assertEqual(canvas_sheet_name_counter([]), 0)
        self.assertEqual(canvas_sheet_name_counter(["Sheet draft", "Sheet 2", "Sheet 9"]), 9)
        self.assertEqual(canvas_sheet_name_counter(["Reactant", "Sheet 2", "Sheet 9"]), 9)
        self.assertEqual(canvas_sheet_name_counter(["Result 1"], prefix="Result"), 1)


if __name__ == "__main__":
    unittest.main()
