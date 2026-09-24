from __future__ import annotations


def notify_error_for(canvas, message: str) -> bool:
    callback = canvas.runtime_state.callback_state.error
    if callback is None:
        return False
    callback(message)
    return True


def history_service_for_canvas(canvas):
    runtime_state = getattr(canvas, "runtime_state", None)
    service = getattr(runtime_state, "history_service", None)
    if service is not None:
        return service
    msg = "Canvas runtime history service is not available"
    raise AttributeError(msg)


def set_history_change_callback_for(canvas, callback) -> None:
    history_service_for_canvas(canvas).set_change_callback(callback)


def set_document_change_callback_for(canvas, callback) -> None:
    canvas.runtime_state.document_metadata_state.note_chrome_session = None
    canvas.runtime_state.callback_state.document_change = callback


def notify_document_change_for(canvas, *, edited_note=None) -> None:
    if edited_note is None:
        canvas.runtime_state.document_metadata_state.note_chrome_session = None
    callback = canvas.runtime_state.callback_state.document_change
    if callback is not None:
        try:
            if edited_note is None:
                callback()
            else:
                callback(edited_note=edited_note)
        except Exception:
            # Chrome is an observer, not an authority over editor/history state.
            return


__all__ = [
    "history_service_for_canvas",
    "notify_document_change_for",
    "notify_error_for",
    "set_document_change_callback_for",
    "set_history_change_callback_for",
]
