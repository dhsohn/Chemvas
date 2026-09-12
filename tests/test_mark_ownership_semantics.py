import json
import os
from copy import deepcopy
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document, write_document
from chemvas.core.molfile import parse_molfile, write_molfile
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import CANVAS_FILE_VERSION, serialize_model_state
from chemvas.features.insertion import model_with_atom_annotations
from chemvas.ui.canvas_format_access import clipboard_selection_mime_for
from chemvas.ui.canvas_scene_items_state import mark_items_for
from chemvas.ui.canvas_service_ports import mark_scene_service_for_access
from chemvas.ui.canvas_window_access import (
    restore_canvas_state_for,
    snapshot_canvas_state_for,
)
from chemvas.ui.mark_item_access import apply_mark_color_for, mark_center_for
from chemvas.ui.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene_clipboard_copy_service import (
    copy_selection_to_clipboard_for_canvas,
)
from chemvas.ui.scene_decoration_access import add_mark_for_atom_for
from chemvas.ui.select_all_access import select_all_scene_items_for
from chemvas.ui.selection_outline_state import selection_outlines_for
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.structure_mutation_access import add_atom_for
from chemvas.ui.structure_payload_access import build_structure_payload_for
from tests.canvas_factory import build_canvas_view

# Independent totals: N already carries one radical; O already carries -1.
# The moved mark contributes only to its explicitly chosen owner.
ELECTRONIC_STATES = [
    (
        "plus",
        {0: {"formal_charge": 1, "radical_electrons": 1}, 1: {"formal_charge": -1}},
        {0: {"radical_electrons": 1}},
    ),
    (
        "circled_plus",
        {0: {"formal_charge": 1, "radical_electrons": 1}, 1: {"formal_charge": -1}},
        {0: {"radical_electrons": 1}},
    ),
    (
        "minus",
        {0: {"formal_charge": -1, "radical_electrons": 1}, 1: {"formal_charge": -1}},
        {0: {"radical_electrons": 1}, 1: {"formal_charge": -2}},
    ),
    (
        "circled_minus",
        {0: {"formal_charge": -1, "radical_electrons": 1}, 1: {"formal_charge": -1}},
        {0: {"radical_electrons": 1}, 1: {"formal_charge": -2}},
    ),
    (
        "radical",
        {0: {"radical_electrons": 2}, 1: {"formal_charge": -1}},
        {0: {"radical_electrons": 1}, 1: {"formal_charge": -1, "radical_electrons": 1}},
    ),
]


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas_factory(app):
    canvases = []

    def create():
        canvas = build_canvas_view()
        canvases.append(canvas)
        return canvas

    yield create
    for canvas in reversed(canvases):
        canvas.services.document.canvas_scene_reset_service.clear_scene()
        canvas.close()
        canvas.deleteLater()
    app.processEvents()


def _drawing(canvas_factory, kind, *, target_owner=False):
    canvas = canvas_factory()
    old = add_atom_for(canvas, "N", -40.0, 0.0)
    new = add_atom_for(canvas, "O", 50.0, 0.0)
    assert (old, new) == (0, 1)
    add_mark_for_atom_for(canvas, old, QPointF(-47, -7), kind="radical")
    add_mark_for_atom_for(canvas, new, QPointF(43, -7), kind="minus")
    owner = new if target_owner else old
    item = add_mark_for_atom_for(canvas, owner, QPointF(60, -10), kind=kind)
    apply_mark_color_for(canvas, item, "#Aa22Cc")
    canvas.services.input.tool_mode_controller.set_tool("select")
    canvas.services.history_service.clear()
    return canvas, item


def _payload(canvas):
    return build_structure_payload_for(canvas, set(canvas.model.atoms), set())


def _assert_electronics(canvas, expected):
    assert canvas.model.atom_annotations == expected
    model, annotations, _bounds = _payload(canvas)
    assert annotations == expected
    block = write_molfile(model, atom_annotations=annotations)
    assert parse_molfile(block).atom_annotations == expected
    return model, annotations, block


