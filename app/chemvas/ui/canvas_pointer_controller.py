from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QMenu

from chemvas.features.rendering import (
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    double_position_for_style,
    is_positionable_double_bond_style,
    style_for_double_position,
)
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_model_access import bond_for_id
from chemvas.ui.input_view_access import (
    global_pos_from_event_for,
    reset_view_transform_for,
    scroll_view_by_for,
    set_zoom_for,
    touch_interaction_for,
    zoom_factor_for,
)
from chemvas.ui.sheet_setup_access import scene_pos_in_sheet_for

_DRAWING_TOOL_NAMES = frozenset(
    {"bond", "text", "mark", "note", "arrow", "ts_bracket", "shape", "orbital"}
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
        hover_controller,
        tool_controller,
        scene_transform_controller,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state_for(canvas)
        self.hit_testing_service = hit_testing_service
        self.insert_controller = insert_controller
        self.hover = hover_controller
        self.tool_controller = tool_controller
        self.scene_transform = scene_transform_controller

    @staticmethod
    def _accept_event(event) -> None:
        accept = getattr(event, "accept", None)
        if callable(accept):
            accept()

    @staticmethod
    def _tool_draws_on_sheet(tool) -> bool:
        return getattr(tool, "name", None) in _DRAWING_TOOL_NAMES

    def _clear_insert_preview(self, preview_kind: str) -> None:
        clear_preview = getattr(
            self.insert_controller, f"clear_{preview_kind}_preview", None
        )
        if callable(clear_preview):
            clear_preview()

    def _reset_tool_preview(self, tool) -> None:
        deactivate = getattr(tool, "deactivate", None)
        if callable(deactivate):
            deactivate()
        activate = getattr(tool, "activate", None)
        if callable(activate):
            activate()

    def _outside_sheet(self, scene_pos) -> bool:
        return not scene_pos_in_sheet_for(self.canvas, scene_pos)

    def _dispatch_press_event(
        self,
        event,
        *,
        base_event,
        allow_select_tool: bool,
    ) -> None:
        touch_interaction_for(self.canvas)
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._show_double_bond_context_menu(event)
        ):
            self.hover.clear_hover_highlight()
            return
        if (
            self.insert_state.template_active
            and event.button() == Qt.MouseButton.LeftButton
        ):
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                self._clear_insert_preview("template")
                self.hover.clear_hover_highlight()
                self._accept_event(event)
                return
            self.insert_controller.commit_template_insert(scene_pos)
            self.hover.clear_hover_highlight()
            return
        if (
            self.insert_state.smiles_active
            and event.button() == Qt.MouseButton.LeftButton
        ):
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                self._clear_insert_preview("smiles")
                self.hover.clear_hover_highlight()
                self._accept_event(event)
                return
            self.insert_controller.commit_smiles_insert(scene_pos)
            self.hover.clear_hover_highlight()
            return
        active_tool = getattr(self.tool_controller, "active", None)
        if (
            active_tool
            and event.button() == Qt.MouseButton.LeftButton
            and self._tool_draws_on_sheet(active_tool)
        ):
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                self.hover.clear_hover_highlight()
                self._accept_event(event)
                return
        if active_tool and (allow_select_tool or active_tool.name != "select"):
            clear_before_press = getattr(active_tool, "name", None) == "perspective"
            if clear_before_press:
                # Perspective captures an exact scene snapshot on press.
                # Remove transient hover items before that boundary so their
                # normal cleanup is not treated as an external scene mutation.
                self.hover.clear_hover_highlight()
            handled = active_tool.on_mouse_press(event)
            if not clear_before_press:
                # Other tools still consume hover atom/bond IDs while handling
                # their press, so preserve the established clear-after contract.
                self.hover.clear_hover_highlight()
            if handled:
                return
            base_event(event)
            return
        base_event(event)
        self.hover.clear_hover_highlight()

    def _show_double_bond_context_menu(self, event, *, menu_factory=QMenu) -> bool:
        bond_id = self._context_bond_id(event)
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None or not is_positionable_double_bond_style(
            bond.style, bond.order
        ):
            return False

        current_position = double_position_for_style(bond.style, bond.order)
        menu = menu_factory(self.canvas)
        for label, position_style in DOUBLE_BOND_CONTEXT_STYLES:
            target_style = style_for_double_position(
                bond.style, bond.order, position_style
            )
            if target_style is None:
                continue
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(position_style == current_position)
            action.triggered.connect(
                lambda _checked=False, target_style=target_style: (
                    self.scene_transform.apply_bond_style(
                        bond_id,
                        target_style,
                        2,
                    )
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
        scene_pos = self.hit_testing_service.scene_pos_from_event(event)
        if self._outside_sheet(scene_pos):
            if self.insert_state.template_active:
                self._clear_insert_preview("template")
                self.hover.clear_hover_highlight()
                return
            if self.insert_state.smiles_active:
                self._clear_insert_preview("smiles")
                self.hover.clear_hover_highlight()
                return
            active_tool = getattr(self.tool_controller, "active", None)
            if (
                event.buttons() != Qt.MouseButton.NoButton
                and active_tool
                and self._tool_draws_on_sheet(active_tool)
            ):
                self._reset_tool_preview(active_tool)
            self.hover.clear_hover_highlight()
            return
        if self.insert_state.template_active:
            self.insert_controller.render_template_preview(scene_pos)
            return
        if self.insert_state.smiles_active:
            self.insert_controller.render_smiles_preview(scene_pos)
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self.hover.update_hover_highlight(scene_pos)
        else:
            self.hover.clear_hover_highlight()
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and active_tool.on_mouse_move(event):
            return
        base_mouse_move_event(event)

    def mouse_release_event(self, event, *, base_mouse_release_event) -> None:
        touch_interaction_for(self.canvas)
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and self._tool_draws_on_sheet(active_tool):
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                self._reset_tool_preview(active_tool)
                self.hover.clear_hover_highlight()
                self.hover.refresh()
                self._accept_event(event)
                return
        if active_tool and active_tool.on_mouse_release(event):
            self.hover.refresh()
            return
        base_mouse_release_event(event)
        self.hover.refresh()

    def viewport_event(self, event, *, single_shot, base_viewport_event) -> bool:
        if event.type() in {QEvent.Type.Leave, QEvent.Type.Hide}:
            self.hover.clear_hover_highlight()
        elif event.type() == QEvent.Type.Enter:
            single_shot(0, self.hover.refresh)
        elif event.type() == QEvent.Type.MouseMove:
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                if self.insert_state.template_active:
                    self._clear_insert_preview("template")
                elif self.insert_state.smiles_active:
                    self._clear_insert_preview("smiles")
                elif (
                    getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)()
                    != Qt.MouseButton.NoButton
                ):
                    active_tool = getattr(self.tool_controller, "active", None)
                    if active_tool and self._tool_draws_on_sheet(active_tool):
                        self._reset_tool_preview(active_tool)
                self.hover.clear_hover_highlight()
            elif self.insert_state.template_active:
                self.insert_controller.render_template_preview(scene_pos)
            elif self.insert_state.smiles_active:
                self.insert_controller.render_smiles_preview(scene_pos)
            elif (
                getattr(event, "buttons", lambda: Qt.MouseButton.NoButton)()
                == Qt.MouseButton.NoButton
            ):
                self.hover.update_hover_highlight(scene_pos)
            else:
                self.hover.clear_hover_highlight()
        return base_viewport_event(event)

    def wheel_event(self, event, *, base_wheel_event) -> None:
        touch_interaction_for(self.canvas)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle:
                # Smooth, cursor-anchored magnification: ~20% per mouse notch
                # (angle == 120), and proportionally finer for trackpads.
                set_zoom_for(
                    self.canvas,
                    zoom_factor_for(self.canvas) * (1.0015**angle),
                    under_mouse=True,
                )
            event.accept()
            return
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
        self.hover.clear_hover_highlight()
