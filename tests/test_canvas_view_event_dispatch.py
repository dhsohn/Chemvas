"""CanvasView hands each Qt event to the input services, or to Qt itself."""

from __future__ import annotations

import contextlib
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QGraphicsView

import chemvas.ui.canvas_view as canvas_view_module
from chemvas.ui.canvas_callback_state import (
    callback_state_for,
    run_scene_selection_group_callback_for,
    run_scene_selection_outline_callback_for,
)
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from tests.canvas_factory import build_canvas_view

POINTER_OVERRIDES = [
    ("mousePressEvent", "mouse_press_event", "base_mouse_press_event"),
    (
        "mouseDoubleClickEvent",
        "mouse_double_click_event",
        "base_mouse_double_click_event",
    ),
    ("mouseMoveEvent", "mouse_move_event", "base_mouse_move_event"),
    ("mouseReleaseEvent", "mouse_release_event", "base_mouse_release_event"),
    ("wheelEvent", "wheel_event", "base_wheel_event"),
]


@pytest.fixture
def view(qt_application):
    canvas = build_canvas_view()
    yield canvas
    schedule_canvas_deletion_for(canvas)
    qt_application.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)


@contextlib.contextmanager
def _attached(*, pointer=None, keyboard=None):
    """Swap what the view port resolves, for one block of one test only.

    The swap ends before the fixture closes the canvas: Qt delivers real events
    during close, and a half-built controller double must not receive them.
    """
    with (
        mock.patch.object(
            canvas_view_module,
            "pointer_controller_for_view",
            mock.Mock(return_value=pointer),
        ),
        mock.patch.object(
            canvas_view_module,
            "input_controller_for_view",
            mock.Mock(return_value=keyboard),
        ),
    ):
        yield


@pytest.mark.parametrize(("override", "handler", "base_keyword"), POINTER_OVERRIDES)
def test_pointer_override_hands_the_event_and_the_base_handler_to_the_controller(
    view, override, handler, base_keyword
) -> None:
    controller = SimpleNamespace(**{handler: mock.Mock()})
    event = SimpleNamespace(accept=mock.Mock())

    with (
        _attached(pointer=controller),
        mock.patch.object(QGraphicsView, override, new=mock.Mock()) as base,
    ):
        getattr(view, override)(event)

    getattr(controller, handler).assert_called_once_with(event, **{base_keyword: base})
    base.assert_not_called()
    event.accept.assert_not_called()


@pytest.mark.parametrize(("override", "handler", "base_keyword"), POINTER_OVERRIDES)
def test_pointer_override_falls_back_to_qt_before_services_are_attached(
    view, override, handler, base_keyword
) -> None:
    event = SimpleNamespace(accept=mock.Mock())

    with (
        _attached(),
        mock.patch.object(QGraphicsView, override, new=mock.Mock()) as base,
    ):
        getattr(view, override)(event)

    base.assert_called_once_with(event)


@pytest.mark.parametrize(("override", "handler", "base_keyword"), POINTER_OVERRIDES[:4])
def test_a_failing_mouse_handler_is_contained_at_the_qt_boundary(
    view, override, handler, base_keyword
) -> None:
    controller = SimpleNamespace(
        **{handler: mock.Mock(side_effect=RuntimeError("tool failed"))}
    )
    event = SimpleNamespace(accept=mock.Mock())

    with (
        _attached(pointer=controller),
        mock.patch.object(QGraphicsView, override, new=mock.Mock()),
    ):
        getattr(view, override)(event)

    event.accept.assert_called_once_with()


def test_wheel_errors_are_outside_the_editing_exception_boundary(view) -> None:
    controller = SimpleNamespace(
        wheel_event=mock.Mock(side_effect=RuntimeError("zoom failed"))
    )

    with (
        _attached(pointer=controller),
        mock.patch.object(QGraphicsView, "wheelEvent", new=mock.Mock()),
        pytest.raises(RuntimeError, match="zoom failed"),
    ):
        view.wheelEvent(SimpleNamespace(accept=mock.Mock()))


