from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.bond_preview_access import (
    add_bond_preview_items_for,
    clear_bond_preview_items_for,
)


def test_clear_bond_preview_items_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.bond_preview_access.clear_bond_preview_items_helper", return_value=[]) as clear_helper:
        assert clear_bond_preview_items_for(canvas, ["old"]) == []

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_add_bond_preview_items_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.bond_preview_access.add_bond_preview_items_helper", return_value=["added"]) as add_helper:
        assert add_bond_preview_items_for(canvas, ["new"]) == ["added"]

    canvas.scene.assert_called_once_with()
    add_helper.assert_called_once_with(scene, ["new"])
