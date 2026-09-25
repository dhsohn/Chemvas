from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QMenu

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.rendering import (
    DOUBLE_STYLE_CENTER,
    DOUBLE_STYLE_DEFAULT,
    DOUBLE_STYLE_OUTER,
    double_position_for_style,
    is_positionable_double_bond_style,
    style_for_double_position,
)
from chemvas.ui.canvas.canvas_window_access import notify_error_for
from chemvas.ui.canvas.input_view_access import (
    reset_view_transform_for,
    scroll_view_by_for,
    set_zoom_for,
)
from chemvas.ui.canvas.sheet_setup_access import (
    OFF_SHEET_EDIT_GUIDANCE,
    scene_pos_in_sheet_for,
)
from chemvas.ui.dialogs.mark_reassignment_dialog import reassign_mark_with_dialog

_DRAWING_TOOL_NAMES = frozenset(
    {
        "bond",
        "text",
        "mark",
        "note",
        "arrow",
        "line",
        "ts_bracket",
        "shape",
        "orbital",
    }
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
        self.insert_state = canvas.runtime_state.insert_state
        self.hit_testing_service = hit_testing_service
        self.insert_controller = insert_controller
        self.hover = hover_controller
        self.tool_controller = tool_controller
        self.scene_transform = scene_transform_controller
        self._offsheet_gesture_notified = False

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

    def _notify_offsheet_gesture(self) -> None:
        if not self._offsheet_gesture_notified:
            notify_error_for(self.canvas, OFF_SHEET_EDIT_GUIDANCE)
            self._offsheet_gesture_notified = True

    def _cancel_offsheet_drawing(self, tool, buttons) -> None:
        self._reset_tool_preview(tool)
        if buttons & Qt.MouseButton.LeftButton:
            self._notify_offsheet_gesture()

    def _dispatch_press_event(
        self,
        event,
        *,
        base_event,
        allow_select_tool: bool,
    ) -> None:
        self.canvas.runtime_state.selection_info_state.touch_interaction()
        if event.button() == Qt.MouseButton.LeftButton:
            self._offsheet_gesture_notified = False
        if event.button() == Qt.MouseButton.RightButton and (
            self._show_mark_context_menu(event)
            or self._show_double_bond_context_menu(event)
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
                self._notify_offsheet_gesture()
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
                self._notify_offsheet_gesture()
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
                self._notify_offsheet_gesture()
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

    def _show_mark_context_menu(self, event, *, menu_factory=QMenu) -> bool:
        item = self.hit_testing_service.item_at_event(event, prefer_marks=True)
        if item is None or item.data(0) != "mark":
            return False
        self.tool_controller.prepare_for_document_edit()
        self.hover.clear_hover_highlight()
        menu = menu_factory(self.canvas)
        action = menu.addAction("Reassign to atom…")
        if menu.exec(event.globalPosition().toPoint()) is action:
            reassign_mark_with_dialog(self.canvas, item)
        self._accept_event(event)
        return True

    def _show_double_bond_context_menu(self, event, *, menu_factory=QMenu) -> bool:
        bond_id = self._context_bond_id(event)
        bond = self.canvas.model.bond_for_id(bond_id)
        if bond is None or not is_positionable_double_bond_style(
            bond.style, bond.order
        ):
            return False

        self.tool_controller.prepare_for_document_edit()
        self.hover.clear_hover_highlight()
        # Cancellation restores model objects and can remove a preview bond.
        bond = self.canvas.model.bond_for_id(bond_id)
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
        menu.exec(event.globalPosition().toPoint())
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

    def _edit_arrow_labels_at(self, event) -> bool:
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool is None or active_tool.name not in {"select", "arrow", "line"}:
            return False
        item = self.hit_testing_service.item_at_event(event)
        if item is None or item.data(0) not in VALID_ARROW_KINDS:
            return False
        self.canvas.services.scene_decoration_service.edit_arrow_labels(item)
        return True

    def mouse_double_click_event(self, event, *, base_mouse_double_click_event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._edit_arrow_labels_at(
            event
        ):
            self.hover.clear_hover_highlight()
            self._accept_event(event)
            return
        self._dispatch_press_event(
            event,
            base_event=base_mouse_double_click_event,
            allow_select_tool=False,
        )

    def mouse_move_event(self, event, *, base_mouse_move_event) -> None:
        self.canvas.runtime_state.selection_info_state.touch_interaction()
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
                event.buttons() == Qt.MouseButton.NoButton
                or active_tool is None
                or self._tool_draws_on_sheet(active_tool)
            ):
                if event.buttons() != Qt.MouseButton.NoButton and active_tool:
                    self._cancel_offsheet_drawing(active_tool, event.buttons())
                self.hover.clear_hover_highlight()
                return
            # These tools already accept off-sheet press/release. Keep their
            # held-pointer preview on the same normal dispatch path too.
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
        self.canvas.runtime_state.selection_info_state.touch_interaction()
        active_tool = getattr(self.tool_controller, "active", None)
        if active_tool and self._tool_draws_on_sheet(active_tool):
            scene_pos = self.hit_testing_service.scene_pos_from_event(event)
            if self._outside_sheet(scene_pos):
                self._cancel_offsheet_drawing(active_tool, event.button())
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
        return base_viewport_event(event)

    def wheel_event(self, event, *, base_wheel_event) -> None:
        self.canvas.runtime_state.selection_info_state.touch_interaction()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle:
                # Smooth, cursor-anchored magnification: ~20% per mouse notch
                # (angle == 120), and proportionally finer for trackpads.
                set_zoom_for(
                    self.canvas,
                    float(self.canvas.runtime_state.input_view_state.zoom)
                    * (1.0015**angle),
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
