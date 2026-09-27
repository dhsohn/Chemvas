from types import SimpleNamespace

from chemvas.ui.selection.selection_state import (
    SelectionState,
    append_selection_outline_for,
    clear_selection_outlines_for,
    set_selection_outlines_for,
)
from tests.runtime_state import canvas_runtime_state


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
