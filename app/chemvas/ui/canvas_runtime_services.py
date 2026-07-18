"""Typed, feature-grouped runtime services for a canvas.

The feature bundles are the canonical API. Flat service attributes remain as a
temporary compatibility surface for legacy tests and are redirected into the
same bundle objects, so there is still exactly one service instance per role.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class AuxiliaryServices(Protocol):
    atom_label_service: Any
    benzene_preview_service: Any
    structure_insert_service: Any


class DocumentServices(Protocol):
    canvas_document_session_service: Any
    canvas_history_recording_service: Any
    canvas_scene_reset_service: Any


class GraphServices(Protocol):
    canvas_graph_service: Any


class InputServices(Protocol):
    input_controller: Any
    pointer_controller: Any
    tool_mode_controller: Any
    chemdraw_shortcut_service: Any


class InteractionServices(Protocol):
    move_controller: Any
    note_controller: Any
    selection_rotation_controller: Any


class SceneViewServices(Protocol):
    scene_item_controller: Any
    selection_highlight_styler: Any
    geometry_controller: Any
    canvas_ring_fill_scene_service: Any
    rotation_preview_controller: Any


class HandleServices(Protocol):
    handle_controller: Any
    handle_overlay_service: Any
    handle_mutation_service: Any
    curved_arrow_path_service: Any


class HoverServices(Protocol):
    hover_interaction_service: Any
    hover_scene_service: Any
    mark_hover_preview_service: Any
    bond_hover_preview_service: Any

    @property
    def hover_refresh(self) -> Callable[..., None]: ...


class SceneDecorationServices(Protocol):
    canvas_mark_scene_service: Any
    scene_decoration_build_service: Any
    scene_decoration_service: Any


class SceneOperationServices(Protocol):
    scene_clipboard_controller: Any
    scene_delete_controller: Any
    scene_transform_controller: Any
    style_controller: Any
    canvas_color_mutation_service: Any


class SelectionServices(Protocol):
    hit_testing_service: Any
    selection_controller: Any


class StructureServices(Protocol):
    canvas_atom_mutation_service: Any
    canvas_bond_mutation_service: Any
    structure_build_service: Any
    insert_controller: Any


class ToolingServices(Protocol):
    tools: Any


_LEGACY_SERVICE_PATHS: dict[str, tuple[str, str]] = {
    "selection_controller": ("selection", "selection_controller"),
    "scene_item_controller": ("scene_view", "scene_item_controller"),
    "scene_clipboard_controller": (
        "scene_operations",
        "scene_clipboard_controller",
    ),
    "scene_delete_controller": ("scene_operations", "scene_delete_controller"),
    "scene_transform_controller": (
        "scene_operations",
        "scene_transform_controller",
    ),
    "insert_controller": ("structure", "insert_controller"),
    "input_controller": ("input", "input_controller"),
    "handle_controller": ("handles", "handle_controller"),
    "handle_overlay_service": ("handles", "handle_overlay_service"),
    "handle_mutation_service": ("handles", "handle_mutation_service"),
    "curved_arrow_path_service": ("handles", "curved_arrow_path_service"),
    "selection_highlight_styler": (
        "scene_view",
        "selection_highlight_styler",
    ),
    "move_controller": ("interaction", "move_controller"),
    "note_controller": ("interaction", "note_controller"),
    "pointer_controller": ("input", "pointer_controller"),
    "geometry_controller": ("scene_view", "geometry_controller"),
    "canvas_atom_mutation_service": (
        "structure",
        "canvas_atom_mutation_service",
    ),
    "canvas_bond_mutation_service": (
        "structure",
        "canvas_bond_mutation_service",
    ),
    "chemdraw_shortcut_service": ("input", "chemdraw_shortcut_service"),
    "hit_testing_service": ("selection", "hit_testing_service"),
    "canvas_color_mutation_service": (
        "scene_operations",
        "canvas_color_mutation_service",
    ),
    "canvas_document_session_service": (
        "document",
        "canvas_document_session_service",
    ),
    "canvas_graph_service": ("graph", "canvas_graph_service"),
    "canvas_history_recording_service": (
        "document",
        "canvas_history_recording_service",
    ),
    "canvas_mark_scene_service": (
        "scene_decoration",
        "canvas_mark_scene_service",
    ),
    "canvas_ring_fill_scene_service": (
        "scene_view",
        "canvas_ring_fill_scene_service",
    ),
    "canvas_scene_reset_service": ("document", "canvas_scene_reset_service"),
    "rotation_preview_controller": ("scene_view", "rotation_preview_controller"),
    "atom_label_service": ("auxiliary", "atom_label_service"),
    "hover_interaction_service": ("hover", "hover_interaction_service"),
    "hover_scene_service": ("hover", "hover_scene_service"),
    "mark_hover_preview_service": ("hover", "mark_hover_preview_service"),
    "bond_hover_preview_service": ("hover", "bond_hover_preview_service"),
    "structure_build_service": ("structure", "structure_build_service"),
    "benzene_preview_service": ("auxiliary", "benzene_preview_service"),
    "scene_decoration_build_service": (
        "scene_decoration",
        "scene_decoration_build_service",
    ),
    "scene_decoration_service": (
        "scene_decoration",
        "scene_decoration_service",
    ),
    "structure_insert_service": ("auxiliary", "structure_insert_service"),
    "selection_rotation_controller": (
        "interaction",
        "selection_rotation_controller",
    ),
    "style_controller": ("scene_operations", "style_controller"),
    "tool_mode_controller": ("input", "tool_mode_controller"),
    "tools": ("tooling", "tools"),
}


@dataclass(slots=True)
class CanvasRuntimeServices:
    auxiliary: AuxiliaryServices
    document: DocumentServices
    graph: GraphServices
    input: InputServices
    interaction: InteractionServices
    scene_view: SceneViewServices
    handles: HandleServices
    hover: HoverServices
    scene_decoration: SceneDecorationServices
    scene_operations: SceneOperationServices
    selection: SelectionServices
    structure: StructureServices
    tooling: ToolingServices
    history_service: Any

    def __getattr__(self, name: str) -> Any:
        path = _LEGACY_SERVICE_PATHS.get(name)
        if path is None:
            raise AttributeError(name)
        bundle_name, member_name = path
        bundle = object.__getattribute__(self, bundle_name)
        return getattr(bundle, member_name)

    def __setattr__(self, name: str, value: Any) -> None:
        path = _LEGACY_SERVICE_PATHS.get(name)
        if path is None:
            object.__setattr__(self, name, value)
            return
        bundle_name, member_name = path
        bundle = object.__getattribute__(self, bundle_name)
        setattr(bundle, member_name, value)


# Transitional import name; new production code uses CanvasRuntimeServices.
CanvasServices = CanvasRuntimeServices


__all__ = ["CanvasRuntimeServices", "CanvasServices"]
