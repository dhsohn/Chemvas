from types import SimpleNamespace

from chemvas.ui.selection.selection_state import (
    SelectionState,
    append_selection_outline_for,
    clear_selection_outlines_for,
    set_selection_outlines_for,
)
from tests.runtime_state import canvas_runtime_state


def test_selection_outline_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(
        selection_state=SelectionState(outlines=["outline"])
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert canvas.runtime_state.selection_state is runtime_state.selection_state
    assert canvas.runtime_state.selection_state.outlines == ["outline"]


def test_selection_outline_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    outlines = ["existing"]
    canvas = SimpleNamespace(
        selection_outlines=outlines,
        runtime_state=canvas_runtime_state(selection_state=SelectionState()),
    )

    state = canvas.runtime_state.selection_state

    assert state.outlines == []
    assert canvas.runtime_state.selection_state.outlines == []


def test_selection_outline_state_setters_update_state_without_canvas_attr_mirror() -> (
    None
):
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(selection_state=SelectionState())
    )

    set_selection_outlines_for(canvas, ["a"])
    append_selection_outline_for(canvas, "b")

    assert canvas.runtime_state.selection_state.outlines == ["a", "b"]
    assert not hasattr(canvas, "selection_outlines")

    clear_selection_outlines_for(canvas)

    assert canvas.runtime_state.selection_state.outlines == []
    assert not hasattr(canvas, "selection_outlines")
