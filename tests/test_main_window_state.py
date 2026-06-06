from __future__ import annotations

from ui.main_window_state import MainWindowState


def test_main_window_state_tracks_paths_overrides_flags_and_tab_index() -> None:
    state = MainWindowState()

    state.current_file_path = "/tmp/example.chemvas"
    state.set_context_bar_page_override("template")
    state.last_canvas_tab_index = 3
    state.tab_reactions_suspended = True
    state.repositioning_add_tab = True

    assert state.current_file_path == "/tmp/example.chemvas"
    assert state.context_bar_page_override == "template"
    assert state.last_canvas_tab_index == 3
    assert state.tab_reactions_suspended is True
    assert state.repositioning_add_tab is True

    state.clear_context_bar_page_override()

    assert state.context_bar_page_override is None


def test_main_window_state_generates_and_resets_sheet_names() -> None:
    state = MainWindowState()

    assert state.next_canvas_sheet_name() == "Sheet 1"
    assert state.next_canvas_sheet_name("Result") == "Result 2"
    assert state.next_result_canvas_name("Result") == "Result 1"
    assert state.next_result_canvas_name("Result") == "Result 2"

    state.reset_canvas_name_counter(["Sheet 1", "Sheet 4", "Analysis"])

    assert state.next_canvas_sheet_name() == "Sheet 5"
