from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import ui.canvas_view_event_router as router


def test_route_key_press_event_uses_input_controller_or_base(monkeypatch) -> None:
    event = object()
    input_controller = SimpleNamespace(key_press_event=mock.Mock())
    base = mock.Mock()
    monkeypatch.setattr(router, "input_controller_for_view", mock.Mock(return_value=input_controller))

    router.route_key_press_event("view", event, base_key_press_event=base)

    input_controller.key_press_event.assert_called_once_with(event)
    base.assert_not_called()

    router.input_controller_for_view.return_value = None
    router.route_key_press_event("view", event, base_key_press_event=base)

    base.assert_called_once_with(event)


def test_route_pointer_mouse_events_use_pointer_controller_or_base(monkeypatch) -> None:
    event = object()
    pointer_controller = SimpleNamespace(
        mouse_press_event=mock.Mock(),
        mouse_double_click_event=mock.Mock(),
        mouse_move_event=mock.Mock(),
        mouse_release_event=mock.Mock(),
    )
    base = mock.Mock()
    monkeypatch.setattr(router, "pointer_controller_for_view", mock.Mock(return_value=pointer_controller))

    router.route_mouse_press_event("view", event, base_mouse_press_event=base)
    router.route_mouse_double_click_event("view", event, base_mouse_double_click_event=base)
    router.route_mouse_move_event("view", event, base_mouse_move_event=base)
    router.route_mouse_release_event("view", event, base_mouse_release_event=base)

    pointer_controller.mouse_press_event.assert_called_once_with(event, base_mouse_press_event=base)
    pointer_controller.mouse_double_click_event.assert_called_once_with(event, base_mouse_double_click_event=base)
    pointer_controller.mouse_move_event.assert_called_once_with(event, base_mouse_move_event=base)
    pointer_controller.mouse_release_event.assert_called_once_with(event, base_mouse_release_event=base)
    base.assert_not_called()

    router.pointer_controller_for_view.return_value = None
    router.route_mouse_press_event("view", event, base_mouse_press_event=base)

    base.assert_called_once_with(event)


def test_route_viewport_wheel_event_and_scroll_use_pointer_controller_or_base(monkeypatch) -> None:
    event = object()
    pointer_controller = SimpleNamespace(
        viewport_event=mock.Mock(return_value=True),
        wheel_event=mock.Mock(),
        scroll_contents_by=mock.Mock(),
    )
    base_viewport = mock.Mock(return_value=False)
    base_wheel = mock.Mock()
    base_scroll = mock.Mock()
    monkeypatch.setattr(router, "pointer_controller_for_view", mock.Mock(return_value=pointer_controller))

    assert router.route_viewport_event("view", event, base_viewport_event=base_viewport) is True
    router.route_wheel_event("view", event, base_wheel_event=base_wheel)
    router.route_scroll_contents_by("view", 3, -2, base_scroll_contents_by=base_scroll)

    pointer_controller.viewport_event.assert_called_once_with(
        event,
        single_shot=router.QTimer.singleShot,
        base_viewport_event=base_viewport,
    )
    pointer_controller.wheel_event.assert_called_once_with(event, base_wheel_event=base_wheel)
    pointer_controller.scroll_contents_by.assert_called_once_with(3, -2, base_scroll_contents_by=base_scroll)
    base_viewport.assert_not_called()
    base_wheel.assert_not_called()
    base_scroll.assert_not_called()

    router.pointer_controller_for_view.return_value = None
    assert router.route_viewport_event("view", event, base_viewport_event=base_viewport) is False
    router.route_wheel_event("view", event, base_wheel_event=base_wheel)
    router.route_scroll_contents_by("view", 3, -2, base_scroll_contents_by=base_scroll)

    base_viewport.assert_called_once_with(event)
    base_wheel.assert_called_once_with(event)
    base_scroll.assert_called_once_with(3, -2)


def test_route_event_uses_input_controller_or_base(monkeypatch) -> None:
    event = object()
    input_controller = SimpleNamespace(event=mock.Mock(return_value=True))
    base = mock.Mock(return_value=False)
    monkeypatch.setattr(router, "input_controller_for_view", mock.Mock(return_value=input_controller))

    assert router.route_event("view", event, base_event=base) is True

    input_controller.event.assert_called_once_with(
        event,
        native_gesture_event_type=router.QNativeGestureEvent,
    )
    base.assert_not_called()

    router.input_controller_for_view.return_value = None
    assert router.route_event("view", event, base_event=base) is False

    base.assert_called_once_with(event)


def test_route_scene_selection_callbacks_use_stable_callback_state(monkeypatch) -> None:
    calls: list[str] = []
    callbacks = SimpleNamespace(
        scene_selection_group=lambda: calls.append("expand"),
        scene_selection_outline=lambda: calls.append("outline"),
    )
    monkeypatch.setattr(
        router,
        "callback_state_for",
        mock.Mock(return_value=callbacks),
    )

    view = object()
    router.route_scene_selection_group_changed(view)
    router.route_scene_selection_outline_changed(view)

    assert calls == ["expand", "outline"]
    assert router.callback_state_for.call_args_list == [mock.call(view), mock.call(view)]
