from __future__ import annotations


def notify_error_for(canvas, message: str) -> bool:
    callback = canvas.runtime_state.callback_state.error
    if callback is None:
        return False
    callback(message)
    return True


def set_history_change_callback_for(canvas, callback) -> None:
    canvas.services.history_service.set_change_callback(callback)


def set_document_change_callback_for(canvas, callback) -> None:
    canvas.runtime_state.document_metadata_state.invalidate_note_chrome()
    canvas.runtime_state.callback_state.document_change = callback


def notify_document_change_for(canvas, *, edited_note=None) -> None:
    if edited_note is None:
        canvas.runtime_state.document_metadata_state.invalidate_note_chrome()
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
    "notify_document_change_for",
    "notify_error_for",
    "set_document_change_callback_for",
    "set_history_change_callback_for",
]
