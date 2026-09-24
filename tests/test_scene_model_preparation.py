"""Whole-model ingress retains native label normalization, not the renderer."""

from __future__ import annotations

import copy
from dataclasses import asdict

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from chemvas.bootstrap.document_cli_shared import (
    offscreen_canvas,
)
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.export.export_render_service import resolve_export_plan
from chemvas.ui.export.export_scope import exported_scene
from chemvas.ui.export.export_vector import render_svg_bytes

pytestmark = pytest.mark.usefixtures("qt_application")


def _state(label: str, explicit: bool) -> dict:
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": label, "x": 0, "y": 0},
                {"id": 1, "element": "C", "x": 40, "y": 0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
        }
    )
    # Native validation accepts surrounding whitespace although composition
    # normalizes it. Exercise an actual current-format native input.
    state["model"]["atoms"][0].update(element=f" {label} ", explicit_label=explicit)
    build_document_payload(state, CANVAS_FILE_VERSION)
    return state


def _paint(scene):
    items, plan = resolve_export_plan(scene, margin=3)
    svg = render_svg_bytes(scene, items, plan, "transparent", "native-label-test")
    image = QImage(600, 240, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    with exported_scene(scene, items):
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(
            painter,
            QRectF(0, 0, 600, 240),
            QRectF(plan.source_x, plan.source_y, plan.source_w, plan.source_h),
        )
        painter.end()
    return asdict(plan), svg, image.constBits().asstring(image.sizeInBytes())


@pytest.mark.parametrize("label", ["N", "C", "NH2"])
@pytest.mark.parametrize("explicit", [False, True])
def test_native_open_normalizes_label_before_drawing_without_mutating_input(
    label, explicit
):
    state = _state(label, explicit)
    original = copy.deepcopy(state)
    expected = copy.deepcopy(state)
    expected["model"]["atoms"][0].update(element=label, explicit_label=False)
    with offscreen_canvas(expected, command="canonical-label-test") as (
        canvas,
        session,
    ):
        expected_snapshot = session.snapshot_state()
        expected_paint = _paint(canvas.scene())
    with offscreen_canvas(state, command="native-label-test") as (canvas, session):
        assert session.snapshot_state() == expected_snapshot
        assert _paint(canvas.scene()) == expected_paint
    assert state == original


@pytest.mark.parametrize("label", ["N", "C", "NH2"])
@pytest.mark.parametrize("explicit", [False, True])
def test_headless_materialization_matches_native_label_preparation(label, explicit):
    from chemvas.bootstrap.document_cli_shared import offscreen_document_scene

    state = _state(label, explicit)
    original = copy.deepcopy(state)
    expected = copy.deepcopy(state)
    expected["model"]["atoms"][0].update(element=label, explicit_label=False)
    with offscreen_canvas(expected, command="canonical-label-test") as (canvas, _):
        expected_paint = _paint(canvas.scene())
    with offscreen_document_scene(state, command="headless-label-test") as context:
        assert context.model.atoms[0].element == label
        assert context.model.atoms[0].explicit_label is False
        assert _paint(context.scene) == expected_paint
    assert state == original
