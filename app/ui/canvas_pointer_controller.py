from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt


class CanvasPointerController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def _dispatch_press_event(
        self,
        event,
        *,
        base_event,
        allow_select_tool: bool,
    ) -> None:
        self.canvas._touch_interaction()
        if self.canvas._template_insert_active and event.button() == Qt.MouseButton.LeftButton:
            self.canvas._commit_template_insert(self.canvas.scene_pos_from_event(event))
            self.canvas._clear_hover_highlight()
            return
        if self.canvas._smiles_insert_active and event.button() == Qt.MouseButton.LeftButton:
            self.canvas._commit_smiles_insert(self.canvas.scene_pos_from_event(event))
            self.canvas._clear_hover_highlight()
            return
        active_tool = self.canvas.tools.active
        if active_tool and (allow_select_tool or active_tool.name != "select") and active_tool.on_mouse_press(event):
            self.canvas._clear_hover_highlight()
            return
        base_event(event)
        self.canvas._clear_hover_highlight()

    def mouse_press_event(self, event, *, base_mouse_press_event) -> None:
        self._dispatch_press_event(
            event,
            base_event=base_mouse_press_event,
            allow_select_tool=True,
        )

    def mouse_double_click_event(self, event, *, base_mouse_double_click_event) -> None:
        self._dispatch_press_event(
            event,
            base_event=base_mouse_double_click_event,
            allow_select_tool=False,
        )

    def mouse_move_event(self, event, *, base_mouse_move_event) -> None:
        self.canvas._touch_interaction()
        if self.canvas._template_insert_active:
            self.canvas._render_template_preview(self.canvas.scene_pos_from_event(event))
            return
        if self.canvas._smiles_insert_active:
            self.canvas._render_smiles_preview(self.canvas.scene_pos_from_event(event))
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self.canvas._update_hover_highlight(self.canvas.scene_pos_from_event(event))
        else:
            self.canvas._clear_hover_highlight()
        if self.canvas.tools.active and self.canvas.tools.active.on_mouse_move(event):
            return
        base_mouse_move_event(event)

    def mouse_release_event(self, event, *, base_mouse_release_event) -> None:
        self.canvas._touch_interaction()
        if self.canvas.tools.active and self.canvas.tools.active.on_mouse_release(event):
            self.canvas._refresh_hover_from_cursor()
            return
        base_mouse_release_event(event)
        self.canvas._refresh_hover_from_cursor()

    def viewport_event(self, event, *, single_shot, base_viewport_event) -> bool:
        if event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
            self.canvas._clear_hover_highlight()
        elif event.type() == QEvent.Type.Enter:
            single_shot(0, self.canvas._refresh_hover_from_cursor)
        elif event.type() == QEvent.Type.MouseMove:
            scene_pos = self.canvas.scene_pos_from_event(event)
            if self.canvas._template_insert_active:
                self.canvas._render_template_preview(scene_pos)
            elif self.canvas._smiles_insert_active:
                self.canvas._render_smiles_preview(scene_pos)
            elif getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)() == Qt.MouseButton.NoButton:
                self.canvas._update_hover_highlight(scene_pos)
            else:
                self.canvas._clear_hover_highlight()
        return base_viewport_event(event)

    def wheel_event(self, event, *, base_wheel_event) -> None:
        self.canvas._touch_interaction()
        self.canvas._reset_view_transform()
        delta = event.pixelDelta()
        if delta.isNull():
            angle = event.angleDelta()
            dx = -int(angle.x() / 2)
            dy = -int(angle.y() / 2)
        else:
            dx = -delta.x()
            dy = -delta.y()
        if dx or dy:
            self.canvas.horizontalScrollBar().setValue(self.canvas.horizontalScrollBar().value() + dx)
            self.canvas.verticalScrollBar().setValue(self.canvas.verticalScrollBar().value() + dy)
            event.accept()
            return
        base_wheel_event(event)

    def scroll_contents_by(self, dx: int, dy: int, *, base_scroll_contents_by) -> None:
        base_scroll_contents_by(dx, dy)
        self.canvas._reset_view_transform()
        self.canvas._refresh_hover_from_cursor()
