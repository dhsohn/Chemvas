from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import ui.canvas_view_setup as setup


def test_initialize_canvas_view_configures_view_runtime_and_services(monkeypatch) -> None:
    canvas = mock.Mock()
    canvas.viewport.return_value = mock.Mock()
    canvas.scene.return_value.selectionChanged.connect = mock.Mock()
    runtime_state = SimpleNamespace(
        graph_state="graph-state",
        insert_state="insert-state",
        history_service="history-service",
        tool_settings_state=SimpleNamespace(arrow_line_width=0.0),
    )
    services = SimpleNamespace(
        selection_controller=SimpleNamespace(update_selection_outline=mock.Mock()),
        tools=SimpleNamespace(set_active=mock.Mock()),
    )
    calls = []

    monkeypatch.setattr(setup, "set_sheet_setup_state_for", lambda canvas, size, orientation: calls.append("sheet"))
    monkeypatch.setattr(setup, "model_for", lambda canvas: calls.append("model"))
    monkeypatch.setattr(setup, "renderer_for", lambda canvas: calls.append("renderer"))
    monkeypatch.setattr(setup, "rdkit_adapter_for", lambda canvas: calls.append("rdkit"))
    monkeypatch.setattr(setup, "attach_canvas_runtime_state", lambda canvas: runtime_state)
    monkeypatch.setattr(setup, "apply_sheet_scene_rect_for", lambda canvas: calls.append("scene-rect"))
    monkeypatch.setattr(setup, "bond_renderer_for", lambda canvas: calls.append("bond-renderer"))
    monkeypatch.setattr(setup, "bond_line_width_for", lambda canvas: 2.5)
    monkeypatch.setattr(setup, "build_canvas_services", mock.Mock(return_value=services))
    monkeypatch.setattr(setup, "attach_canvas_services", mock.Mock())
    monkeypatch.setattr(setup, "QGraphicsScene", mock.Mock(return_value="scene"))
    monkeypatch.setattr(setup, "expand_selection_to_groups_for", mock.Mock())

    setup.initialize_canvas_view(canvas)

    setup.QGraphicsScene.assert_called_once_with(canvas)
    canvas.setScene.assert_called_once_with("scene")
    assert calls == ["sheet", "model", "renderer", "rdkit", "scene-rect", "bond-renderer"]
    assert runtime_state.tool_settings_state.arrow_line_width == 2.5
    setup.build_canvas_services.assert_called_once_with(
        canvas,
        graph_state="graph-state",
        insert_state="insert-state",
        history_service="history-service",
    )
    setup.attach_canvas_services.assert_called_once_with(canvas, services)
    selection_connect = canvas.scene.return_value.selectionChanged.connect
    assert selection_connect.call_count == 2
    expand_slot = selection_connect.call_args_list[0].args[0]
    expand_slot()
    setup.expand_selection_to_groups_for.assert_called_once_with(canvas)
    assert selection_connect.call_args_list[1].args[0] is services.selection_controller.update_selection_outline
    services.tools.set_active.assert_called_once_with("bond")
