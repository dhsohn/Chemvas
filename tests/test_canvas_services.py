from __future__ import annotations

from types import SimpleNamespace

import chemvas.ui.canvas_runtime_services as runtime_services_module
import chemvas.ui.canvas_services as canvas_services
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_services import (
    CanvasServices,
    attach_canvas_services,
    build_canvas_services,
)

CANONICAL_SERVICE_GROUPS = {
    "auxiliary",
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
    "history_service",
}


def _services_with_distinct_values() -> CanvasServices:
    return CanvasServices(
        **{field_name: object() for field_name in CanvasServices.__dataclass_fields__}
    )


def test_attach_canvas_services_does_not_create_private_service_aliases() -> None:
    canvas = SimpleNamespace()
    services = _services_with_distinct_values()

    attach_canvas_services(canvas, services)

    assert canvas.services is services
    assert not hasattr(canvas, "tools")
    for field_name in CanvasServices.__dataclass_fields__:
        assert not hasattr(canvas, f"_{field_name}")


def test_canvas_runtime_services_has_grouped_canonical_surface() -> None:
    assert CanvasServices is CanvasRuntimeServices
    assert set(CanvasRuntimeServices.__dataclass_fields__) == CANONICAL_SERVICE_GROUPS
    assert CANONICAL_SERVICE_GROUPS.isdisjoint(
        runtime_services_module._LEGACY_SERVICE_PATHS
    )


