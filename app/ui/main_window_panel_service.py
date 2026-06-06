from __future__ import annotations

from ui.main_window_preview_panel import build_preview_panel_dock


class MainWindowPanelService:
    def __init__(
        self,
        *,
        preview_for_window,
        apply_panel_assembly_for_window,
        panel_dock_for_window,
        preview_panel_button_for_window,
    ) -> None:
        self._preview_for_window = preview_for_window
        self._apply_panel_assembly_for_window = apply_panel_assembly_for_window
        self._panel_dock_for_window = panel_dock_for_window
        self._preview_panel_button_for_window = preview_panel_button_for_window

    def init_panels(self, window) -> None:
        assembly = build_preview_panel_dock(
            window,
            preview_widget=self._preview_for_window(window),
        )
        self._apply_panel_assembly_for_window(window, assembly)
        assembly.dock.visibilityChanged.connect(
            lambda visible: self.sync_preview_panel_button(window, visible)
        )
        self.sync_preview_panel_button(window)

    def toggle_preview_panel(self, window, checked: bool | None = None) -> None:
        dock = self._panel_dock_for_window(window)
        if dock is None:
            return
        should_show = dock.isHidden() if checked is None else bool(checked)
        dock.setVisible(should_show)
        if should_show:
            dock.raise_()
        self.sync_preview_panel_button(window)

    def sync_preview_panel_button(self, window, _visible: bool | None = None) -> None:
        button = self._preview_panel_button_for_window(window)
        dock = self._panel_dock_for_window(window)
        if button is None or dock is None:
            return
        hidden = dock.isHidden()
        if not isinstance(hidden, bool):
            return
        previous = button.blockSignals(True)
        button.setChecked(not hidden)
        button.blockSignals(previous)


__all__ = ["MainWindowPanelService"]
