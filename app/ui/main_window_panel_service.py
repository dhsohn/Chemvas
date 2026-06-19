from __future__ import annotations

from ui.main_window_preview_window import build_preview_window
from ui.rdkit_adapter_access import rdkit_adapter_for


class MainWindowPanelService:
    def __init__(
        self,
        *,
        preview_for_window,
        active_canvas_for_window,
        export_xyz_for_window,
        apply_preview_window_assembly_for_window,
        preview_window_for_window,
        preview_panel_button_for_window,
    ) -> None:
        self._preview_for_window = preview_for_window
        self._active_canvas_for_window = active_canvas_for_window
        self._export_xyz_for_window = export_xyz_for_window
        self._apply_preview_window_assembly_for_window = apply_preview_window_assembly_for_window
        self._preview_window_for_window = preview_window_for_window
        self._preview_panel_button_for_window = preview_panel_button_for_window

    def init_panels(self, window) -> None:
        preview = self._preview_for_window(window)
        set_export_action = getattr(preview, "set_export_xyz_action", None)
        if callable(set_export_action):
            set_export_action(
                lambda: self._export_xyz_for_window(window, selected_only=True),
            )
        assembly = build_preview_window(
            window,
            preview_widget=preview,
        )
        self._apply_preview_window_assembly_for_window(window, assembly)
        self.sync_preview_panel_button(window)

    def open_preview_window(self, window, _checked: bool | None = None) -> None:
        preview_window = self._preview_window_for_window(window)
        if preview_window is None:
            return
        preview = self._preview_for_window(window)
        try:
            canvas = self._active_canvas_for_window(window)
        except RuntimeError:
            preview.clear_preview("No chemical structure selected.")
        else:
            preview.set_rdkit_adapter(rdkit_adapter_for(canvas))
            preview.refresh_selected_from_canvas(canvas)
        preview_window.show()
        preview_window.raise_()
        preview_window.activateWindow()
        self.sync_preview_panel_button(window)

    def sync_preview_panel_button(self, window, _visible: bool | None = None) -> None:
        button = self._preview_panel_button_for_window(window)
        if button is None:
            return
        previous = button.blockSignals(True)
        button.setChecked(False)
        button.blockSignals(previous)


__all__ = ["MainWindowPanelService"]
