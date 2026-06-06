from types import SimpleNamespace

from ui.selection_outline_state import (
    SelectionOutlineState,
    append_selection_outline_for,
    clear_selection_outlines_for,
    selection_outline_state_for,
    selection_outlines_for,
    set_selection_outlines_for,
)


def test_selection_outline_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(selection_outline_state=SelectionOutlineState(outlines=["outline"]))
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert selection_outline_state_for(canvas) is runtime_state.selection_outline_state
    assert selection_outlines_for(canvas) == ["outline"]


def test_selection_outline_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    outlines = ["existing"]
    canvas = SimpleNamespace(selection_outlines=outlines)

    state = selection_outline_state_for(canvas)

    assert state.outlines == []
    assert selection_outlines_for(canvas) == []


def test_selection_outline_state_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_selection_outlines_for(canvas, ["a"])
    append_selection_outline_for(canvas, "b")

    assert selection_outlines_for(canvas) == ["a", "b"]
    assert not hasattr(canvas, "selection_outlines")

    clear_selection_outlines_for(canvas)

    assert selection_outlines_for(canvas) == []
    assert not hasattr(canvas, "selection_outlines")