@pytest.mark.parametrize("kind,before_expected,after_expected", ELECTRONIC_STATES)
def test_rebind_matches_explicit_electronics_and_direct_target_drawing(
    canvas_factory, kind, before_expected, after_expected
):
    canvas, item = _drawing(canvas_factory, kind)
    direct, _direct_item = _drawing(canvas_factory, kind, target_owner=True)
    center = mark_center_for(canvas, item)
    canvas.services.interaction.move_controller.move_item(
        item, 60 - center.x(), -10 - center.y()
    )
    assert item.data(1)["atom_id"] == 0
    _assert_electronics(canvas, before_expected)
    before = snapshot_canvas_state_for(canvas)
    item_state, position = deepcopy(item.data(1)), item.pos()

    assert mark_scene_service_for_access(canvas).rebind_mark(item, 1)

    model, annotations, molfile = _assert_electronics(canvas, after_expected)
    direct_model, direct_annotations, direct_molfile = _assert_electronics(
        direct, after_expected
    )
    assert serialize_model_state(model) == serialize_model_state(direct_model)
    assert annotations == direct_annotations
    assert molfile == direct_molfile
    assert item.pos() == position
    assert item.data(1)["kind"] == item_state["kind"]
    assert item.data(1)["color"] == item_state["color"]
    assert item.data(1)["atom_id"] == 1
    after = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service
    for _ in range(2):
        history.undo()
        _assert_electronics(canvas, before_expected)
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        _assert_electronics(canvas, after_expected)
        assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("kind,_before,after_expected", ELECTRONIC_STATES)
def test_rebound_identifiers_match_direct_target_without_geometry_inference(
    canvas_factory, kind, _before, after_expected
):
    pytest.importorskip("rdkit")
    canvas, item = _drawing(canvas_factory, kind)
    direct, _direct_item = _drawing(canvas_factory, kind, target_owner=True)
    assert mark_scene_service_for_access(canvas).rebind_mark(item, 1)
    model, annotations, _molfile = _assert_electronics(canvas, after_expected)
    direct_model, direct_annotations, _direct_molfile = _assert_electronics(
        direct, after_expected
    )
    adapter = RDKitAdapter()
    identifiers = adapter.compute_identifiers(
        model_with_atom_annotations(model, annotations)
    )
    expected = adapter.compute_identifiers(
        model_with_atom_annotations(direct_model, direct_annotations)
    )
    assert identifiers.smiles
    assert identifiers.inchikey
    assert identifiers == expected


def _copy(canvas):
    clipboard = Mock()
    controller = SceneClipboardController(canvas)
    assert copy_selection_to_clipboard_for_canvas(
        canvas,
        clipboard=clipboard,
        payload_provider=controller.selection_payload_for_clipboard,
    )
    return clipboard.setMimeData.call_args.args[0]


@pytest.mark.parametrize("kind,_before,after_expected", ELECTRONIC_STATES)
def test_rebound_native_and_clipboard_roundtrip_keep_owner_kind_color(
    canvas_factory, tmp_path, kind, _before, after_expected
):
    canvas, item = _drawing(canvas_factory, kind)
    assert mark_scene_service_for_access(canvas).rebind_mark(item, 1)
    before = snapshot_canvas_state_for(canvas)
    path = tmp_path / "rebound.chemvas"
    write_document(path, before, CANVAS_FILE_VERSION)
    original_bytes = path.read_bytes()
    restored = canvas_factory()
    loaded = read_document(path).state
    assert loaded == json.loads(json.dumps(before))
    restore_canvas_state_for(restored, loaded)
    restored_state = snapshot_canvas_state_for(restored)
    # Glyph-center arithmetic may differ at the final binary-float bit. Native
    # ownership, stored offsets, colors, kinds and every other field stay exact.
    for actual, expected in zip(restored_state["marks"], before["marks"], strict=True):
        for coordinate in ("x", "y"):
            assert actual[coordinate] == pytest.approx(
                expected[coordinate], abs=1e-12, rel=0
            )
            actual[coordinate] = expected[coordinate]
    assert restored_state == before
    _assert_electronics(restored, after_expected)
    select_all_scene_items_for(restored)
    mime = _copy(restored)
    payload = json.loads(bytes(mime.data(clipboard_selection_mime_for(restored))))
    assert len(payload["marks"]) == 3
    copied = next(mark for mark in payload["marks"] if mark.get("color") == "#Aa22Cc")
    assert copied["mark_kind"] == kind
    oxygen = next(atom["id"] for atom in payload["atoms"] if atom["element"] == "O")
    assert copied["atom_id"] == oxygen
    assert "mark_owner" not in json.dumps(payload)
    pasted = canvas_factory()
    clip = SceneClipboardController(pasted)
    assert clip.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, json.dumps(payload))
    )
    colored = next(
        mark
        for mark in mark_items_for(pasted)
        if (mark.data(1) or {}).get("color") == "#Aa22Cc"
    )
    pasted_oxygen = next(
        atom_id for atom_id, atom in pasted.model.atoms.items() if atom.element == "O"
    )
    assert colored.data(1)["atom_id"] == pasted_oxygen
    assert colored.data(1)["kind"] == kind
    assert colored.data(1)["color"] == "#Aa22Cc"
    _assert_electronics(pasted, after_expected)
    final = snapshot_canvas_state_for(pasted)
    pasted.services.history_service.undo()
    assert not pasted.model.atoms
    pasted.services.history_service.redo()
    assert snapshot_canvas_state_for(pasted) == final
    assert snapshot_canvas_state_for(canvas) == before
    assert path.read_bytes() == original_bytes


