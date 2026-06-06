from __future__ import annotations

from ui.canvas_callback_state import callback_state_for
from ui.canvas_window_ports import canvas_window_document_session_service
from ui.selection_info_state import selection_info_state_for


def snapshot_canvas_state_for(canvas) -> dict:
    return canvas_window_document_session_service(canvas).snapshot_state()


def restore_canvas_state_for(canvas, state: dict) -> None:
    canvas_window_document_session_service(canvas).restore_state(state)


def save_canvas_to_file_for(canvas, path: str) -> None:
    canvas_window_document_session_service(canvas).save_to_file(path)


def set_selection_info_callback_for(canvas, callback) -> None:
    selection_info_state_for(canvas).callback = callback


def set_error_callback_for(canvas, callback) -> None:
    callback_state_for(canvas).error = callback


def notify_error_for(canvas, message: str) -> bool:
    callback = callback_state_for(canvas).error
    if callback is None:
        return False
    callback(message)
    return True


def set_tool_change_callback_for(canvas, callback) -> None:
    callback_state_for(canvas).tool_change = callback


def set_zoom_callback_for(canvas, callback) -> None:
    callback_state_for(canvas).zoom = callback


def history_service_for_canvas(canvas):
    runtime_state = getattr(canvas, "runtime_state", None)
    service = getattr(runtime_state, "history_service", None)
    if service is not None:
        return service
    msg = "Canvas runtime history service is not available"
    raise AttributeError(msg)


def set_history_change_callback_for(canvas, callback) -> None:
    history_service_for_canvas(canvas).set_change_callback(callback)


def can_undo_for(canvas) -> bool:
    return history_service_for_canvas(canvas).can_undo()


def can_redo_for(canvas) -> bool:
    return history_service_for_canvas(canvas).can_redo()


__all__ = [
    "can_redo_for",
    "can_undo_for",
    "history_service_for_canvas",
    "notify_error_for",
    "restore_canvas_state_for",
    "save_canvas_to_file_for",
    "set_error_callback_for",
    "set_history_change_callback_for",
    "set_selection_info_callback_for",
    "set_tool_change_callback_for",
    "set_zoom_callback_for",
    "snapshot_canvas_state_for",
]
