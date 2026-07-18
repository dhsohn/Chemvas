from __future__ import annotations

from types import SimpleNamespace

from chemvas.ui.sheet_setup_state import (
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)


def test_sheet_setup_state_initializes_from_legacy_canvas_attrs() -> None:
    canvas = SimpleNamespace(sheet_size="A4", sheet_orientation="portrait")

    state = sheet_setup_state_for(canvas)

    assert (state.size_name, state.orientation) == ("A4", "portrait")
    assert sheet_setup_values_for(canvas) == ("A4", "portrait")


def test_set_sheet_setup_state_updates_state_and_compat_canvas_attrs() -> None:
    canvas = SimpleNamespace()

    assert set_sheet_setup_state_for(canvas, "a4", "vertical") == ("A4", "portrait")

    assert sheet_setup_values_for(canvas) == ("A4", "portrait")
    assert canvas.sheet_size == "A4"
    assert canvas.sheet_orientation == "portrait"