def test_build_canvas_services_uses_selection_service_bundle(monkeypatch) -> None:
    canvas_graph_service = object()
    hit_testing_service = object()
    selection_controller = object()
    active_tool = SimpleNamespace(name="perspective")
    tool_controller = SimpleNamespace(set_active=object(), active=active_tool)
    graph_bundle = SimpleNamespace(canvas_graph_service=canvas_graph_service)
    selection_bundle = SimpleNamespace(
        hit_testing_service=hit_testing_service,
        selection_controller=selection_controller,
    )
    tool_bundle = SimpleNamespace(tools=tool_controller)
    build_canvas_graph_services_calls = []
    build_selection_services_calls = []
    build_canvas_auxiliary_services_calls = []
    build_handle_services_calls = []
    build_hover_services_calls = []
    build_canvas_interaction_services_calls = []
    build_canvas_input_services_calls = []
    build_canvas_document_services_calls = []
    build_scene_decoration_services_calls = []
    build_scene_operation_services_calls = []
    build_canvas_scene_view_services_calls = []
    build_structure_services_calls = []
    build_tool_services_calls = []

    def fake_build_canvas_graph_services(canvas, *, graph_state):
        build_canvas_graph_services_calls.append((canvas, graph_state))
        return graph_bundle

    def fake_build_selection_services(
        canvas, *, graph_service, active_tool_name_provider=None
    ):
        build_selection_services_calls.append(
            (canvas, graph_service, active_tool_name_provider)
        )
        return selection_bundle

    auxiliary_bundle = SimpleNamespace(
        atom_label_service=object(),
        benzene_preview_service=object(),
        structure_insert_service=object(),
    )

    def fake_build_canvas_auxiliary_services(
        canvas,
        *,
        move_controller,
        graph_service,
        history_service,
        hover_refresh,
        structure_build_service,
        note_controller,
    ):
        build_canvas_auxiliary_services_calls.append(
            (
                canvas,
                move_controller,
                graph_service,
                history_service,
                hover_refresh,
                structure_build_service,
                note_controller,
            )
        )
        return auxiliary_bundle

    def fake_build_tool_services(
        canvas,
        *,
        hit_testing_service,
        selection_controller,
        note_controller,
        handle_controller,
        selection_rotation_controller,
        scene_delete_controller,
        scene_transform_controller,
        style_controller,
        color_mutation_service,
        graph_service,
        history_service,
    ):
        build_tool_services_calls.append(
            (
                canvas,
                hit_testing_service,
                selection_controller,
                note_controller,
                handle_controller,
                selection_rotation_controller,
                scene_delete_controller,
                scene_transform_controller,
                style_controller,
                color_mutation_service,
                graph_service,
                history_service,
            )
        )
        return tool_bundle

    handle_bundle = SimpleNamespace(
        handle_controller=object(),
        handle_overlay_service=object(),
        handle_mutation_service=object(),
        curved_arrow_path_service=object(),
    )

    def fake_build_handle_services(canvas):
        build_handle_services_calls.append(canvas)
        return handle_bundle

    hover_bundle = SimpleNamespace(
        hover_interaction_service=object(),
        hover_scene_service=object(),
        mark_hover_preview_service=object(),
        bond_hover_preview_service=object(),
        hover_refresh=lambda: None,
    )

    def fake_build_hover_services(
        canvas,
        *,
        selection_controller,
        hit_testing_service,
        active_tool_provider,
        active_tool_name_provider,
    ):
        build_hover_services_calls.append(
            (
                canvas,
                selection_controller,
                hit_testing_service,
                active_tool_provider,
                active_tool_name_provider,
            )
        )
        return hover_bundle

    interaction_bundle = SimpleNamespace(
        note_controller=object(),
        move_controller=object(),
        selection_rotation_controller=object(),
    )

    def fake_build_canvas_interaction_services(
        canvas,
        *,
        selection_controller,
        hit_testing_service,
        graph_service,
        history_service,
    ):
        build_canvas_interaction_services_calls.append(
            (
                canvas,
                selection_controller,
                hit_testing_service,
                graph_service,
                history_service,
            )
        )
        return interaction_bundle

    scene_decoration_bundle = SimpleNamespace(
        canvas_mark_scene_service=object(),
        scene_decoration_build_service=object(),
        scene_decoration_service=object(),
    )

    def fake_build_scene_decoration_services(canvas, *, history_service):
        build_scene_decoration_services_calls.append((canvas, history_service))
        return scene_decoration_bundle

    scene_operation_bundle = SimpleNamespace(
        scene_clipboard_controller=object(),
        scene_delete_controller=object(),
        scene_transform_controller=object(),
        style_controller=object(),
        canvas_color_mutation_service=object(),
    )

    def fake_build_scene_operation_services(
        canvas,
        *,
        selection_controller,
        move_controller,
        atom_mutation_service,
        bond_mutation_service,
        note_controller,
        graph_service,
        history_service,
    ):
        build_scene_operation_services_calls.append(
            (
                canvas,
                selection_controller,
                move_controller,
                atom_mutation_service,
                bond_mutation_service,
                note_controller,
                graph_service,
                history_service,
            )
        )
        return scene_operation_bundle

    input_bundle = SimpleNamespace(
        input_controller=object(),
        pointer_controller=object(),
        tool_mode_controller=object(),
        chemdraw_shortcut_service=object(),
    )

    def fake_build_canvas_input_services(
        canvas,
        *,
        hit_testing_service,
        insert_controller,
        hover_interaction_service,
        tool_controller,
        scene_delete_controller,
        scene_clipboard_controller,
        scene_transform_controller,
        mark_scene_service,
        hover_refresh,
        history_service,
    ):
        build_canvas_input_services_calls.append(
            (
                canvas,
                hit_testing_service,
                insert_controller,
                hover_interaction_service,
                tool_controller,
                scene_delete_controller,
                scene_clipboard_controller,
                scene_transform_controller,
                mark_scene_service,
                hover_refresh,
                history_service,
            )
        )
        return input_bundle

    document_bundle = SimpleNamespace(
        canvas_document_session_service=object(),
        canvas_history_recording_service=object(),
        canvas_scene_reset_service=object(),
    )

    def fake_build_canvas_document_services(
        canvas,
        *,
        hit_testing_service,
        graph_service,
        structure_build_service,
        history_service,
    ):
        build_canvas_document_services_calls.append(
            (
                canvas,
                hit_testing_service,
                graph_service,
                structure_build_service,
                history_service,
            )
        )
        return document_bundle

    scene_view_bundle = SimpleNamespace(
        scene_item_controller=object(),
        selection_highlight_styler=object(),
        geometry_controller=object(),
        canvas_ring_fill_scene_service=object(),
        rotation_preview_controller=object(),
    )

    def fake_build_canvas_scene_view_services(
        canvas,
        *,
        graph_service,
        hit_testing_service,
        history_service,
        scene_transform_controller,
    ):
        build_canvas_scene_view_services_calls.append(
            (
                canvas,
                graph_service,
                hit_testing_service,
                history_service,
                scene_transform_controller,
            )
        )
        return scene_view_bundle

    structure_bundle = SimpleNamespace(
        canvas_atom_mutation_service=object(),
        canvas_bond_mutation_service=object(),
        structure_build_service=object(),
        insert_controller=object(),
    )

    def fake_build_structure_services(
        canvas,
        *,
        hit_testing_service,
        graph_service,
        move_controller,
        insert_state,
        history_service,
    ):
        build_structure_services_calls.append(
            (
                canvas,
                hit_testing_service,
                graph_service,
                move_controller,
                insert_state,
                history_service,
            )
        )
        return structure_bundle

    monkeypatch.setattr(
        canvas_services, "build_canvas_graph_services", fake_build_canvas_graph_services
    )
    monkeypatch.setattr(
        canvas_services, "build_selection_services", fake_build_selection_services
    )
    monkeypatch.setattr(
        canvas_services,
        "build_canvas_auxiliary_services",
        fake_build_canvas_auxiliary_services,
    )
    monkeypatch.setattr(
        canvas_services, "build_handle_services", fake_build_handle_services
    )
    monkeypatch.setattr(
        canvas_services, "build_hover_services", fake_build_hover_services
    )
    monkeypatch.setattr(
        canvas_services,
        "build_canvas_interaction_services",
        fake_build_canvas_interaction_services,
    )
    monkeypatch.setattr(
        canvas_services,
        "build_canvas_document_services",
        fake_build_canvas_document_services,
    )
    monkeypatch.setattr(
        canvas_services, "build_canvas_input_services", fake_build_canvas_input_services
    )
    monkeypatch.setattr(
        canvas_services,
        "build_canvas_scene_view_services",
        fake_build_canvas_scene_view_services,
    )
    monkeypatch.setattr(
        canvas_services,
        "build_scene_decoration_services",
        fake_build_scene_decoration_services,
    )
    monkeypatch.setattr(
        canvas_services,
        "build_scene_operation_services",
        fake_build_scene_operation_services,
    )
    monkeypatch.setattr(
        canvas_services, "build_structure_services", fake_build_structure_services
    )
    monkeypatch.setattr(
        canvas_services, "build_tool_services", fake_build_tool_services
    )

    canvas = SimpleNamespace()
    graph_state = object()
    insert_state = object()
    history_service = object()
    services = build_canvas_services(
        canvas,
        graph_state=graph_state,
        insert_state=insert_state,
        history_service=history_service,
    )

    assert build_canvas_graph_services_calls == [(canvas, graph_state)]
    assert services.canvas_graph_service is canvas_graph_service
    assert (
        services.scene_clipboard_controller
        is scene_operation_bundle.scene_clipboard_controller
    )
    assert (
        services.scene_delete_controller
        is scene_operation_bundle.scene_delete_controller
    )
    assert (
        services.scene_transform_controller
        is scene_operation_bundle.scene_transform_controller
    )
    assert build_selection_services_calls[0][0] is canvas
    assert build_selection_services_calls[0][1] is services.canvas_graph_service
    assert callable(build_selection_services_calls[0][2])
    assert build_selection_services_calls[0][2]() == "perspective"
    assert build_canvas_auxiliary_services_calls == [
        (
            canvas,
            services.move_controller,
            services.canvas_graph_service,
            history_service,
            hover_bundle.hover_refresh,
            services.structure_build_service,
            services.note_controller,
        )
    ]
    assert build_handle_services_calls == [canvas]
    assert build_hover_services_calls[0][0] is canvas
    assert build_hover_services_calls[0][1] is selection_controller
    assert build_hover_services_calls[0][2] is hit_testing_service
    assert callable(build_hover_services_calls[0][3])
    assert callable(build_hover_services_calls[0][4])
    assert build_hover_services_calls[0][3]() is active_tool
    assert build_hover_services_calls[0][4]() == "perspective"
    assert build_canvas_interaction_services_calls == [
        (
            canvas,
            selection_controller,
            hit_testing_service,
            services.canvas_graph_service,
            history_service,
        )
    ]
    assert build_scene_decoration_services_calls == [(canvas, history_service)]
    assert build_structure_services_calls == [
        (
            canvas,
            hit_testing_service,
            services.canvas_graph_service,
            services.move_controller,
            insert_state,
            history_service,
        )
    ]
    assert build_scene_operation_services_calls == [
        (
            canvas,
            selection_controller,
            services.move_controller,
            services.canvas_atom_mutation_service,
            services.canvas_bond_mutation_service,
            services.note_controller,
            services.canvas_graph_service,
            history_service,
        )
    ]
    assert build_canvas_input_services_calls == [
        (
            canvas,
            hit_testing_service,
            services.insert_controller,
            services.hover_interaction_service,
            tool_controller,
            services.scene_delete_controller,
            services.scene_clipboard_controller,
            services.scene_transform_controller,
            services.canvas_mark_scene_service,
            hover_bundle.hover_refresh,
            history_service,
        )
    ]
    assert build_canvas_document_services_calls == [
        (
            canvas,
            hit_testing_service,
            services.canvas_graph_service,
            services.structure_build_service,
            history_service,
        )
    ]
    assert build_canvas_scene_view_services_calls == [
        (
            canvas,
            services.canvas_graph_service,
            hit_testing_service,
            history_service,
            services.scene_transform_controller,
        )
    ]
    assert build_tool_services_calls == [
        (
            canvas,
            hit_testing_service,
            selection_controller,
            services.note_controller,
            services.handle_controller,
            services.selection_rotation_controller,
            services.scene_delete_controller,
            services.scene_transform_controller,
            services.style_controller,
            services.canvas_color_mutation_service,
            services.canvas_graph_service,
            history_service,
        )
    ]
    assert services.hit_testing_service is hit_testing_service
    assert services.selection_controller is selection_controller
    assert services.handle_controller is handle_bundle.handle_controller
    assert services.handle_overlay_service is handle_bundle.handle_overlay_service
    assert services.handle_mutation_service is handle_bundle.handle_mutation_service
    assert services.curved_arrow_path_service is handle_bundle.curved_arrow_path_service
    assert services.hover_interaction_service is hover_bundle.hover_interaction_service
    assert services.hover_scene_service is hover_bundle.hover_scene_service
    assert (
        services.mark_hover_preview_service is hover_bundle.mark_hover_preview_service
    )
    assert (
        services.bond_hover_preview_service is hover_bundle.bond_hover_preview_service
    )
    assert (
        services.canvas_mark_scene_service
        is scene_decoration_bundle.canvas_mark_scene_service
    )
    assert (
        services.scene_decoration_build_service
        is scene_decoration_bundle.scene_decoration_build_service
    )
    assert (
        services.scene_decoration_service
        is scene_decoration_bundle.scene_decoration_service
    )
    assert (
        services.canvas_atom_mutation_service
        is structure_bundle.canvas_atom_mutation_service
    )
    assert (
        services.canvas_bond_mutation_service
        is structure_bundle.canvas_bond_mutation_service
    )
    assert services.structure_build_service is structure_bundle.structure_build_service
    assert services.insert_controller is structure_bundle.insert_controller
    assert services.input_controller is input_bundle.input_controller
    assert services.pointer_controller is input_bundle.pointer_controller
    assert services.tool_mode_controller is input_bundle.tool_mode_controller
    assert services.chemdraw_shortcut_service is input_bundle.chemdraw_shortcut_service
    assert (
        services.scene_clipboard_controller
        is scene_operation_bundle.scene_clipboard_controller
    )
    assert (
        services.scene_delete_controller
        is scene_operation_bundle.scene_delete_controller
    )
    assert (
        services.scene_transform_controller
        is scene_operation_bundle.scene_transform_controller
    )
    assert services.style_controller is scene_operation_bundle.style_controller
    assert (
        services.canvas_color_mutation_service
        is scene_operation_bundle.canvas_color_mutation_service
    )
    assert (
        services.canvas_document_session_service
        is document_bundle.canvas_document_session_service
    )
    assert (
        services.canvas_history_recording_service
        is document_bundle.canvas_history_recording_service
    )
    assert (
        services.canvas_scene_reset_service
        is document_bundle.canvas_scene_reset_service
    )
    assert services.scene_item_controller is scene_view_bundle.scene_item_controller
    assert (
        services.selection_highlight_styler
        is scene_view_bundle.selection_highlight_styler
    )
    assert services.geometry_controller is scene_view_bundle.geometry_controller
    assert (
        services.canvas_ring_fill_scene_service
        is scene_view_bundle.canvas_ring_fill_scene_service
    )
    assert (
        services.rotation_preview_controller
        is scene_view_bundle.rotation_preview_controller
    )
    assert services.note_controller is interaction_bundle.note_controller
    assert services.move_controller is interaction_bundle.move_controller
    assert (
        services.selection_rotation_controller
        is interaction_bundle.selection_rotation_controller
    )
    assert services.atom_label_service is auxiliary_bundle.atom_label_service
    assert services.benzene_preview_service is auxiliary_bundle.benzene_preview_service
    assert (
        services.structure_insert_service is auxiliary_bundle.structure_insert_service
    )
    assert services.tools is tool_controller
    assert services.history_service is history_service

    assert services.auxiliary is auxiliary_bundle
    assert services.document is document_bundle
    assert services.graph is graph_bundle
    assert services.input is input_bundle
    assert services.interaction is interaction_bundle
    assert services.scene_view is scene_view_bundle
    assert services.handles is handle_bundle
    assert services.hover is hover_bundle
    assert services.scene_decoration is scene_decoration_bundle
    assert services.scene_operations is scene_operation_bundle
    assert services.selection is selection_bundle
    assert services.structure is structure_bundle
    assert services.tooling is tool_bundle

    selection_bundle_identity = services.selection
    replacement_selection_controller = object()
    services.selection_controller = replacement_selection_controller
    assert services.selection is selection_bundle_identity
    assert services.selection.selection_controller is replacement_selection_controller
    assert services.selection_controller is replacement_selection_controller

    tool_bundle_identity = services.tooling
    replacement_tools = object()
    services.tools = replacement_tools
    assert services.tooling is tool_bundle_identity
    assert services.tooling.tools is replacement_tools
    assert services.tools is replacement_tools

    try:
        services.unknown_service = object()
    except AttributeError:
        pass
    else:
        raise AssertionError("unknown service names must not create shadow attributes")
