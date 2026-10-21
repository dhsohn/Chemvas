"""Reviewed export must keep the live scene's observable stacking after Undo."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter

from chemvas.bootstrap.main_window import build_main_window
from chemvas.domain.document import Atom, Bond
from chemvas.features.export.cdxml_label_bindings import parse_cdxml_label_bindings
from chemvas.ui.export.figure_export_service import FigureExportService
from chemvas.ui.window import main_window_document_action_service as actions
from chemvas.ui.window.main_window_document_dialogs import FigureExportOptions
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.document_file_helpers import read_payload, write_payload_text
from tests.test_cdxml_export import _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")
OPTIONS = dict(
    dpi=300,
    background="white",
    sizing="custom",
    target_width_mm=170,
    max_height_mm=None,
    min_font_pt=None,
)


@pytest.fixture
def crossing(tmp_path):
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    canvas.services.canvas_document_session_service.apply_state(
        _simple_state(
            atoms={
                0: Atom("C", -40, -40),
                1: Atom("C", 40, 40),
                2: Atom("C", -40, 40),
                3: Atom("C", 40, -40),
                4: Atom("Ar", 120, 120),
                5: Atom("C", 100, 120),
            },
            bonds=[
                Bond(0, 1, color="#ff0000"),
                Bond(2, 3, color="#0000ff"),
                Bond(1, 2),
                Bond(5, 4),
            ],
        )
    )
    service = actions.MainWindowDocumentActionService()
    source = tmp_path / "crossing.cdxml"
    assert service.save_canvas_to_path(window, str(source), message_box=Mock())
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    sidecar = tmp_path / "meanings.json"
    write_payload_text(
        sidecar,
        json.dumps(
            dict(
                format="chemvas-cdxml-label-bindings",
                version=1,
                source_sha256=digest,
                bindings=[dict(atom_id=4, expected_label="Ar", meaning="generic_aryl")],
            )
        ),
    )
    binding = parse_cdxml_label_bindings(
        read_payload(sidecar.read_text()),
        source_sha256=digest,
        sidecar_sha256=hashlib.sha256(sidecar.read_bytes()).hexdigest(),
    )
    canvas.services.scene_transform_controller.apply_bond_style(0, "double", 2)
    canvas.services.history_service.undo()
    assert not window.services.canvas_document_service.is_dirty(canvas)
    yield window, canvas, service, source, sidecar, binding
    assert source.read_bytes() == source_bytes
    window.services.canvas_document_service.mark_clean(canvas)
    window.close()


def _pixel(scene):
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 100, 100), QRectF(-5, -5, 10, 10))
    painter.end()
    return image.pixelColor(50, 50).name()


def _gui_export(fixture, monkeypatch, output, scope):
    window, _, service, _, sidecar, _ = fixture
    options = FigureExportOptions(
        fmt="cdxml",
        scope=scope,
        sizing="custom",
        dpi=300,
        background="white",
        target_width_mm=170,
        cdxml_label_bindings_path=str(sidecar),
    )
    monkeypatch.setattr(actions, "prompt_export_options", lambda _: options)
    dialog, messages = Mock(), Mock()
    dialog.getSaveFileName.return_value = str(output), ""
    service.export_figure(window, file_dialog=dialog, message_box=messages)
    return messages


@pytest.mark.parametrize("scope", ["sheet", "selection"])
@pytest.mark.parametrize("different_z", [False, True])
def test_reviewed_gui_preserves_undo_crossing_pixel_and_native_z(
    crossing, tmp_path, monkeypatch, scope, different_z
):
    window, canvas, _, _, _, binding = crossing
    red = canvas.runtime_state.bond_graphics_state.bond_items[0][0]
    if different_z:
        red.setZValue(1.5)
    assert _pixel(canvas.scene()) == "#ff0000"
    selection = None
    if scope == "selection":
        canvas.scene().clearSelection()
        for items in canvas.runtime_state.bond_graphics_state.bond_items.values():
            for item in items:
                item.setSelected(True)
        atoms = canvas.runtime_state.atom_graphics_state
        for item in [*atoms.atom_items.values(), *atoms.atom_dots.values()]:
            item.setSelected(True)
        selection = canvas.scene().selectedItems()
    direct = tmp_path / "direct.cdxml"
    FigureExportService(canvas.render_context).export_figure(
        str(direct),
        fmt="cdxml",
        scope=scope,
        selection=selection,
        label_bindings=binding,
        **OPTIONS,
    )
    original_export = FigureExportService.export_figure
    detached_pixels = []

    def observe(service, *args, **kwargs):
        detached_pixels.append(_pixel(service.context.scene))
        return original_export(service, *args, **kwargs)

    monkeypatch.setattr(FigureExportService, "export_figure", observe)
    output = tmp_path / "reviewed.cdxml"
    _gui_export(crossing, monkeypatch, output, scope).warning.assert_not_called()
    assert detached_pixels == ["#ff0000"]
    live = ET.fromstring(direct.read_bytes())
    reviewed = ET.fromstring(output.read_bytes())
    assert [b.attrib for b in live.findall(".//b")] == [
        b.attrib for b in reviewed.findall(".//b")
    ]
    assert output.read_bytes() == direct.read_bytes()
    assert not window.services.canvas_document_service.is_dirty(canvas)


def test_snapshot_keeps_captured_order_after_later_live_restack(crossing, tmp_path):
    window, canvas, service, _, sidecar, _ = crossing
    prepared = service._reviewed_cdxml_snapshot(window, str(sidecar), scope="sheet")
    before = tmp_path / "before.cdxml"
    prepared.export(str(before), **OPTIONS)
    blue = canvas.runtime_state.bond_graphics_state.bond_items[1][0]
    blue.setZValue(1.5)
    assert _pixel(canvas.scene()) == "#0000ff"
    after = tmp_path / "after.cdxml"
    prepared.export(str(after), **OPTIONS)
    assert before.read_bytes() == after.read_bytes()


def test_changed_parent_hierarchy_refuses_before_overwriting(
    crossing, tmp_path, monkeypatch
):
    _, canvas, _, _, _, _ = crossing
    items = canvas.runtime_state.bond_graphics_state.bond_items
    items[1][0].setParentItem(items[0][0])
    output = tmp_path / "existing.cdxml"
    output.write_bytes(b"keep existing output")
    messages = _gui_export(crossing, monkeypatch, output, "sheet")
    messages.warning.assert_called_once()
    assert "cannot reproduce" in messages.warning.call_args.args[2]
    assert output.read_bytes() == b"keep existing output"


def test_reviewed_snapshot_retains_fragment_overlap_refusal(
    crossing, tmp_path, monkeypatch
):
    window, canvas, service, source, sidecar, _ = crossing
    canvas.services.note_controller.create_text_note(QPointF(0, -8), "overlap")
    # Save this changed drawing and review its own exact bytes.
    revised = tmp_path / "overlap.cdxml"
    assert service.save_canvas_to_path(window, str(revised), message_box=Mock())
    payload = read_payload(sidecar.read_text())
    payload["source_sha256"] = hashlib.sha256(revised.read_bytes()).hexdigest()
    write_payload_text(sidecar, json.dumps(payload))
    output = tmp_path / "refused.cdxml"
    messages = _gui_export(crossing, monkeypatch, output, "sheet")
    messages.warning.assert_called_once()
    assert "interleave" in messages.warning.call_args.args[2]
    assert not output.exists()
