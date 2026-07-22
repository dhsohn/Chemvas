from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices

SERVICE_PATHS: dict[str, tuple[str, str]] = {
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
    "structure_build_service": ("structure", "structure_build_service"),
    "scene_decoration_build_service": (
        "scene_decoration",
        "scene_decoration_build_service",
    ),
    "scene_decoration_service": (
        "scene_decoration",
        "scene_decoration_service",
    ),
    "selection_rotation_controller": (
        "interaction",
        "selection_rotation_controller",
    ),
    "style_controller": ("scene_operations", "style_controller"),
    "tool_mode_controller": ("input", "tool_mode_controller"),
    "tools": ("tooling", "tools"),
}

_GROUP_NAMES = (
    "document",
    "graph",
    "input",
    "interaction",
    "scene_view",
    "handles",
    "scene_decoration",
    "scene_operations",
    "selection",
    "structure",
    "tooling",
)


class CanvasRuntimeServicesDouble(CanvasRuntimeServices):
    """Partial canonical service graph for focused legacy UI tests."""

    def __init__(self, **services: Any) -> None:
        groups = {
            group_name: services.pop(group_name, SimpleNamespace())
            for group_name in _GROUP_NAMES
        }
        atom_label_service = services.pop("atom_label_service", None)
        hover = services.pop("hover", SimpleNamespace())
        history_service = services.pop("history_service", None)
        super().__init__(
            **groups,
            hover=hover,
            atom_label_service=atom_label_service,
            history_service=history_service,
        )
        for name, value in services.items():
            setattr(self, name, value)

    def __getattr__(self, name: str) -> Any:
        path = SERVICE_PATHS.get(name)
        if path is None:
            raise AttributeError(name)
        group_name, member_name = path
        return getattr(getattr(self, group_name), member_name)

    def __setattr__(self, name: str, value: Any) -> None:
        path = SERVICE_PATHS.get(name)
        if path is None:
            super().__setattr__(name, value)
            return
        group_name, member_name = path
        setattr(getattr(self, group_name), member_name, value)


def canvas_runtime_services(**services: Any) -> CanvasRuntimeServicesDouble:
    return CanvasRuntimeServicesDouble(**services)


__all__ = [
    "SERVICE_PATHS",
    "CanvasRuntimeServicesDouble",
    "canvas_runtime_services",
]
