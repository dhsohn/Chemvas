from types import SimpleNamespace
from unittest import mock

from ui.input_view_access import (
    device_pixel_ratio_for,
    focus_canvas_for,
    focused_scene_item_for,
    global_pos_from_event_for,
    scene_pos_from_global_pos_for,
    scroll_view_by_for,
    set_focused_scene_item_for,
    set_scene_rect_for,
    update_viewport_for,
    viewport_center_scene_pos_for,
)


class _Rect:
    def center(self):
        return "viewport-center"


class _Viewport:
    def rect(self):
        return _Rect()


class _Scene:
    def __init__(self, focus_item=None) -> None:
        self._focus_item = focus_item
        self.focused_item = None

    def focusItem(self):
        return self._focus_item

    def setFocusItem(self, item) -> None:
        self.focused_item = item


class _ContainingRect:
    def __init__(self, contains: bool) -> None:
        self._contains = contains

    def contains(self, _pos) -> bool:
        return self._contains


class _GlobalViewport:
    def __init__(self, contains: bool = True) -> None:
        self.contains = contains

    def mapFromGlobal(self, pos):
        return f"viewport:{pos}"

    def mapToGlobal(self, pos):
        return f"global:{pos}"

    def rect(self):
        return _ContainingRect(self.contains)


class _ScrollBar:
    def __init__(self, value: int) -> None:
        self._value = value
        self.updated_value: int | None = None

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        self.updated_value = value


class _Point:
    def __init__(self, value) -> None:
        self.value = value

    def toPoint(self):
        return self.value


def test_viewport_center_scene_pos_maps_viewport_center_to_scene() -> None:
    canvas = SimpleNamespace(
        viewport=mock.Mock(return_value=_Viewport()),
        mapToScene=mock.Mock(return_value="scene-center"),
    )

    assert viewport_center_scene_pos_for(canvas) == "scene-center"

    canvas.viewport.assert_called_once_with()
    canvas.mapToScene.assert_called_once_with("viewport-center")


def test_focused_scene_item_for_reads_scene_focus_item() -> None:
    focus_item = object()
    scene = _Scene(focus_item)
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    assert focused_scene_item_for(canvas) is focus_item

    canvas.scene.assert_called_once_with()


def test_focused_scene_item_for_handles_missing_scene() -> None:
    assert focused_scene_item_for(SimpleNamespace()) is None


def test_focus_canvas_for_calls_canvas_focus() -> None:
    canvas = SimpleNamespace(setFocus=mock.Mock())

    focus_canvas_for(canvas, "reason")

    canvas.setFocus.assert_called_once_with("reason")


def test_scene_rect_and_viewport_helpers_delegate_to_canvas_view() -> None:
    viewport = SimpleNamespace(update=mock.Mock())
    canvas = SimpleNamespace(setSceneRect=mock.Mock(), viewport=mock.Mock(return_value=viewport))
    rect = object()

    set_scene_rect_for(canvas, rect)
    update_viewport_for(canvas)

    canvas.setSceneRect.assert_called_once_with(rect)
    canvas.viewport.assert_called_once_with()
    viewport.update.assert_called_once_with()


def test_set_focused_scene_item_for_sets_scene_focus_item() -> None:
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    item = object()

    set_focused_scene_item_for(canvas, item)

    canvas.scene.assert_called_once_with()
    assert scene.focused_item is item


def test_scene_pos_from_global_pos_maps_inside_viewport_to_scene() -> None:
    canvas = SimpleNamespace(
        viewport=mock.Mock(return_value=_GlobalViewport(contains=True)),
        mapToScene=mock.Mock(return_value="scene-pos"),
    )

    assert scene_pos_from_global_pos_for(canvas, "global-pos") == "scene-pos"

    canvas.viewport.assert_called_once_with()
    canvas.mapToScene.assert_called_once_with("viewport:global-pos")


def test_scene_pos_from_global_pos_returns_none_outside_viewport() -> None:
    canvas = SimpleNamespace(
        viewport=mock.Mock(return_value=_GlobalViewport(contains=False)),
        mapToScene=mock.Mock(return_value="scene-pos"),
    )

    assert scene_pos_from_global_pos_for(canvas, "global-pos") is None

    canvas.mapToScene.assert_not_called()


def test_global_pos_from_event_prefers_qt6_global_position() -> None:
    event = SimpleNamespace(globalPosition=mock.Mock(return_value=_Point("qt6-global")))

    assert global_pos_from_event_for(SimpleNamespace(), event) == "qt6-global"

    event.globalPosition.assert_called_once_with()


def test_global_pos_from_event_keeps_qt5_global_pos() -> None:
    event = SimpleNamespace(globalPos=mock.Mock(return_value="qt5-global"))

    assert global_pos_from_event_for(SimpleNamespace(), event) == "qt5-global"

    event.globalPos.assert_called_once_with()


def test_global_pos_from_event_maps_event_position_through_viewport() -> None:
    canvas = SimpleNamespace(viewport=mock.Mock(return_value=_GlobalViewport()))
    event = SimpleNamespace(position=mock.Mock(return_value=_Point("event-pos")))

    assert global_pos_from_event_for(canvas, event) == "global:event-pos"

    canvas.viewport.assert_called_once_with()
    event.position.assert_called_once_with()


def test_device_pixel_ratio_for_reads_view_ratio() -> None:
    canvas = SimpleNamespace(devicePixelRatioF=mock.Mock(return_value=2))

    assert device_pixel_ratio_for(canvas) == 2.0

    canvas.devicePixelRatioF.assert_called_once_with()


def test_scroll_view_by_for_updates_scrollbars() -> None:
    horizontal = _ScrollBar(10)
    vertical = _ScrollBar(20)
    canvas = SimpleNamespace(
        horizontalScrollBar=mock.Mock(return_value=horizontal),
        verticalScrollBar=mock.Mock(return_value=vertical),
    )

    assert scroll_view_by_for(canvas, 3, -5) is True

    canvas.horizontalScrollBar.assert_called_once_with()
    canvas.verticalScrollBar.assert_called_once_with()
    assert horizontal.updated_value == 13
    assert vertical.updated_value == 15


def test_scroll_view_by_for_ignores_zero_delta() -> None:
    canvas = SimpleNamespace()

    assert scroll_view_by_for(canvas, 0, 0) is False
