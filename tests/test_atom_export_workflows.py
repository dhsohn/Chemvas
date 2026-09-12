"""Real-canvas atom editing, fitted output and clipboard bounds regression."""

import json
import math
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest

from chemvas.bootstrap import document_render
from chemvas.core.document_io import read_document
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_history_state import history_state_for
from chemvas.ui.input_view_access import set_zoom_for
from chemvas.ui.scene_clipboard_copy_service import (
    copy_selection_to_clipboard_for_canvas,
)
from chemvas.ui.select_all_access import select_all_scene_items_for
from tests.test_native_geometry_backlog import app as app
from tests.test_native_geometry_backlog import canvas as canvas


def _draw_ring(canvas, app, monkeypatch):
    canvas.services.input.tool_mode_controller.set_tool("benzene")
    set_zoom_for(canvas, 4)
    canvas.centerOn(0, 0)
    app.processEvents()
    QTest.mouseClick(
        canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF())
    )
    app.processEvents()
    assert len(canvas.model.atoms) == 6
    atom_id, atom = min(canvas.model.atoms.items(), key=lambda entry: entry[1].y)
    canvas.services.input.tool_mode_controller.set_tool("select")
    canvas.setFocus()
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(atom.x, atom.y)))
    app.processEvents()
    before = snapshot_canvas_document_state(canvas)
    # Wayland cannot warp QCursor; inject only its location, retaining the
    # actual key event and normal hover/hit-test/label edit route.
    global_pos = canvas.viewport().mapToGlobal(
        canvas.mapFromScene(QPointF(atom.x, atom.y))
    )
    with monkeypatch.context() as cursor:
        cursor.setattr("chemvas.ui.hover.QCursor.pos", lambda: global_pos)
        QTest.keyClick(canvas, Qt.Key.Key_O)
    app.processEvents()
    assert canvas.model.atoms[atom_id].element == "O"
    return atom_id, before


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_live_atom_edit_export_copy_and_undo_preserve_document(
    canvas, app, tmp_path, monkeypatch, fmt
):
    atom_id, before = _draw_ring(canvas, app, monkeypatch)
    documents = canvas.services.document.canvas_document_session_service
    state = history_state_for(canvas)
    after = snapshot_canvas_document_state(canvas)
    stacks = list(state.history), list(state.redo_stack)
    plan = documents.plan_figure_export(sizing="col1")
    glyph_top = (
        atom_items_for(canvas)[atom_id]
        .mapToScene(atom_items_for(canvas)[atom_id].glyph_path())
        .boundingRect()
        .top()
    )
    pad = max(2, canvas.renderer.style.bond_line_width * 2)
    assert math.isclose(plan.source_y, glyph_top - pad, abs_tol=1e-9)
    output = tmp_path / f"fitted.{fmt}"
    documents.export_figure(str(output), fmt=fmt, sizing="col1", dpi=300)
    assert output.stat().st_size > 0
    if fmt == "png":
        image = QImage(str(output))
        assert image.width() == round(84 / 25.4 * 300)
        first_ink = next(
            y
            for y in range(image.height())
            if any(image.pixelColor(x, y).alpha() for x in range(image.width()))
        )
        expected_pad = pad / plan.source_h * image.height()
        assert abs(first_ink - expected_pad) <= 2
    elif fmt == "svg":
        root = ET.fromstring(output.read_bytes())
        assert list(map(float, root.attrib["viewBox"].split())) == pytest.approx(
            [0, 0, plan.out_w_pt, plan.out_h_pt], abs=0.001
        )
    else:
        assert output.read_bytes().startswith(b"%PDF-")
    assert snapshot_canvas_document_state(canvas) == after
    assert (state.history, state.redo_stack) == stacks

    select_all_scene_items_for(canvas)
    selected = set(canvas.scene().selectedItems())
    clipboard = Mock()
    assert copy_selection_to_clipboard_for_canvas(
        canvas,
        clipboard=clipboard,
        payload_provider=canvas.services.scene_operations.scene_clipboard_controller.selection_payload_for_clipboard,
    )
    mime = clipboard.setMimeData.call_args.args[0]
    assert mime.hasImage()
    assert mime.hasFormat("image/svg+xml")
    assert mime.hasFormat("application/pdf")
    clipboard_svg = ET.fromstring(bytes(mime.data("image/svg+xml")))
    assert list(map(float, clipboard_svg.attrib["viewBox"].split())) == pytest.approx(
        [0, 0, plan.source_w, plan.source_h], abs=0.001
    )
    assert snapshot_canvas_document_state(canvas) == after
    assert set(canvas.scene().selectedItems()) == selected
    assert (state.history, state.redo_stack) == stacks
    canvas.services.history_service.undo()
    assert snapshot_canvas_document_state(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_document_state(canvas) == after


def test_live_saved_oxygen_ring_uses_same_cli_fit(
    canvas, app, tmp_path, capsys, monkeypatch
):
    _draw_ring(canvas, app, monkeypatch)
    documents = canvas.services.document.canvas_document_session_service
    before = snapshot_canvas_document_state(canvas)
    source = tmp_path / "ring.chemvas"
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
    report = json.loads(capsys.readouterr().out)
    assert report["format"] == "chemvas-document-render-report"
    assert QImage(str(gui_png)) == QImage(str(cli_png))
    assert source.read_bytes() == source_bytes
    assert read_document(source).state == json.loads(json.dumps(before))
    assert snapshot_canvas_document_state(canvas) == before
