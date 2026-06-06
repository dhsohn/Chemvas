from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform

from ui.canvas_hover_state import hover_state_for
from ui.input_view_state import input_view_state_for
from ui.selection_info_state import selection_info_state_for


def shortcut_modifiers_for(event) -> Qt.KeyboardModifier:
    mask = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
    )
    return event.modifiers() & mask


def reset_view_transform_for(canvas) -> None:
    state = input_view_state_for(canvas)
    state.base_transform = QTransform()
    state.perspective_shear = 0.0
    state.perspective_scale_y = 1.0
    canvas.setTransform(QTransform())


def update_view_transform_for(canvas) -> None:
    state = input_view_state_for(canvas)
    transform = QTransform(state.base_transform)
    if state.perspective_shear or state.perspective_scale_y != 1.0:
        transform.shear(state.perspective_shear, 0.0)
        transform.scale(1.0, state.perspective_scale_y)
    canvas.setTransform(transform)


def rotate_view_for(canvas, angle_degrees: float) -> None:
    if not angle_degrees:
        return
    state = input_view_state_for(canvas)
    transform = QTransform(state.base_transform)
    transform.rotate(angle_degrees)
    state.base_transform = transform
    update_view_transform_for(canvas)


def touch_interaction_for(canvas) -> None:
    selection_info_state_for(canvas).last_interaction_time = time.monotonic()


def viewport_center_scene_pos_for(canvas):
    return canvas.mapToScene(canvas.viewport().rect().center())


def focused_scene_item_for(canvas):
    scene = getattr(canvas, "scene", None)
    if not callable(scene):
        return None
    return scene().focusItem()


def focus_canvas_for(canvas, reason) -> None:
    canvas.setFocus(reason)


def set_scene_rect_for(canvas, rect) -> None:
    canvas.setSceneRect(rect)


def update_viewport_for(canvas) -> None:
    canvas.viewport().update()


def set_focused_scene_item_for(canvas, item) -> None:
    scene = getattr(canvas, "scene", None)
    if callable(scene):
        scene().setFocusItem(item)


def scene_pos_from_global_pos_for(canvas, global_pos):
    viewport = canvas.viewport()
    viewport_pos = viewport.mapFromGlobal(global_pos)
    if not viewport.rect().contains(viewport_pos):
        return None
    return canvas.mapToScene(viewport_pos)


def global_pos_from_event_for(canvas, event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    if hasattr(event, "globalPos"):
        return event.globalPos()
    return canvas.viewport().mapToGlobal(event.position().toPoint())


def device_pixel_ratio_for(canvas) -> float:
    return float(canvas.devicePixelRatioF())


def scroll_view_by_for(canvas, dx: int, dy: int) -> bool:
    if not dx and not dy:
        return False
    horizontal = canvas.horizontalScrollBar()
    vertical = canvas.verticalScrollBar()
    horizontal.setValue(horizontal.value() + dx)
    vertical.setValue(vertical.value() + dy)
    return True


def view_scale_for(canvas) -> float:
    return float(canvas.transform().m11())


def should_override_chemdraw_shortcut_for(canvas, event) -> bool:
    modifiers = shortcut_modifiers_for(event)
    if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
        return False
    text = event.text()
    if hover_state_for(canvas).atom_id is not None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return True
        return text in {
            "+",
            "-",
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "h",
            "i",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "q",
            "r",
            "s",
            "u",
            "v",
            "w",
            "x",
            "z",
            "A",
            "B",
            "C",
            "E",
            "F",
            "H",
            "K",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "S",
            "Y",
            "Z",
        }
    if hover_state_for(canvas).bond_id is not None:
        return text in {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "a", "b", "h", "w", "B", "H"}
    return False


__all__ = [
    "device_pixel_ratio_for",
    "focus_canvas_for",
    "focused_scene_item_for",
    "global_pos_from_event_for",
    "reset_view_transform_for",
    "rotate_view_for",
    "scene_pos_from_global_pos_for",
    "shortcut_modifiers_for",
    "should_override_chemdraw_shortcut_for",
    "scroll_view_by_for",
    "set_scene_rect_for",
    "set_focused_scene_item_for",
    "touch_interaction_for",
    "update_viewport_for",
    "update_view_transform_for",
    "view_scale_for",
    "viewport_center_scene_pos_for",
]
