from __future__ import annotations

from collections.abc import Callable

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
from ui.canvas_model_access import bond_for_id
from ui.hover_highlight_access import clear_hover_highlight_for
from ui.input_view_access import (
    global_pos_from_event_for,
    reset_view_transform_for,
    scroll_view_by_for,
    touch_interaction_for,
)

DOUBLE_BOND_CONTEXT_STYLES = (
    ("Inward", DOUBLE_STYLE_DEFAULT),
    ("Centered", DOUBLE_STYLE_CENTER),
    ("Outward", DOUBLE_STYLE_OUTER),
)


class CanvasPointerController:
    def __init__(
        self,
        canvas,
        *,
        hit_testing_service,
        insert_controller,
        hover_interaction_service,
        tool_controller,
        scene_transform_controller,
        hover_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)
        self.hit_testing_service = hit_testing_service
        self.insert_controller = insert_controller
        self.hover_interaction_service = hover_interaction_service
        self.tool_controller = tool_controller
        self.scene_transform = scene_transform_controller
        self._hover_refresh = hover_refresh or (lambda: None)

    def _dispatch_press_event(
        self,
        event,
        *,
        base_event,
        allow_select_tool: bool,
    ) -> None:
        touch_interaction_for(self.canvas)
        if event.button() == Qt.MouseButton.RightButton and self._show_double_bond_context_menu(event):
            clear_hover_highlight_for(self.canvas)
            return
        if self.insert_state.template_active and event.button() == Qt.MouseButton.LeftButton:
            self.insert_controller.commit_template_insert(self.hit_testing_service.scene_pos_from_event(event))
            clear_hover_highlight_for(self.canvas)
            return
        if self.insert_state.smiles_active and event.button() == Qt.MouseButton.LeftButton:
            self.insert_controller.commit_smiles_insert(self.hit_testing_service.scene_pos_from_event(event))
            clear_hover_highlight_for(self.canvas)
            return
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and (allow_select_tool or active_tool.name != "select") and active_tool.on_mouse_press(event):
            clear_hover_highlight_for(self.canvas)
            return
        base_event(event)
        clear_hover_highlight_for(self.canvas)

    def _show_double_bond_context_menu(self, event, *, menu_factory=QMenu) -> bool:
        bond_id = self._context_bond_id(event)
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None or not is_plain_double_bond_style(bond.style, bond.order):
            return False

        current_style = normalized_plain_double_style(bond.style, bond.order)
        menu = menu_factory(self.canvas)
        for label, style in DOUBLE_BOND_CONTEXT_STYLES:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(style == current_style)
            action.triggered.connect(
                lambda _checked=False, target_style=style: self.scene_transform.apply_bond_style(
                    bond_id,
                    target_style,
                    2,
                )
            )
        menu.exec(global_pos_from_event_for(self.canvas, event))
        return True

    def _context_bond_id(self, event) -> int | None:
        if not hasattr(event, "position"):
            return None
        item = self.hit_testing_service.item_at_event(event)
        if item is not None and item.data(0) == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                return bond_id
        return self.hit_testing_service.bond_id_from_event(event)

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
        touch_interaction_for(self.canvas)
        if self.insert_state.template_active:
            self.insert_controller.render_template_preview(self.hit_testing_service.scene_pos_from_event(event))
            return
        if self.insert_state.smiles_active:
            self.insert_controller.render_smiles_preview(self.hit_testing_service.scene_pos_from_event(event))
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self.hover_interaction_service.update_hover_highlight(self.hit_testing_service.scene_pos_from_event(event))
        else:
            clear_hover_highlight_for(self.canvas)
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and active_tool.on_mouse_move(event):
            return
        base_mouse_move_event(event)

    def mouse_release_event(self, event, *, base_mouse_release_event) -> None:
        touch_interaction_for(self.canvas)
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and active_tool.on_mouse_release(event):
            self._hover_refresh()
            return
        base_mouse_release_event(event)
        self._hover_refresh()

    def viewport_event(self, event, *, single_shot, base_viewport_event) -> bool:
        if event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
            clear_hover_highlight_for(self.canvas)
        elif event.type() == QEvent.Type.Enter:
            single_shot(0, self._hover_refresh)
        elif event.type() == QEvent.Type.MouseMove:
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self.insert_state.template_active:
                self.insert_controller.render_template_preview(scene_pos)
            elif self.insert_state.smiles_active:
                self.insert_controller.render_smiles_preview(scene_pos)
            elif getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)() == Qt.MouseButton.NoButton:
                self.hover_interaction_service.update_hover_highlight(scene_pos)
            else:
                clear_hover_highlight_for(self.canvas)
        return base_viewport_event(event)

    def wheel_event(self, event, *, base_wheel_event) -> None:
        touch_interaction_for(self.canvas)
        reset_view_transform_for(self.canvas)
        delta = event.pixelDelta()
        if delta.isNull():
            angle = event.angleDelta()
            dx = -int(angle.x() / 2)
            dy = -int(angle.y() / 2)
        else:
            dx = -delta.x()
            dy = -delta.y()
        if scroll_view_by_for(self.canvas, dx, dy):
            event.accept()
            return
        base_wheel_event(event)

    def scroll_contents_by(self, dx: int, dy: int, *, base_scroll_contents_by) -> None:
        base_scroll_contents_by(dx, dy)
        reset_view_transform_for(self.canvas)
        self._hover_refresh()
