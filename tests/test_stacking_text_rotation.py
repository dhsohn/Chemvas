from io import BytesIO

import pytest
from PIL import Image
from PyQt6.QtGui import QImage

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, validate_image_state
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import export_scene
from chemvas.ui.canvas_document_state import (
    document_item_lists_for,
    snapshot_canvas_document_state,
)
from chemvas.ui.canvas_service_ports import (
    history_service_for_access,
    scene_transform_controller_for_access,
)
from chemvas.ui.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.selection_state import selection_for
from chemvas.ui.stacking_actions import stack_selection

pytestmark = pytest.mark.usefixtures("qt_application")


def source(*, note=False):
    buffer = BytesIO()
    Image.new("RGB", (80, 40), "#00ff00").save(buffer, format="PNG")
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
            "images": [{"source": "green.png", "x": 0, "y": 0}],
            "shapes": [
                {
                    "shape_kind": "rect",
                    "stroke_style": "solid",
                    "left": 0,
                    "top": 0,
                    "right": 80,
                    "bottom": 40,
                    "fill": "#ff0000",
                }
            ],
            "notes": [{"text": "Rotate this long text", "x": 100, "y": 0}]
            if note
            else [],
        },
        image_source_reader=lambda _: buffer.getvalue(),
    )


def test_shape_image_stacking_pixels_history_and_reopen(tmp_path):
    with offscreen_canvas(source(), command="stacking") as (canvas, _):
        items = document_item_lists_for(canvas)
        shape, image = items["shapes"][0], items["images"][0]
        before = snapshot_canvas_document_state(canvas)
        shape.setSelected(True)
        assert stack_selection(canvas, front=True)
        front = snapshot_canvas_document_state(canvas)
        assert shape.zValue() > image.zValue()
        output = tmp_path / "front.png"
        export_scene(canvas.scene(), str(output), fmt="png", margin=0, dpi=72)
        raster = QImage(str(output))
        assert (
            raster.pixelColor(raster.width() // 2, raster.height() // 2).name()
            == "#ff0000"
        )
        history = history_service_for_access(canvas)
        history.undo()
        assert snapshot_canvas_document_state(canvas) == before
        history.redo()
        assert snapshot_canvas_document_state(canvas) == front
        assert not stack_selection(canvas, front=True)
        assert stack_selection(canvas, front=False)
        assert shape.zValue() < image.zValue()
        export_scene(canvas.scene(), str(output), fmt="png", margin=0, dpi=72)
        raster = QImage(str(output))
        assert (
            raster.pixelColor(raster.width() // 2, raster.height() // 2).name()
            == "#00ff00"
        )
        image.setSelected(True)
        assert stack_selection(canvas, front=True)
        assert 3 < shape.zValue() < image.zValue() < 10
        saved = snapshot_canvas_document_state(canvas)
        payload = SceneClipboardController(canvas).selection_payload_for_clipboard()
        assert {s["kind"] for s in payload["scene_items"]} == {"shape", "image"}
        assert all("z" in s for s in payload["scene_items"])
        path = tmp_path / "stacking.chemvas"
        write_document(path, saved, CANVAS_FILE_VERSION)
    with offscreen_canvas(read_document(path).state, command="reopen") as (canvas, _):
        restored = document_item_lists_for(canvas)
        assert restored["shapes"][0].zValue() == saved["shapes"][0]["z"]
        assert restored["images"][0].zValue() == saved["images"][0]["z"]


def test_stacking_failed_history_is_atomic(monkeypatch):
    with offscreen_canvas(source(), command="stacking-failure") as (canvas, _):
        for kind in ("images", "shapes"):
            document_item_lists_for(canvas)[kind][0].setSelected(True)
        before = snapshot_canvas_document_state(canvas)
        history = history_service_for_access(canvas)
        monkeypatch.setattr(history, "push", lambda _: False)
        with pytest.raises(ValueError, match="History is disabled"):
            stack_selection(canvas, front=True)
        assert snapshot_canvas_document_state(canvas) == before


def test_text_rotation_visible_bounds_undo_clipboard_save_and_export(tmp_path):
    state = source(note=True)
    state["images"] = []
    state["shapes"] = []
    with offscreen_canvas(state, command="text-rotation") as (canvas, _):
        note = document_item_lists_for(canvas)["notes"][0]
        selection_for(canvas).select_note(note)
        before = snapshot_canvas_document_state(canvas)
        bounds = note.sceneBoundingRect()
        center = bounds.center()
        scene_transform_controller_for_access(canvas).rotate_selected_items(90)
        assert note.rotation() == 90
        rotated_bounds = note.sceneBoundingRect()
        assert rotated_bounds.width() == pytest.approx(bounds.height())
        assert rotated_bounds.height() == pytest.approx(bounds.width())
        assert rotated_bounds.center().x() == pytest.approx(center.x())
        assert rotated_bounds.center().y() == pytest.approx(center.y())
        rotated = snapshot_canvas_document_state(canvas)
        history = history_service_for_access(canvas)
        history.undo()
        assert snapshot_canvas_document_state(canvas) == before
        history.redo()
        assert snapshot_canvas_document_state(canvas) == rotated
        payload = SceneClipboardController(canvas).selection_payload_for_clipboard()
        assert payload["scene_items"][0]["rotation"] == 90
        path = tmp_path / "rotated.chemvas"
        write_document(path, rotated, CANVAS_FILE_VERSION)
        output = tmp_path / "rotated.png"
        export_scene(canvas.scene(), str(output), fmt="png", margin=0, dpi=72)
        raster = QImage(str(output))
        assert raster.height() > raster.width() * 2
    with offscreen_canvas(read_document(path).state, command="rotated-reopen") as (
        canvas,
        _,
    ):
        note = document_item_lists_for(canvas)["notes"][0]
        assert note.rotation() == 90
        assert note.sceneBoundingRect() == rotated_bounds
        output2 = tmp_path / "reopened.png"
        export_scene(canvas.scene(), str(output2), fmt="png", margin=0, dpi=72)
        assert QImage(str(output2)) == raster


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "2", -13, 11])
def test_image_depth_rejects_invalid_values(bad):
    state = source()["images"][0]
    with pytest.raises(ValueError):
        validate_image_state({**state, "z": bad})


