from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from chemvas.ui.preview_scene_access import (
    add_smiles_preview_item_for,
    apply_template_preview_geometry_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)


def test_clear_smiles_preview_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch(
        "chemvas.ui.preview_scene_access.clear_smiles_preview_helper",
        return_value=[],
    ) as clear_helper:
        assert clear_smiles_preview_for(canvas, ["old"]) == []

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_add_smiles_preview_item_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch(
        "chemvas.ui.preview_scene_access.add_smiles_preview_item_helper",
        return_value="item",
    ) as add_helper:
        assert add_smiles_preview_item_for(canvas, "picture") == "item"

    canvas.scene.assert_called_once_with()
    add_helper.assert_called_once_with(scene, "picture")


def test_clear_template_preview_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch(
        "chemvas.ui.preview_scene_access.clear_template_preview_helper",
        return_value=([], [], []),
    ) as clear_helper:
        assert clear_template_preview_for(canvas, ["old"]) == ([], [], [])

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_apply_template_preview_geometry_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    result = (["items"], ["line"], ["dot"])

    with mock.patch(
        "chemvas.ui.preview_scene_access.apply_template_preview_geometry_helper",
        return_value=result,
    ) as apply_helper:
        assert (
            apply_template_preview_geometry_for(
                canvas,
                "geometry",
                base_pen="pen",
                existing_items=["old"],
                existing_lines=["old-line"],
                existing_dots=["old-dot"],
                action="rebuild",
            )
            == result
        )

    canvas.scene.assert_called_once_with()
    apply_helper.assert_called_once_with(
        scene,
        "geometry",
        base_pen="pen",
        existing_items=["old"],
        existing_lines=["old-line"],
        existing_dots=["old-dot"],
        action="rebuild",
    )
