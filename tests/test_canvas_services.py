from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import chemvas.ui.canvas_services as canvas_services
import pytest
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_services import attach_canvas_services, build_canvas_services

CANONICAL_SERVICE_FIELDS = {
    "document",
    "graph",
    "input",
    "interaction",
    "scene_view",
    "handles",
    "hover",
    "scene_decoration",
    "scene_operations",
    "selection",
    "structure",
    "tooling",
    "atom_label_service",
    "history_service",
}


def _services_with_distinct_values() -> CanvasRuntimeServices:
    return CanvasRuntimeServices(
        **{
            field_name: object()
            for field_name in CanvasRuntimeServices.__dataclass_fields__
        }
    )


def test_attach_canvas_services_stores_only_the_canonical_runtime() -> None:
    canvas = SimpleNamespace()
    services = _services_with_distinct_values()

    attach_canvas_services(canvas, services)

    assert canvas.services is services
    for field_name in CanvasRuntimeServices.__dataclass_fields__:
        assert not hasattr(canvas, f"_{field_name}")


def test_canvas_runtime_services_has_no_flat_compatibility_surface() -> None:
    services = _services_with_distinct_values()

    assert set(CanvasRuntimeServices.__dataclass_fields__) == CANONICAL_SERVICE_FIELDS
    with pytest.raises(AttributeError):
        _ = services.selection_controller
    with pytest.raises(AttributeError):
        services.selection_controller = object()


