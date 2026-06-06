from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.hover_scene_access import (
    add_hover_preview_items_to_scene_for,
    add_hover_scene_item_for,
    clear_hover_items_for,
)


class _Scene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


def test_clear_hover_items_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.hover_scene_access.clear_hover_items_helper", return_value=[]) as clear_helper:
        assert clear_hover_items_for(canvas, ["old"]) == []

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_add_hover_preview_items_to_scene_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.hover_scene_access.add_hover_preview_items_helper", return_value=["added"]) as add_helper:
        assert add_hover_preview_items_to_scene_for(canvas, ["new"]) == ["added"]

    canvas.scene.assert_called_once_with()
    add_helper.assert_called_once_with(scene, ["new"])


def test_add_hover_scene_item_for_adds_item_to_canvas_scene() -> None:
    scene = _Scene()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    item = object()

    assert add_hover_scene_item_for(canvas, item) is item

    canvas.scene.assert_called_once_with()
    assert scene.items == [item]
