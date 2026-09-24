from types import SimpleNamespace

from chemvas.ui.canvas.canvas_tool_settings_state import (
    CanvasToolSettingsState,
    set_tool_setting_for,
)
from tests.runtime_state import canvas_runtime_state


def test_tool_settings_state_for_uses_runtime_state() -> None:
    runtime_state = canvas_runtime_state(
        tool_settings_state=CanvasToolSettingsState(active_bond_style="hash")
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert canvas.runtime_state.tool_settings_state is runtime_state.tool_settings_state
    assert canvas.runtime_state.tool_settings_state.active_bond_style == "hash"


def test_tool_settings_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    canvas = SimpleNamespace(
        active_bond_style="wedge",
        active_bond_order=1,
        mark_kind="minus",
        active_arrow_type="equilibrium",
        active_bracket_type="dagger",
        arrow_line_width=2.5,
        runtime_state=canvas_runtime_state(
            tool_settings_state=CanvasToolSettingsState()
        ),
    )

    state = canvas.runtime_state.tool_settings_state

    assert state.active_bond_style == "single"
    assert state.active_bond_order == 1
    assert state.mark_kind == "plus"
    assert state.active_arrow_type == "reaction"
    assert state.active_bracket_type == "square_pair"
    assert state.arrow_line_width == 1.0


def test_set_tool_setting_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(
            tool_settings_state=CanvasToolSettingsState()
        )
    )

    set_tool_setting_for(canvas, "active_bond_style", "dotted")
    set_tool_setting_for(canvas, "active_bond_order", 1)
    set_tool_setting_for(canvas, "snap_angle_step", 45)

    state = canvas.runtime_state.tool_settings_state
    assert state.active_bond_style == "dotted"
    assert state.active_bond_order == 1
    assert state.snap_angle_step == 45
    assert not hasattr(canvas, "active_bond_style")
    assert not hasattr(canvas, "active_bond_order")
    assert not hasattr(canvas, "snap_angle_step")
