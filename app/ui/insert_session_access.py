from __future__ import annotations

from ui.canvas_service_ports import insert_controller_for_access


def _insert_controller_method(canvas, name: str):
    try:
        controller = insert_controller_for_access(canvas)
    except AttributeError:
        controller = None
    method = getattr(controller, name, None)
    return method if callable(method) else None


def cancel_smiles_insert_for(canvas) -> None:
    method = _insert_controller_method(canvas, "cancel_smiles_insert")
    if method is not None:
        method()


def clear_smiles_preview_for(canvas) -> None:
    method = _insert_controller_method(canvas, "clear_smiles_preview")
    if method is not None:
        method()


def cancel_template_insert_for(canvas) -> None:
    method = _insert_controller_method(canvas, "cancel_template_insert")
    if method is not None:
        method()


def clear_template_preview_for(canvas) -> None:
    method = _insert_controller_method(canvas, "clear_template_preview")
    if method is not None:
        method()


def apply_insert_session_state_for(canvas, state) -> None:
    method = _insert_controller_method(canvas, "apply_insert_session_state")
    if method is not None:
        method(state)


__all__ = [
    "apply_insert_session_state_for",
    "cancel_smiles_insert_for",
    "cancel_template_insert_for",
    "clear_smiles_preview_for",
    "clear_template_preview_for",
]
