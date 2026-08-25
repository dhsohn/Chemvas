from __future__ import annotations

from chemvas.ui.main_window_state import MainWindowState


def test_main_window_state_tracks_overrides_and_tab_index() -> None:
    state = MainWindowState()

    state.set_context_bar_page_override("template")
    state.last_canvas_tab_index = 3

    assert state.context_bar_page_override == "template"
    assert state.last_canvas_tab_index == 3

    state.clear_context_bar_page_override()

    assert state.context_bar_page_override is None


def test_main_window_state_generates_numbered_canvas_names() -> None:
    state = MainWindowState()

    assert state.next_canvas_name() == "Canvas 1"
    assert state.next_canvas_name("Result") == "Result 2"
    assert state.next_canvas_name() == "Canvas 3"
