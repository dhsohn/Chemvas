from __future__ import annotations


class MainWindowActionAvailabilityService:
    def __init__(
        self,
        *,
        history_service_for_window,
        has_exportable_atoms_for_window,
        active_canvas_or_none_for_window,
        undo_button_for_window,
        redo_button_for_window,
        export_xyz_button_for_window,
    ) -> None:
        self._history_service_for_window = history_service_for_window
        self._has_exportable_atoms_for_window = has_exportable_atoms_for_window
        self._active_canvas_or_none_for_window = active_canvas_or_none_for_window
        self._undo_button_for_window = undo_button_for_window
        self._redo_button_for_window = redo_button_for_window
        self._export_xyz_button_for_window = export_xyz_button_for_window

    def update_action_availability(self, window) -> None:
        canvas = self._active_canvas_or_none_for_window(window)
        history_service = self._history_service_for_window(window) if canvas is not None else None
        can_undo = history_service.can_undo() if history_service is not None else False
        can_redo = history_service.can_redo() if history_service is not None else False
        can_export = self._has_exportable_atoms_for_window(window)

        for button, enabled in (
            (self._undo_button_for_window(window), can_undo),
            (self._redo_button_for_window(window), can_redo),
            (self._export_xyz_button_for_window(window), can_export),
        ):
            if button is not None:
                button.setEnabled(enabled)


__all__ = ["MainWindowActionAvailabilityService"]