@pytest.mark.parametrize(
    "field,bad", [("rotation", float("nan")), ("rotation", True), ("z", 11)]
)
def test_composition_rejects_invalid_transform(field, bad):
    spec = {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [],
        "bonds": [],
    }
    if field == "rotation":
        spec["notes"] = [{"text": "bad", "x": 0, "y": 0, field: bad}]
    else:
        spec["shapes"] = [
            {
                "shape_kind": "rect",
                "stroke_style": "solid",
                "left": 0,
                "top": 0,
                "right": 80,
                "bottom": 40,
                field: bad,
            }
        ]
    with pytest.raises(ValueError):
        compose_document_state(spec)


@pytest.mark.parametrize("horizontal", [True, False])
@pytest.mark.parametrize("angle", [30, 90, 210])
def test_rotated_note_flip_keeps_anchor_offset(horizontal, angle):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.annotations.state import note_state_dict, ts_bracket_rect_from_state
    from chemvas.ui.scene_flip_state import flip_scene_item_state

    state = source(note=True)
    state["notes"][0]["rotation"] = angle
    with offscreen_canvas(state, command="rotated-flip") as (canvas, _):
        note = document_item_lists_for(canvas)["notes"][0]
        before = note_state_dict(note)
        bounds = note.sceneBoundingRect()
        center = bounds.center() + QPointF(40, 30)

        def flip_point(point, pivot, horizontal):
            return (
                QPointF(2 * pivot.x() - point.x(), point.y())
                if horizontal
                else QPointF(point.x(), 2 * pivot.y() - point.y())
            )

        kwargs = dict(
            center=center,
            horizontal=horizontal,
            atoms={},
            transformed_atom_positions={},
            flip_point=flip_point,
            ts_bracket_rect_from_state=ts_bracket_rect_from_state,
        )
        after = flip_scene_item_state(note, before, **kwargs)
        note.setPos(after["x"], after["y"])
        assert note.sceneBoundingRect().center().x() == pytest.approx(
            flip_point(bounds.center(), center, horizontal).x()
        )
        assert note.sceneBoundingRect().center().y() == pytest.approx(
            flip_point(bounds.center(), center, horizontal).y()
        )
        again = flip_scene_item_state(note, after, **kwargs)
        assert again["x"] == pytest.approx(before["x"])
        assert again["y"] == pytest.approx(before["y"])
        assert again["rotation"] == angle
