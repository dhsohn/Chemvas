from __future__ import annotations

from types import SimpleNamespace

from chemvas.ui.sheet_setup_state import (
    SheetSetupState,
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)

from tests.runtime_state import canvas_runtime_state


def test_sheet_setup_state_reads_the_runtime_container() -> None:
    state = SheetSetupState(size_name="A4", orientation="portrait")
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(sheet_setup_state=state)
    )

    assert sheet_setup_state_for(canvas) is state
    assert sheet_setup_values_for(canvas) == ("A4", "portrait")


def test_set_sheet_setup_state_updates_only_the_canonical_state() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(sheet_setup_state=SheetSetupState())
    )

    assert set_sheet_setup_state_for(canvas, "a4", "portrait") == ("A4", "portrait")

    assert sheet_setup_values_for(canvas) == ("A4", "portrait")
    assert not hasattr(canvas, "sheet_size")
    assert not hasattr(canvas, "sheet_orientation")
