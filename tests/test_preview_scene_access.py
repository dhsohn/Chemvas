from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from ui.preview_scene_access import (
    apply_smiles_preview_geometry_for,
    apply_template_preview_geometry_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)


def test_clear_smiles_preview_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.preview_scene_access.clear_smiles_preview_helper", return_value=([], {}, {})) as clear_helper:
        assert clear_smiles_preview_for(canvas, ["old"]) == ([], {}, {})

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_apply_smiles_preview_geometry_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    result = (["items"], {0: ["bond"]}, {0: "atom"})

    with mock.patch("ui.preview_scene_access.apply_smiles_preview_geometry_helper", return_value=result) as apply_helper:
        assert (
            apply_smiles_preview_geometry_for(
                canvas,
                "geometry",
                base_pen="pen",
                existing_items=["old"],
                existing_bond_items={0: ["old-bond"]},
                existing_atom_items={0: "old-atom"},
                action="update",
            )
            == result
        )

    canvas.scene.assert_called_once_with()
    apply_helper.assert_called_once_with(
        scene,
        "geometry",
        base_pen="pen",
        existing_items=["old"],
        existing_bond_items={0: ["old-bond"]},
        existing_atom_items={0: "old-atom"},
        action="update",
    )


def test_clear_template_preview_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))

    with mock.patch("ui.preview_scene_access.clear_template_preview_helper", return_value=([], [], [])) as clear_helper:
        assert clear_template_preview_for(canvas, ["old"]) == ([], [], [])

    canvas.scene.assert_called_once_with()
    clear_helper.assert_called_once_with(scene, ["old"])


def test_apply_template_preview_geometry_for_delegates_with_canvas_scene() -> None:
    scene = object()
    canvas = SimpleNamespace(scene=mock.Mock(return_value=scene))
    result = (["items"], ["line"], ["dot"])

    with mock.patch("ui.preview_scene_access.apply_template_preview_geometry_helper", return_value=result) as apply_helper:
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