def _image_bytes(image):
    assert not image.isNull()
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = image.constBits().asstring(image.sizeInBytes())
    assert any(pixels[3::4])
    return image.size(), pixels


@pytest.mark.parametrize(
    "kind", ["plus", "minus", "circled_plus", "circled_minus", "radical"]
)
def test_retained_carbon_visibility_does_not_add_a_second_chemical_change(
    canvas_factory, kind
):
    pytest.importorskip("rdkit")
    canvas = canvas_factory()
    owner = add_atom_for(canvas, "C", 0, 0)
    mark = add_mark_for_atom_for(canvas, owner, QPointF(12, -12), kind=kind)
    mark.setSelected(True)
    canvas.services.history_service.clear()
    before = snapshot_canvas_state_for(canvas)
    canvas.services.scene_operations.scene_delete_controller.delete_selected_items()
    atom = canvas.model.atoms[owner]
    assert atom.element == "C" and atom.explicit_label
    assert not canvas.model.atom_annotations
    model, annotations, _bounds = _payload(canvas)
    assert not annotations
    implicit = deepcopy(model)
    implicit.atoms[owner].explicit_label = False
    # Removing the last electronic mark changes charge/spin intentionally. The
    # additional visibility bit must leave that final neutral chemistry alone.
    assert write_molfile(model, atom_annotations=annotations) == write_molfile(
        implicit, atom_annotations=annotations
    )
    adapter = RDKitAdapter()
    actual = adapter.compute_identifiers(
        model_with_atom_annotations(model, annotations)
    )
    control = adapter.compute_identifiers(
        model_with_atom_annotations(implicit, annotations)
    )
    assert actual == control
    assert actual.smiles == "C"
    assert actual.inchikey
    after = snapshot_canvas_state_for(canvas)
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_owner_feedback_is_visible_but_absent_from_figures_clipboard_and_state(
    canvas_factory, tmp_path
):
    canvas, item = _drawing(canvas_factory, "plus")
    center = mark_center_for(canvas, item)
    canvas.services.interaction.move_controller.move_item(
        item, 60 - center.x(), -10 - center.y()
    )
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    item.setSelected(True)
    refresh_selection_outline_for(canvas)
    outlines = [
        outline
        for outline in selection_outlines_for(canvas)
        if (outline.data(2) or {}).get("kind") == "mark_owner"
    ]
    assert len(outlines) == 1
    assert outlines[0].isVisible()
    assert outlines[0].data(2)["atom_id"] == 0
    assert not outlines[0].path().isEmpty()
    assert "far" in outlines[0].toolTip().lower()
    session = canvas.services.document.canvas_document_session_service
    visible = tmp_path / "feedback-visible.png"
    hidden = tmp_path / "feedback-hidden.png"
    session.export_figure(str(visible), fmt="png", dpi=72)
    with_overlay = _copy(canvas)
    for outline in outlines:
        outline.setVisible(False)
    session.export_figure(str(hidden), fmt="png", dpi=72)
    without_overlay = _copy(canvas)
    assert _image_bytes(QImage(str(visible))) == _image_bytes(QImage(str(hidden)))
    assert _image_bytes(with_overlay.imageData()) == _image_bytes(
        without_overlay.imageData()
    )
    assert bytes(with_overlay.data("image/svg+xml")) == bytes(
        without_overlay.data("image/svg+xml")
    )
    payload = json.loads(bytes(with_overlay.data(clipboard_selection_mime_for(canvas))))
    assert not payload["atoms"]
    assert len(payload["marks"]) == 1
    assert payload["marks"][0]["atom_id"] is None
    assert "mark_owner" not in json.dumps(payload)
    assert snapshot_canvas_state_for(canvas) == before
    assert canvas.services.history_service.capture_stack_snapshot() == history
    assert "mark_owner" not in json.dumps(before)
