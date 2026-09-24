from __future__ import annotations

import math
import os
from unittest.mock import Mock, patch

import pytest

from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.ui.canvas.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas.canvas_group_state import register_group_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene.scene_clipboard_copy_service import (
    copy_selection_to_clipboard_for_canvas,
)
from chemvas.ui.scene.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.selection.selection_queries import (
    selected_ids_for,
    selection_items_for_copy_for,
)
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module", autouse=True)
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.close()
    view.deleteLater()
    app.processEvents()


def _copy(canvas):
    clipboard = Mock()
    assert copy_selection_to_clipboard_for_canvas(
        canvas,
        clipboard=clipboard,
        payload_provider=SceneClipboardController(
            canvas
        ).selection_payload_for_clipboard,
    )
    return clipboard.setMimeData.call_args.args[0]


def _image_bytes(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return image.constBits().asstring(image.sizeInBytes())


def _ring(canvas):
    points = [
        (40 * math.cos(i * math.pi / 3), 40 * math.sin(i * math.pi / 3))
        for i in range(6)
    ]
    ids = [
        canvas.services.canvas_atom_mutation_service.add_atom("C", x, y)
        for x, y in points
    ]
    for i in range(6):
        bond_id = add_bond_for(canvas, ids[i], ids[(i + 1) % 6], 1 + i % 2)
        canvas.bond_renderer.add_bond_graphics(bond_id)
    fill = canvas.services.scene_item_controller.create_scene_item_from_state(
        {
            "points": points,
            "atom_ids": ids,
            "color": "#aaccff",
            "alpha": 0.3,
            "kind": "ring",
        }
    )
    return ids, fill


def test_atom_only_selection_copies_induced_bonds_and_complete_ring(canvas, tmp_path):
    ids, fill = _ring(canvas)
    # A neighbouring branch and its annotation must not expand this to a component.
    extra = canvas.services.canvas_atom_mutation_service.add_atom("O", 85, 0)
    external_bond = add_bond_for(canvas, ids[0], extra)
    canvas.bond_renderer.add_bond_graphics(external_bond)
    external_mark = add_mark_for_atom_for(canvas, extra, QPointF(95, -10), kind="minus")
    for atom_id in ids:
        canvas.runtime_state.atom_graphics_state.atom_dots[atom_id].setSelected(True)
    original = snapshot_canvas_document_state(canvas)
    selected = set(canvas.scene().selectedItems())
    items = selection_items_for_copy_for(canvas)
    assert fill in items
    assert all(
        item in items
        for bond_id in range(6)
        for item in canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, [])
    )
    assert external_mark not in items
    assert all(
        item not in items
        for item in canvas.runtime_state.bond_graphics_state.bond_items.get(
            external_bond, []
        )
    )
    mime = _copy(canvas)
    image = mime.imageData()
    assert any(_image_bytes(image)[3::4])
    assert mime.hasFormat("image/svg+xml") and mime.hasFormat("application/pdf")
    payload = SceneClipboardController(canvas).selection_payload_for_clipboard()
    assert [len(payload[key]) for key in ("atoms", "bonds", "rings", "marks")] == [
        6,
        6,
        1,
        0,
    ]
    service = canvas.services.canvas_document_session_service
    for fmt in ("svg", "png", "pdf"):
        output = tmp_path / f"selection.{fmt}"
        service.export_figure(str(output), fmt=fmt, scope="selection")
        assert output.stat().st_size > 100
    assert snapshot_canvas_document_state(canvas) == original
    assert set(canvas.scene().selectedItems()) == selected


def test_bond_selection_copies_bound_charge_but_mark_only_stays_independent(canvas):
    carbon = canvas.services.canvas_atom_mutation_service.add_atom("C", 0, 0)
    oxygen = canvas.services.canvas_atom_mutation_service.add_atom("O", 40, 0)
    bond = add_bond_for(canvas, carbon, oxygen)
    canvas.bond_renderer.add_bond_graphics(bond)
    mark = add_mark_for_atom_for(canvas, oxygen, QPointF(52, -12), kind="minus")
    canvas.runtime_state.bond_graphics_state.bond_items.get(bond, [])[0].setSelected(
        True
    )
    assert mark in selection_items_for_copy_for(canvas)
    mime = _copy(canvas)
    marked = mime.imageData()
    mark.setVisible(False)
    unmarked = _copy(canvas).imageData()
    mark.setVisible(True)
    assert _image_bytes(marked) != _image_bytes(unmarked)
    controller = SceneClipboardController(canvas)
    assert len(controller.selection_payload_for_clipboard()["marks"]) == 1
    canvas.scene().clearSelection()
    mark.setSelected(True)
    assert selection_items_for_copy_for(canvas) == [mark]
    payload = controller.selection_payload_for_clipboard()
    assert not payload["atoms"] and not payload["bonds"]
    assert payload["marks"][0]["atom_id"] is None


def test_note_copy_matches_deselected_render_without_changing_note(canvas):
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"text": "Scheme 1", "x": 10, "y": 10, "kind": "note"}
    )
    note.setSelected(True)
    text, html = note.toPlainText(), note.toHtml()
    selected_image = _copy(canvas).imageData()
    note.setSelected(False)
    canvas.runtime_state.selection_state.selected_notes = [note]
    unselected_image = _copy(canvas).imageData()
    assert selected_image.size() == unselected_image.size()
    assert _image_bytes(selected_image) == _image_bytes(unselected_image)
    assert (note.toPlainText(), note.toHtml()) == (text, html)
    assert not note._outline_mode


