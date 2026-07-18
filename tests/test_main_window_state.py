from __future__ import annotations

from chemvas.ui.main_window_state import MainWindowState


def test_main_window_state_tracks_paths_overrides_flags_and_tab_index() -> None:
    state = MainWindowState()

    state.set_context_bar_page_override("template")
    state.last_canvas_tab_index = 3
    state.tab_reactions_suspended = True

    assert state.context_bar_page_override == "template"
    assert state.last_canvas_tab_index == 3
    assert state.tab_reactions_suspended is True

    state.clear_context_bar_page_override()

    assert state.context_bar_page_override is None


def test_main_window_state_generates_and_resets_canvas_names() -> None:
    state = MainWindowState()

    assert state.next_canvas_name() == "Canvas 1"
    assert state.next_canvas_name("Result") == "Result 2"

    state.reset_canvas_name_counter(["Canvas 1", "Canvas 4", "Analysis"])

    assert state.next_canvas_name() == "Canvas 5"
