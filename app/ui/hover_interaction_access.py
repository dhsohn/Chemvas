from __future__ import annotations

from ui.canvas_service_ports import (
    bond_hover_preview_service_for_access,
    hover_interaction_service_for_access,
    hover_scene_service_for_access,
    mark_hover_preview_service_for_access,
)
from ui.canvas_tool_settings_state import tool_settings_state_for


def _service_method(canvas, service_getter, method_name: str):
    try:
        service = service_getter(canvas)
    except AttributeError:
        service = None
    method = getattr(service, method_name, None)
    return method if callable(method) else None


def _hover_scene_method(canvas, name: str):
    return _service_method(canvas, hover_scene_service_for_access, name)


def _mark_hover_preview_method(canvas, name: str):
    return _service_method(canvas, mark_hover_preview_service_for_access, name)


def _bond_hover_preview_method(canvas, name: str):
    return _service_method(canvas, bond_hover_preview_service_for_access, name)


def _hover_interaction_method(canvas, name: str):
    return _service_method(canvas, hover_interaction_service_for_access, name)


def add_mark_hover_preview_for(canvas, pos) -> None:
    method = _mark_hover_preview_method(canvas, "add_mark_hover_preview")
    if method is not None:
        method(pos)


def bond_preview_signature_for(canvas, *, active_tool_name: str | None = None) -> str | None:
    if active_tool_name != "bond":
        return None
    settings = tool_settings_state_for(canvas)
    return f"{settings.active_bond_style}:{settings.active_bond_order}"


def add_free_bond_hover_preview_for(canvas, pos) -> None:
    method = _bond_hover_preview_method(canvas, "add_free_bond_hover_preview")
    if method is not None:
        method(pos)


def update_hover_highlight_for(canvas, pos) -> None:
    update_hover_highlight = _hover_interaction_method(canvas, "update_hover_highlight")
    if callable(update_hover_highlight):
        update_hover_highlight(pos)


def add_atom_hover_indicator_for(canvas, atom_id: int) -> None:
    method = _hover_scene_method(canvas, "add_atom_hover_indicator")
    if method is not None:
        method(atom_id)


def add_bond_tool_hover_preview_for(canvas, atom_id: int, pos) -> None:
    method = _bond_hover_preview_method(canvas, "add_bond_tool_hover_preview")
    if method is not None:
        method(atom_id, pos)


def add_bond_hover_indicator_for(canvas, bond_id: int) -> None:
    method = _hover_scene_method(canvas, "add_bond_hover_indicator")
    if method is not None:
        method(bond_id)


def add_bond_style_hover_preview_for(canvas, bond) -> None:
    method = _bond_hover_preview_method(canvas, "add_bond_style_hover_preview")
    if method is not None:
        method(bond)


__all__ = [
    "add_atom_hover_indicator_for",
    "add_bond_hover_indicator_for",
    "add_bond_style_hover_preview_for",
    "add_bond_tool_hover_preview_for",
    "add_free_bond_hover_preview_for",
    "add_mark_hover_preview_for",
    "bond_preview_signature_for",
    "update_hover_highlight_for",
]
