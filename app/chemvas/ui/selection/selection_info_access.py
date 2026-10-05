from __future__ import annotations


def emit_selection_info_for(canvas) -> None:
    """Tell the active window that this canvas's selection may have changed."""
    callback = canvas.runtime_state.selection_info_state.callback
    if callback:
        callback()


__all__ = ["emit_selection_info_for"]
