from __future__ import annotations

from chemvas.ui.tools.endpoint_snap_access import grid_snap_enabled_for
from chemvas.ui.window.main_window_ports import (
    active_canvas_or_none_for_window,
    grid_snap_action_for_window,
    history_service_for_window,
    redo_action_for_window,
    text_history_availability_for_window,
    undo_action_for_window,
)


class MainWindowActionAvailabilityService:
    def update_action_availability(self, window) -> None:
        text_history = text_history_availability_for_window(window)
        if text_history is not None:
            can_undo, can_redo = text_history
        else:
            canvas = active_canvas_or_none_for_window(window)
            history_service = (
                history_service_for_window(window) if canvas is not None else None
            )
            can_undo = (
                history_service.can_undo() if history_service is not None else False
            )
            can_redo = (
                history_service.can_redo() if history_service is not None else False
            )

        for action, enabled in (
            (undo_action_for_window(window), can_undo),
            (redo_action_for_window(window), can_redo),
        ):
            if action is not None:
                action.setEnabled(enabled)

    def sync_grid_snap_action(self, window) -> None:
        """Show the grid state of the canvas the user is actually looking at."""
        action = grid_snap_action_for_window(window)
        if action is None:
            return
        canvas = active_canvas_or_none_for_window(window)
        enabled = grid_snap_enabled_for(canvas) if canvas is not None else False
        blocked = action.blockSignals(True)
        action.setChecked(enabled)
        action.blockSignals(blocked)


__all__ = ["MainWindowActionAvailabilityService"]
