from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest import mock

import pytest

from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

_REQUIRED_COLLABORATORS = (
    "insert_controller",
    "hover_refresh",
    "set_active_tool",
    "history_service",
)


def _collaborators() -> dict[str, object]:
    return {
        "insert_controller": SimpleNamespace(
            cancel_template_insert=mock.Mock(),
            begin_ring_template_insert=mock.Mock(),
        ),
        "hover_refresh": mock.Mock(),
        "set_active_tool": mock.Mock(),
        "history_service": SimpleNamespace(push=mock.Mock()),
    }


def test_canvas_tool_mode_controller_requires_its_collaborators() -> None:
    parameters = inspect.signature(CanvasToolModeController.__init__).parameters
    for name in _REQUIRED_COLLABORATORS:
        assert name in parameters
        assert parameters[name].default is inspect.Parameter.empty

    canvas = SimpleNamespace()
    for omitted in _REQUIRED_COLLABORATORS:
        kwargs = {
            name: value for name, value in _collaborators().items() if name != omitted
        }
        with pytest.raises(TypeError):
            CanvasToolModeController(canvas, **kwargs)


def test_set_tool_benzene_starts_template_insert() -> None:
    collaborators = _collaborators()
    canvas = SimpleNamespace(
        services=canvas_runtime_services(
            selection=SimpleNamespace(update_selection_outline=mock.Mock()),
        ),
        runtime_state=canvas_runtime_state(
            callback_state=SimpleNamespace(tool_change=None),
            insert_state=SimpleNamespace(template_active=False),
        ),
    )
    controller = CanvasToolModeController(canvas, **collaborators)

    controller.set_tool("benzene")

    collaborators["set_active_tool"].assert_called_once_with("benzene")
    collaborators[
        "insert_controller"
    ].begin_ring_template_insert.assert_called_once_with(6, "benzene")
    collaborators["hover_refresh"].assert_called_once_with(render_insert_preview=True)
