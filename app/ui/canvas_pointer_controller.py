from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QMenu

from ui.bond_style_logic import (
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    is_plain_double_bond_style,
    normalized_plain_double_style,
)
from ui.canvas_insert_state import insert_state_for

DOUBLE_BOND_CONTEXT_STYLES = (
    ("Inward", DOUBLE_STYLE_DEFAULT),
    ("Centered", DOUBLE_STYLE_CENTER),
    ("Outward", DOUBLE_STYLE_OUTER),
)


class CanvasPointerController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)

    def _dispatch_press_event(
        self,
        event,
        *,
        base_event,
        allow_select_tool: bool,
    ) -> None:
        self.canvas._touch_interaction()
        if event.button() == Qt.MouseButton.RightButton and self._show_double_bond_context_menu(event):
            self.canvas._clear_hover_highlight()
            return
        if self.insert_state.template_active and event.button() == Qt.MouseButton.LeftButton:
            self.canvas._commit_template_insert(self.canvas.scene_pos_from_event(event))
            self.canvas._clear_hover_highlight()
            return
        if self.insert_state.smiles_active and event.button() == Qt.MouseButton.LeftButton:
            self.canvas._commit_smiles_insert(self.canvas.scene_pos_from_event(event))
            self.canvas._clear_hover_highlight()
            return
        active_tool = self.canvas.tools.active
        if active_tool and (allow_select_tool or active_tool.name != "select") and active_tool.on_mouse_press(event):
            self.canvas._clear_hover_highlight()
            return
        base_event(event)
        self.canvas._clear_hover_highlight()

    def _show_double_bond_context_menu(self, event, *, menu_factory=QMenu) -> bool:
        bond_id = self._context_bond_id(event)
        if bond_id is None or not (0 <= bond_id < len(self.canvas.model.bonds)):
            return False
        bond = self.canvas.model.bonds[bond_id]
        if bond is None or not is_plain_double_bond_style(bond.style, bond.order):
            return False

        current_style = normalized_plain_double_style(bond.style, bond.order)
        menu = menu_factory(self.canvas)
        for label, style in DOUBLE_BOND_CONTEXT_STYLES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(style == current_style)
            action.triggered.connect(
                lambda _checked=False, target_style=style: self.canvas.apply_bond_style(
                    bond_id,
                    target_style,
                    2,
                )
            )
        menu.exec(self._event_global_pos(event))
        return True

    def _context_bond_id(self, event) -> int | None:
        if not hasattr(event, "position"):
            return None
        item = self.canvas.item_at_event(event)
        if item is not None and item.data(0) == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                return bond_id
        return self.canvas.bond_id_from_event(event)

    def _event_global_pos(self, event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        return self.canvas.viewport().mapToGlobal(event.position().toPoint())

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
        if self.insert_state.template_active:
            self.canvas._render_template_preview(self.canvas.scene_pos_from_event(event))
            return
        if self.insert_state.smiles_active:
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
            if self.insert_state.template_active:
                self.canvas._render_template_preview(scene_pos)
            elif self.insert_state.smiles_active:
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
