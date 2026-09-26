from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QToolButton

from chemvas.shell.theme import TOOLBAR_BUTTON_SIZE, TOOLBAR_ICON_SIZE
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from chemvas.ui.window.main_window_preview_window import build_preview_window

if TYPE_CHECKING:
    from chemvas.ui.window.main_window_like import MainWindowLike


class MainWindowPanelService:
    def __init__(
        self,
        *,
        document_action_service,
    ) -> None:
        self._document_actions = document_action_service

    def init_panels(self, window: MainWindowLike, *, panel_bar) -> None:
        preview = window.preview_3d
        preview.pause_updates()
        set_export_action = getattr(preview, "set_export_xyz_action", None)
        if callable(set_export_action):
            set_export_action(lambda: self._export_selected_xyz(window))
        assembly = build_preview_window(
            window,
            preview_widget=preview,
            panel_bar=panel_bar,
        )
        window.ui_references.apply_preview_window_assembly(assembly)
        assembly.preview_window.visibilityChanged.connect(
            lambda visible: self._refresh_preview(window) if visible else None
        )
        action = window.ui_references.reaction_mapping_action
        if action is not None:
            action.setIcon(
                window.ui_references.require_icon_factory().make_design_icon(
                    "reaction_mapping"
                )
            )
            action.setToolTip("Reaction Mapping: map atoms and review bond changes")
            button = QToolButton(panel_bar)
            button.setObjectName("reactionMappingToggleButton")
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(TOOLBAR_ICON_SIZE, TOOLBAR_ICON_SIZE))
            button.setFixedSize(TOOLBAR_BUTTON_SIZE, TOOLBAR_BUTTON_SIZE)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setProperty("iconOnly", True)
            panel_bar.addWidget(button)

    def _export_selected_xyz(self, window: MainWindowLike) -> None:
        # The same parent and status sink serve docked and floating inspectors.
        preview_window = window.ui_references.preview_window
        status_sink = None
        if preview_window is not None:
            show_status = getattr(preview_window, "show_export_status", None)
            if callable(show_status):
                status_sink = show_status
        self._document_actions.export_xyz(
            window,
            selected_only=True,
            dialog_parent=preview_window,
            status_sink=status_sink,
        )

    def open_preview_window(
        self, window: MainWindowLike, _checked: bool | None = None
    ) -> None:
        preview_window = window.ui_references.preview_window
        if preview_window is None:
            return
        was_visible = preview_window.isVisible()
        preview_window.show()
        preview_window.raise_()
        if was_visible:
            self._refresh_preview(window)

    def _refresh_preview(self, window: MainWindowLike) -> None:
        preview = window.preview_3d
        try:
            canvas = active_canvas_for_window(window)
        except RuntimeError:
            preview.resume_updates()
            preview.clear_preview("No chemical structure selected.")
        else:
            preview.set_rdkit_adapter(canvas.rdkit)
            preview.resume_updates()
            preview.refresh_selected_from_canvas(canvas)


__all__ = ["MainWindowPanelService"]
