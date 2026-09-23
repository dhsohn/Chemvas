from __future__ import annotations

from chemvas.ui.main_window_preview_window import build_preview_window
from chemvas.ui.rdkit_adapter_access import rdkit_adapter_for


class MainWindowPanelService:
    def __init__(
        self,
        *,
        preview_for_window,
        active_canvas_for_window,
        export_xyz_for_window,
        apply_preview_window_assembly_for_window,
        preview_window_for_window,
    ) -> None:
        self._preview_for_window = preview_for_window
        self._active_canvas_for_window = active_canvas_for_window
        self._export_xyz_for_window = export_xyz_for_window
        self._apply_preview_window_assembly_for_window = (
            apply_preview_window_assembly_for_window
        )
        self._preview_window_for_window = preview_window_for_window

    def init_panels(self, window, *, panel_bar) -> None:
        preview = self._preview_for_window(window)
        preview.pause_updates()
        set_export_action = getattr(preview, "set_export_xyz_action", None)
        if callable(set_export_action):
            set_export_action(lambda: self._export_selected_xyz(window))
        assembly = build_preview_window(
            window,
            preview_widget=preview,
            panel_bar=panel_bar,
        )
        self._apply_preview_window_assembly_for_window(window, assembly)
        assembly.preview_window.visibilityChanged.connect(
            lambda visible: self._refresh_preview(window) if visible else None
        )

    def _export_selected_xyz(self, window) -> None:
        # The same parent and status sink serve docked and floating inspectors.
        preview_window = self._preview_window_for_window(window)
        status_sink = None
        if preview_window is not None:
            show_status = getattr(preview_window, "show_export_status", None)
            if callable(show_status):
                status_sink = show_status
        self._export_xyz_for_window(
            window,
            selected_only=True,
            dialog_parent=preview_window,
            status_sink=status_sink,
        )

    def open_preview_window(self, window, _checked: bool | None = None) -> None:
        preview_window = self._preview_window_for_window(window)
        if preview_window is None:
            return
        was_visible = preview_window.isVisible()
        preview_window.show()
        preview_window.raise_()
        if was_visible:
            self._refresh_preview(window)

    def _refresh_preview(self, window) -> None:
        preview = self._preview_for_window(window)
        try:
            canvas = self._active_canvas_for_window(window)
        except RuntimeError:
            preview.resume_updates()
            preview.clear_preview("No chemical structure selected.")
        else:
            preview.set_rdkit_adapter(rdkit_adapter_for(canvas))
            preview.resume_updates()
            preview.refresh_selected_from_canvas(canvas)


__all__ = ["MainWindowPanelService"]
