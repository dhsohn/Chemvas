"""Typed, feature-grouped runtime services for a canvas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from chemvas.ui.hover import HoverController


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


class HandleServices(Protocol):
    handle_controller: Any
    handle_overlay_service: Any
    handle_mutation_service: Any
    curved_arrow_path_service: Any


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


@dataclass(slots=True)
class CanvasRuntimeServices:
    document: DocumentServices
    graph: GraphServices
    input: InputServices
    interaction: InteractionServices
    scene_view: SceneViewServices
    handles: HandleServices
    hover: HoverController
    scene_decoration: SceneDecorationServices
    scene_operations: SceneOperationServices
    selection: SelectionServices
    structure: StructureServices
    tooling: ToolingServices
    atom_label_service: Any
    history_service: Any


__all__ = ["CanvasRuntimeServices"]
