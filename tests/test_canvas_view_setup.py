from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

import chemvas.ui.canvas_view_setup as setup
from chemvas.ui.canvas_callback_state import CanvasCallbackState, callback_state_for
from tests.runtime_services import canvas_runtime_services


def test_callback_state_for_requires_runtime_state() -> None:
    runtime_state = CanvasCallbackState()
    shadow_state = CanvasCallbackState()
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(callback_state=runtime_state),
        callback_state=shadow_state,
    )

    assert callback_state_for(canvas) is runtime_state
    with pytest.raises(AttributeError):
        callback_state_for(SimpleNamespace(callback_state=shadow_state))


def test_initialize_canvas_view_configures_view_runtime_and_services(
    monkeypatch,
) -> None:
    canvas = mock.Mock()
    canvas.viewport.return_value = mock.Mock()
    canvas.scene.return_value.selectionChanged.connect = mock.Mock()
    runtime_state = SimpleNamespace(
        graph_state="graph-state",
        insert_state="insert-state",
        history_service="history-service",
        tool_settings_state=SimpleNamespace(arrow_line_width=0.0),
    )
    callback_state = CanvasCallbackState()
    services = canvas_runtime_services(
        selection=SimpleNamespace(
            update_selection_outline=mock.Mock(), expand_selection_to_groups=mock.Mock()
        ),
        tool_controller=SimpleNamespace(set_active=mock.Mock()),
    )
    calls = []
    render_context = SimpleNamespace(bonds="bond-renderer")

    monkeypatch.setattr(
        setup,
        "set_sheet_setup_state_for",
        lambda canvas, size, orientation: calls.append("sheet"),
    )
    monkeypatch.setattr(
        setup, "set_model_for", lambda canvas, model: calls.append("model")
    )
    monkeypatch.setattr(
        setup,
        "RDKitAdapter",
        mock.Mock(side_effect=lambda: calls.append("rdkit") or "rdkit"),
    )
    monkeypatch.setattr(
        setup,
        "attach_canvas_runtime_state",
        lambda canvas: calls.append("runtime") or runtime_state,
    )
    monkeypatch.setattr(
        setup, "apply_sheet_scene_rect_for", lambda canvas: calls.append("scene-rect")
    )
    monkeypatch.setattr(
        setup,
        "build_scene_render_context",
        mock.Mock(
            side_effect=lambda **_kwargs: (
                calls.append("scene-rendering") or render_context
            )
        ),
    )
    monkeypatch.setattr(setup, "bond_line_width_for", lambda canvas: 2.5)
    monkeypatch.setattr(
        setup, "build_canvas_services", mock.Mock(return_value=services)
    )
    monkeypatch.setattr(setup, "attach_canvas_services", mock.Mock())
    monkeypatch.setattr(
        setup, "callback_state_for", mock.Mock(return_value=callback_state)
    )
    monkeypatch.setattr(setup, "QGraphicsScene", mock.Mock(return_value="scene"))
    renderer = object()
    setup.initialize_canvas_view(canvas, renderer=renderer)

    setup.QGraphicsScene.assert_called_once_with(canvas)
    canvas.setScene.assert_called_once_with("scene")
    # The sheet state is written after the runtime container exists, so it
    # lands in the container instead of on the bare canvas.
    assert calls == [
        "model",
        "rdkit",
        "runtime",
        "sheet",
        "scene-rect",
        "scene-rendering",
    ]
    assert canvas.renderer is renderer
    assert canvas.rdkit == "rdkit"
    assert canvas.bond_renderer == "bond-renderer"
    setup.RDKitAdapter.assert_called_once_with()
    setup.build_scene_render_context.assert_called_once_with(
        scene_provider=canvas.scene,
        model_provider=setup.build_scene_render_context.call_args.kwargs[
            "model_provider"
        ],
        renderer=renderer,
        state=runtime_state,
    )
    model_provider = setup.build_scene_render_context.call_args.kwargs["model_provider"]
    canvas.model = object()
    assert model_provider() is canvas.model
    assert canvas.render_context is render_context
    assert runtime_state.tool_settings_state.arrow_line_width == 2.5
    setup.build_canvas_services.assert_called_once_with(
        canvas,
        graph_state="graph-state",
        insert_state="insert-state",
        history_service="history-service",
    )
    setup.attach_canvas_services.assert_called_once_with(canvas, services)
    selection_connect = canvas.scene.return_value.selectionChanged.connect
    assert selection_connect.call_args_list == [
        mock.call(canvas.handle_scene_selection_group_changed),
        mock.call(canvas.handle_scene_selection_outline_changed),
    ]
    assert callback_state.scene_selection_group is not None
    callback_state.scene_selection_group()
    services.selection.expand_selection_to_groups.assert_called_once_with()
    assert (
        callback_state.scene_selection_outline
        is services.selection.update_selection_outline
    )
    services.tool_controller.set_active.assert_called_once_with("bond")