def test_build_canvas_services_composes_grouped_runtimes(monkeypatch) -> None:
    canvas = SimpleNamespace()
    graph_state = object()
    insert_state = object()
    history_service = object()
    graph_service = object()
    hit_testing_service = object()
    selection_controller = object()
    move_controller = object()
    note_controller = object()
    selection_rotation_controller = object()
    insert_controller = object()
    scene_transform_controller = object()
    scene_delete_controller = object()
    scene_clipboard_controller = object()
    style_controller = object()
    color_mutation_service = object()
    mark_scene_service = object()
    decoration_build_service = object()
    atom_label_service = object()
    active_tool = SimpleNamespace(name="perspective")
    tool_controller = SimpleNamespace(active=active_tool)

    graph = SimpleNamespace(canvas_graph_service=graph_service)
    selection = SimpleNamespace(
        hit_testing_service=hit_testing_service,
        selection_controller=selection_controller,
    )
    handles = SimpleNamespace(
        handle_controller=object(),
        handle_overlay_service=object(),
        handle_mutation_service=object(),
        curved_arrow_path_service=object(),
    )
    interaction = SimpleNamespace(
        move_controller=move_controller,
        note_controller=note_controller,
        selection_rotation_controller=selection_rotation_controller,
    )
    structure = SimpleNamespace(
        canvas_atom_mutation_service=object(),
        canvas_bond_mutation_service=object(),
        structure_build_service=object(),
        insert_controller=insert_controller,
    )
    scene_operations = SimpleNamespace(
        scene_clipboard_controller=scene_clipboard_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        canvas_color_mutation_service=color_mutation_service,
    )
    tooling = SimpleNamespace(tools=tool_controller)
    scene_decoration = SimpleNamespace(
        canvas_mark_scene_service=mark_scene_service,
        scene_decoration_build_service=decoration_build_service,
        scene_decoration_service=object(),
    )
    hover = SimpleNamespace(refresh=mock.Mock())
    input_services = SimpleNamespace(
        input_controller=object(),
        pointer_controller=object(),
        tool_mode_controller=object(),
        chemdraw_shortcut_service=object(),
    )
    document = SimpleNamespace(
        canvas_document_session_service=object(),
        canvas_history_recording_service=object(),
        canvas_scene_reset_service=object(),
    )
    scene_view = SimpleNamespace(
        scene_item_controller=object(),
        selection_highlight_styler=object(),
        geometry_controller=object(),
        canvas_ring_fill_scene_service=object(),
    )

    builders = {
        "build_canvas_graph_services": mock.Mock(return_value=graph),
        "build_selection_services": mock.Mock(return_value=selection),
        "build_handle_services": mock.Mock(return_value=handles),
        "build_canvas_interaction_services": mock.Mock(return_value=interaction),
        "build_structure_services": mock.Mock(return_value=structure),
        "build_scene_operation_services": mock.Mock(return_value=scene_operations),
        "build_tool_services": mock.Mock(return_value=tooling),
        "build_scene_decoration_services": mock.Mock(return_value=scene_decoration),
        "build_hover_controller": mock.Mock(return_value=hover),
        "build_canvas_input_services": mock.Mock(return_value=input_services),
        "build_canvas_document_services": mock.Mock(return_value=document),
        "build_canvas_scene_view_services": mock.Mock(return_value=scene_view),
        "AtomLabelService": mock.Mock(return_value=atom_label_service),
    }
    for name, builder in builders.items():
        monkeypatch.setattr(canvas_services, name, builder)

    services = build_canvas_services(
        canvas,
        graph_state=graph_state,
        insert_state=insert_state,
        history_service=history_service,
    )

    assert services.graph is graph
    assert services.selection is selection
    assert services.handles is handles
    assert services.interaction is interaction
    assert services.structure is structure
    assert services.scene_operations is scene_operations
    assert services.tooling is tooling
    assert services.scene_decoration is scene_decoration
    assert services.hover is hover
    assert services.input is input_services
    assert services.document is document
    assert services.scene_view is scene_view
    assert services.atom_label_service is atom_label_service
    assert services.history_service is history_service

    builders["build_canvas_graph_services"].assert_called_once_with(
        canvas,
        graph_state=graph_state,
    )
    selection_kwargs = builders["build_selection_services"].call_args.kwargs
    assert selection_kwargs["graph_service"] is graph_service
    assert selection_kwargs["active_tool_name_provider"]() == "perspective"
    builders["build_handle_services"].assert_called_once_with(canvas)
    builders["build_canvas_interaction_services"].assert_called_once_with(
        canvas,
        selection_controller=selection_controller,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        history_service=history_service,
    )
    builders["build_structure_services"].assert_called_once_with(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        move_controller=move_controller,
        insert_state=insert_state,
        history_service=history_service,
    )
    builders["build_scene_operation_services"].assert_called_once_with(
        canvas,
        selection_controller=selection_controller,
        move_controller=move_controller,
        atom_mutation_service=structure.canvas_atom_mutation_service,
        bond_mutation_service=structure.canvas_bond_mutation_service,
        note_controller=note_controller,
        graph_service=graph_service,
        history_service=history_service,
    )
    builders["build_tool_services"].assert_called_once_with(
        canvas,
        hit_testing_service=hit_testing_service,
        selection_controller=selection_controller,
        note_controller=note_controller,
        handle_controller=handles.handle_controller,
        selection_rotation_controller=selection_rotation_controller,
        scene_delete_controller=scene_delete_controller,
        scene_transform_controller=scene_transform_controller,
        style_controller=style_controller,
        color_mutation_service=color_mutation_service,
        graph_service=graph_service,
        history_service=history_service,
    )
    builders["build_scene_decoration_services"].assert_called_once_with(
        canvas,
        history_service=history_service,
    )
    hover_call = builders["build_hover_controller"].call_args
    assert hover_call.args == (canvas,)
    assert hover_call.kwargs == {
        "selection_controller": selection_controller,
        "hit_testing_service": hit_testing_service,
        "insert_controller": insert_controller,
        "scene_decoration_build_service": decoration_build_service,
        "mark_scene_service": mark_scene_service,
        "active_tool_name_provider": hover_call.kwargs["active_tool_name_provider"],
    }
    assert hover_call.kwargs["active_tool_name_provider"]() == "perspective"
    builders["build_canvas_input_services"].assert_called_once_with(
        canvas,
        hit_testing_service=hit_testing_service,
        insert_controller=insert_controller,
        hover_controller=hover,
        tool_controller=tool_controller,
        scene_delete_controller=scene_delete_controller,
        scene_clipboard_controller=scene_clipboard_controller,
        scene_transform_controller=scene_transform_controller,
        mark_scene_service=mark_scene_service,
        history_service=history_service,
    )
    builders["build_canvas_document_services"].assert_called_once_with(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure.structure_build_service,
        history_service=history_service,
    )
    builders["AtomLabelService"].assert_called_once_with(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
        hover_refresh=hover.refresh,
    )
    builders["build_canvas_scene_view_services"].assert_called_once_with(
        canvas,
        graph_service=graph_service,
        hit_testing_service=hit_testing_service,
        history_service=history_service,
    )
