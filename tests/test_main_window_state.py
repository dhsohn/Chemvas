from __future__ import annotations

from chemvas.ui.window.main_window_state import MainWindowState


def test_main_window_state_generates_numbered_canvas_names() -> None:
    state = MainWindowState()

    assert state.next_canvas_name() == "Canvas 1"
    assert state.next_canvas_name("Result") == "Result 2"
    assert state.next_canvas_name() == "Canvas 3"
