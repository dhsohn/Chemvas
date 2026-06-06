from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QNativeGestureEvent

from ui.canvas_view_ports import input_controller_for_view, pointer_controller_for_view


def route_key_press_event(view, event, *, base_key_press_event) -> None:
    input_controller = input_controller_for_view(view)
    if input_controller is None:
        base_key_press_event(event)
        return
    input_controller.key_press_event(event)


def route_mouse_press_event(view, event, *, base_mouse_press_event) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_mouse_press_event(event)
        return
    pointer_controller.mouse_press_event(
        event,
        base_mouse_press_event=base_mouse_press_event,
    )


def route_mouse_double_click_event(view, event, *, base_mouse_double_click_event) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_mouse_double_click_event(event)
        return
    pointer_controller.mouse_double_click_event(
        event,
        base_mouse_double_click_event=base_mouse_double_click_event,
    )


def route_mouse_move_event(view, event, *, base_mouse_move_event) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_mouse_move_event(event)
        return
    pointer_controller.mouse_move_event(
        event,
        base_mouse_move_event=base_mouse_move_event,
    )


def route_mouse_release_event(view, event, *, base_mouse_release_event) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_mouse_release_event(event)
        return
    pointer_controller.mouse_release_event(
        event,
        base_mouse_release_event=base_mouse_release_event,
    )


def route_viewport_event(view, event, *, base_viewport_event) -> bool:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        return base_viewport_event(event)
    return pointer_controller.viewport_event(
        event,
        single_shot=QTimer.singleShot,
        base_viewport_event=base_viewport_event,
    )


def route_wheel_event(view, event, *, base_wheel_event) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_wheel_event(event)
        return
    pointer_controller.wheel_event(
        event,
        base_wheel_event=base_wheel_event,
    )


def route_event(view, event, *, base_event) -> bool:
    input_controller = input_controller_for_view(view)
    if input_controller is None:
        return base_event(event)
    return input_controller.event(event, native_gesture_event_type=QNativeGestureEvent)


def route_scroll_contents_by(view, dx: int, dy: int, *, base_scroll_contents_by) -> None:
    pointer_controller = pointer_controller_for_view(view)
    if pointer_controller is None:
        base_scroll_contents_by(dx, dy)
        return
    pointer_controller.scroll_contents_by(
        dx,
        dy,
        base_scroll_contents_by=base_scroll_contents_by,
    )


__all__ = [
    "route_event",
    "route_key_press_event",
    "route_mouse_double_click_event",
    "route_mouse_move_event",
    "route_mouse_press_event",
    "route_mouse_release_event",
    "route_scroll_contents_by",
    "route_viewport_event",
    "route_wheel_event",
]