def test_qt_rubber_band_note_copy_omits_selection_frame(canvas, app):
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"text": "Scheme 1", "x": 10, "y": 10, "kind": "note"}
    )
    canvas.services.tool_mode_controller.set_tool("select")
    canvas.resize(700, 500)
    canvas.show()
    canvas.centerOn(note.sceneBoundingRect().center())
    app.processEvents()
    rect = note.sceneBoundingRect().adjusted(-15, -15, 15, 15)
    start, end = (
        canvas.mapFromScene(rect.topLeft()),
        canvas.mapFromScene(rect.bottomRight()),
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=10)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert note.isSelected()
    selected_image = _copy(canvas).imageData()
    note.setSelected(False)
    canvas.runtime_state.selection_state.selected_notes = [note]
    assert _image_bytes(selected_image) == _image_bytes(_copy(canvas).imageData())


def test_copy_failure_restores_visibility_and_outline_and_keeps_clipboard(canvas):
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"text": "Scheme 1", "x": 10, "y": 10, "kind": "note"}
    )
    other = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"text": "not selected", "x": 10, "y": 100, "kind": "note"}
    )
    note.setSelected(True)
    clipboard = Mock()
    state = snapshot_canvas_document_state(canvas)
    with patch(
        "chemvas.ui.scene.scene_clipboard_copy_service.build_clipboard_mime_data",
        side_effect=ValueError("renderer failed"),
    ):
        with pytest.raises(ValueError, match="renderer failed"):
            copy_selection_to_clipboard_for_canvas(
                canvas,
                clipboard=clipboard,
                payload_provider=SceneClipboardController(
                    canvas
                ).selection_payload_for_clipboard,
            )
    assert note.isSelected() and other.isVisible()
    assert not note._outline_mode
    assert snapshot_canvas_document_state(canvas) == state
    clipboard.setMimeData.assert_not_called()


def test_partial_ring_does_not_copy_whole_fill_or_unselected_atom(canvas):
    ids, fill = _ring(canvas)
    for atom_id in ids[:3]:
        canvas.runtime_state.atom_graphics_state.atom_dots[atom_id].setSelected(True)
    items = selection_items_for_copy_for(canvas)
    assert fill not in items
    assert all(
        canvas.runtime_state.atom_graphics_state.atom_dots[atom_id] not in items
        for atom_id in ids[3:]
    )
    payload = SceneClipboardController(canvas).selection_payload_for_clipboard()
    assert [len(payload[key]) for key in ("atoms", "bonds", "rings")] == [3, 2, 0]
    assert all(
        item in items
        for bond_id in (0, 1)
        for item in canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, [])
    )


def test_copy_preserves_group_identity_and_explicit_decorations(canvas):
    ids, _ = _ring(canvas)
    note = canvas.services.scene_item_controller.create_scene_item_from_state(
        {"text": "Compound A", "x": -20, "y": 60, "kind": "note"}
    )
    for atom_id in ids:
        canvas.runtime_state.atom_graphics_state.atom_dots[atom_id].setSelected(True)
    note.setSelected(True)
    group_id = register_group_for(
        canvas, set(ids), [require_scene_record_id(item) for item in [note]]
    )
    group = canvas.runtime_state.group_state.groups[group_id]
    controller = SceneClipboardController(canvas)
    payload = controller.selection_payload_for_clipboard()
    original = snapshot_canvas_document_state(canvas)
    assert len(payload["groups"]) == 1 and len(payload["scene_items"]) == 1
    assert note in selection_items_for_copy_for(canvas)
    _copy(canvas)
    assert canvas.runtime_state.group_state.groups[group_id] is group
    assert group.item_ids == [require_scene_record_id(note)] and group.atom_ids == set(
        ids
    )
    assert controller.selection_payload_for_clipboard() == payload
    assert snapshot_canvas_document_state(canvas) == original


def test_qt_atom_click_copy_paste_and_undo_keep_images_and_payload_consistent(
    canvas, app
):
    ids, _ = _ring(canvas)
    canvas.services.tool_mode_controller.set_tool("select")
    canvas.resize(700, 500)
    canvas.show()
    canvas.centerOn(0, 0)
    app.processEvents()
    before = snapshot_canvas_document_state(canvas)
    for atom_id in ids:
        point = (
            canvas.runtime_state.atom_graphics_state.atom_dots[atom_id]
            .sceneBoundingRect()
            .center()
        )
        QTest.mouseClick(
            canvas.viewport(),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            canvas.mapFromScene(point),
        )
    assert selected_ids_for(canvas) == (set(ids), set())
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    mime = app.clipboard().mimeData()
    assert mime.hasFormat("image/svg+xml") and mime.hasFormat("application/pdf")
    assert any(_image_bytes(mime.imageData())[3::4])
    assert snapshot_canvas_document_state(canvas) == before
    target = build_canvas_view()
    try:
        target.show()
        app.processEvents()
        QTest.keyClick(
            target.viewport(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier
        )
        state = snapshot_canvas_document_state(target)
        assert len(state["model"]["atoms"]) == len(state["model"]["bonds"]) == 6
        assert len(state["ring_fills"]) == 1
        history = target.services.history_service
        history.undo()
        assert not snapshot_canvas_document_state(target)["model"]["atoms"]
        history.redo()
        assert snapshot_canvas_document_state(target) == state
    finally:
        target.close()
        target.deleteLater()
        app.clipboard().clear()
        app.processEvents()
