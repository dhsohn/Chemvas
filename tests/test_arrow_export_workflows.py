"""Native arrow-label fitting keeps editable state and shared output consistent."""

import json
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage

from chemvas.bootstrap import document_render
from chemvas.core.document_io import read_document
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_history_state import history_state_for
from chemvas.ui.scene_clipboard_copy_service import (
    copy_selection_to_clipboard_for_canvas,
)
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


def _labelled_arrow(canvas):
    arrow = add_arrow_for(canvas, QPointF(-40, 0), QPointF(40, 0), "arrow")
    before = snapshot_canvas_document_state(canvas)
    assert canvas.services.scene_decoration.scene_decoration_service.set_arrow_labels(
        arrow, {"above": "K_{2}CO_{3}\nDMSO, rt", "below": "\n68%, 96% ee\n"}
    )
    return arrow, before


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_arrow_fit_export_clipboard_and_history(canvas, app, tmp_path, fmt):
    arrow, before = _labelled_arrow(canvas)
    documents = canvas.services.document.canvas_document_session_service
    after = snapshot_canvas_document_state(canvas)
    geometry = [
        (child, child.pos(), child.boundingRect()) for child in arrow.childItems()
    ]
    history = history_state_for(canvas)
    stacks = list(history.history), list(history.redo_stack)
    plan = documents.plan_figure_export(sizing="col1")
    output = tmp_path / f"arrow.{fmt}"
    documents.export_figure(str(output), fmt=fmt, sizing="col1", dpi=300)
    assert output.stat().st_size > 0
    if fmt == "png":
        image = QImage(str(output))
        assert image.width() == round(84 / 25.4 * 300)
        painted_rows = [
            y
            for y in range(image.height())
            if any(image.pixelColor(x, y).alpha() for x in range(image.width()))
        ]
        pad = max(2, canvas.renderer.style.bond_line_width * 2)
        expected = pad / plan.source_h * image.height()
        assert painted_rows[0] == pytest.approx(expected, abs=2)
        assert image.height() - 1 - painted_rows[-1] == pytest.approx(expected, abs=2)
    elif fmt == "svg":
        root = ET.fromstring(output.read_bytes())
        assert list(map(float, root.attrib["viewBox"].split())) == pytest.approx(
            [0, 0, plan.out_w_pt, plan.out_h_pt], abs=0.001
        )
    else:
        assert output.read_bytes().startswith(b"%PDF-")
    assert snapshot_canvas_document_state(canvas) == after
    assert (history.history, history.redo_stack) == stacks
    assert [
        (item, item.pos(), item.boundingRect()) for item, _, _ in geometry
    ] == geometry

    select_all_scene_items_for(canvas)
    selected = set(canvas.scene().selectedItems())
    clipboard = Mock()
    assert copy_selection_to_clipboard_for_canvas(
        canvas,
        clipboard=clipboard,
        payload_provider=canvas.services.scene_operations.scene_clipboard_controller.selection_payload_for_clipboard,
    )
    mime = clipboard.setMimeData.call_args.args[0]
    assert mime.hasImage() and mime.hasFormat("application/pdf")
    clipboard_svg = ET.fromstring(bytes(mime.data("image/svg+xml")))
    assert list(map(float, clipboard_svg.attrib["viewBox"].split())) == pytest.approx(
        [0, 0, plan.source_w, plan.source_h], abs=0.001
    )
    assert snapshot_canvas_document_state(canvas) == after
    assert set(canvas.scene().selectedItems()) == selected
    assert (history.history, history.redo_stack) == stacks
    canvas.services.history_service.undo()
    assert snapshot_canvas_document_state(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_document_state(canvas) == after


def test_saved_arrow_has_same_gui_and_cli_fit(canvas, app, tmp_path, capsys):
    _labelled_arrow(canvas)
    documents = canvas.services.document.canvas_document_session_service
    before = snapshot_canvas_document_state(canvas)
    source = tmp_path / "arrow.chemvas"
    documents.save_to_file(str(source))
    source_bytes = source.read_bytes()
    gui_png, cli_png = tmp_path / "gui.png", tmp_path / "cli.png"
    documents.export_figure(str(gui_png), fmt="png", sizing="col1", dpi=300)
    assert (
        document_render.run(
            [
                "render-document",
                str(source),
                "--output",
                str(cli_png),
                "--width-mm",
                "84",
                "--dpi",
                "300",
                "--background",
                "transparent",
            ]
        )
        == 0
    )
    assert (
        json.loads(capsys.readouterr().out)["format"]
        == "chemvas-document-render-report"
    )
    assert QImage(str(gui_png)) == QImage(str(cli_png))
    assert source.read_bytes() == source_bytes
    assert read_document(source).state == json.loads(json.dumps(before))
    documents.apply_state(read_document(source).state)
    assert snapshot_canvas_document_state(canvas) == before