def test_viewport_event_passes_the_timer_and_returns_the_controller_answer(
    view,
) -> None:
    controller = SimpleNamespace(viewport_event=mock.Mock(return_value=True))
    event = object()

    with mock.patch.object(
        QGraphicsView, "viewportEvent", new=mock.Mock(return_value=False)
    ) as base:
        with _attached(pointer=controller):
            assert view.viewportEvent(event) is True
        controller.viewport_event.assert_called_once_with(
            event,
            single_shot=canvas_view_module.QTimer.singleShot,
            base_viewport_event=base,
        )
        base.assert_not_called()

        with _attached():
            assert view.viewportEvent(event) is False
        base.assert_called_once_with(event)


def test_scroll_contents_by_goes_to_the_controller_or_to_qt(view) -> None:
    controller = SimpleNamespace(scroll_contents_by=mock.Mock())

    with mock.patch.object(QGraphicsView, "scrollContentsBy", new=mock.Mock()) as base:
        with _attached(pointer=controller):
            view.scrollContentsBy(3, -2)
        controller.scroll_contents_by.assert_called_once_with(
            3, -2, base_scroll_contents_by=base
        )
        base.assert_not_called()

        with _attached():
            view.scrollContentsBy(3, -2)
        base.assert_called_once_with(3, -2)


def test_key_press_goes_to_the_input_controller_or_to_qt(view) -> None:
    controller = SimpleNamespace(key_press_event=mock.Mock())
    event = object()

    with mock.patch.object(QGraphicsView, "keyPressEvent", new=mock.Mock()) as base:
        with _attached(keyboard=controller):
            view.keyPressEvent(event)
        controller.key_press_event.assert_called_once_with(event)
        base.assert_not_called()

        with _attached():
            view.keyPressEvent(event)
        base.assert_called_once_with(event)


@pytest.mark.parametrize("notification_fails", [False, True])
def test_failed_key_handler_is_reported_and_consumed(view, notification_fails) -> None:
    controller = SimpleNamespace(
        key_press_event=mock.Mock(side_effect=ValueError("invalid edit"))
    )
    event = SimpleNamespace(accept=mock.Mock())
    with (
        _attached(keyboard=controller),
        mock.patch.object(
            canvas_view_module,
            "notify_error_for",
            side_effect=RuntimeError("notification failed")
            if notification_fails
            else None,
        ) as notify,
    ):
        view.keyPressEvent(event)

    notify.assert_called_once_with(
        view, "The current interaction could not be completed. Try again."
    )
    event.accept.assert_called_once_with()


def test_event_passes_the_native_gesture_type_and_returns_the_answer(view) -> None:
    controller = SimpleNamespace(event=mock.Mock(return_value=True))
    event = object()

    with mock.patch.object(
        QGraphicsView, "event", new=mock.Mock(return_value=False)
    ) as base:
        with _attached(keyboard=controller):
            assert view.event(event) is True
        controller.event.assert_called_once_with(
            event,
            native_gesture_event_type=canvas_view_module.QNativeGestureEvent,
        )
        base.assert_not_called()

        with _attached():
            assert view.event(event) is False
        base.assert_called_once_with(event)


def test_scene_selection_callbacks_run_when_set_and_tolerate_none(view) -> None:
    calls: list[str] = []
    callbacks = callback_state_for(view)
    previous = (callbacks.scene_selection_group, callbacks.scene_selection_outline)
    callbacks.scene_selection_group = lambda: calls.append("expand")
    callbacks.scene_selection_outline = lambda: calls.append("outline")

    run_scene_selection_group_callback_for(view)
    run_scene_selection_outline_callback_for(view)
    view.handle_scene_selection_group_changed()
    view.handle_scene_selection_outline_changed()

    assert calls == ["expand", "outline", "expand", "outline"]

    callbacks.scene_selection_group = None
    callbacks.scene_selection_outline = None
    run_scene_selection_group_callback_for(view)
    run_scene_selection_outline_callback_for(view)

    assert calls == ["expand", "outline", "expand", "outline"]
    callbacks.scene_selection_group, callbacks.scene_selection_outline = previous
