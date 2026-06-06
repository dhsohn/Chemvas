from __future__ import annotations

from types import SimpleNamespace

from ui.active_tool_reference import ActiveToolReference


def test_active_tool_reference_resolves_late_bound_tool_controller() -> None:
    reference = ActiveToolReference()

    assert reference.active_tool() is None
    assert reference.active_tool_name() is None

    active_tool = SimpleNamespace(name="select")
    reference.tool_controller = SimpleNamespace(active=active_tool)

    assert reference.active_tool() is active_tool
    assert reference.active_tool_name() == "select"


def test_active_tool_reference_ignores_blank_tool_name() -> None:
    reference = ActiveToolReference(
        tool_controller=SimpleNamespace(active=SimpleNamespace(name="")),
    )

    assert reference.active_tool_name() is None
