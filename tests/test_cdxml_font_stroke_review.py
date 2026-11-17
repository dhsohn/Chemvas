"""Public export, whole-caption clipboard and scene-unit box regressions."""

import json
import math
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTextCursor

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document import (
    CLIPBOARD_SELECTION_VERSION,
    validate_clipboard_selection_payload,
)
from chemvas.features.cdxml_document import parse_cdxml_document, read_cdxml_document
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import MinimumFontSizeError
from chemvas.ui.annotations.projections import restore_active_projection
from chemvas.ui.annotations.text import update_note_box
from chemvas.ui.export.cdxml_document_writer import save_cdxml_document
from chemvas.ui.scene.scene_clipboard_controller import SceneClipboardController
from chemvas.ui.scene.scene_clipboard_logic import decode_clipboard_selection_payload
from tests.test_cdxml_font_stroke_parity import appearance, source
from tests.test_export_readability_service import _assess

pytestmark = pytest.mark.usefixtures("qt_application")


def _caption_state(*, size=8.5, rotation=27):
    return parse_cdxml_document(
        source(
            '<t id="2" p="80 30" BoundingBox="55 20 110 35" '
            f'Justification="Center" RotationAngle="{rotation * 65536}">'
            f'<s font="3" size="{size}">N</s>'
            '<s font="3" size="9.4" face="1">B</s>'
            '<s font="3" size="7.2" face="2">I</s></t>'
        )
    ).state


@pytest.mark.parametrize("fmt", ["svg", "png"])
def test_public_export_minimum_accepts_native_atom_and_rejects_small_output(
    tmp_path, fmt
):
    state = parse_cdxml_document(
        source(
            '<fragment id="2"><n id="3" p="40 60" Element="7">'
            '<t p="36 64"><s font="3" size="10.5" face="96">NH2</s></t>'
            "</n></fragment>"
        )
    ).state
    with offscreen_canvas(state, command="native-readability") as (canvas, service):
        original = service.snapshot_state()
        report = _assess(canvas, output_format=fmt)
        assert report["coverage"]["atom"]["minimum_pt"] == pytest.approx(10.5)
        assert report["coverage"]["atom"]["glyphs"] == 2
        assert report["coverage"]["atom_script"]["glyphs"] == 1
        minimum = report["minimum_font_pt"]
        assert 0 < minimum < 10.5
        _assess(canvas, minimum=minimum, output_format=fmt)
        with pytest.raises(MinimumFontSizeError):
            _assess(canvas, minimum=minimum + 0.01, output_format=fmt)
        path = tmp_path / f"readable.{fmt}"
        service.export_figure(str(path), fmt=fmt, min_font_pt=0.1)
        assert path.stat().st_size > 100
        rejected = tmp_path / f"too-small.{fmt}"
        with pytest.raises(MinimumFontSizeError) as error:
            service.export_figure(str(rejected), fmt=fmt, min_font_pt=999)
        assert error.value.minimum_pt > 0.1
        assert error.value.witness["kind"] == "atom"
        assert error.value.witness["script"] is True
        assert not rejected.exists()
        assert service.snapshot_state() == original


def test_native_atom_measurement_still_refuses_missing_glyphs_and_skips_hidden():
    state = parse_cdxml_document(
        source(
            '<fragment id="2"><n id="3" p="40 60" Element="7">'
            '<t p="36 64"><s font="3" size="8.5">N</s></t></n></fragment>'
        )
    ).state
    with offscreen_canvas(state, command="native-readability-missing") as (canvas, _):
        item = next(iter(canvas.runtime_state.atom_graphics_state.atom_items.values()))
        cursor = QTextCursor(item.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText("\U0010ffff")
        with pytest.raises(ValueError, match="missing glyph"):
            _assess(canvas)
        item.setVisible(False)
        assert _assess(canvas, minimum=999)["status"] == "no-visible-text"


def _families(item):
    block = item.document().begin()
    return [
        block.layout().glyphRuns(i, 1)[0].rawFont().familyName()
        for i in range(len(block.text()))
    ]


@pytest.mark.parametrize("destination", ["same", "native", "new"])
@pytest.mark.parametrize("legacy_pixels", [False, True])
def test_whole_native_caption_copy_paste_and_disk_reopen(
    tmp_path, destination, legacy_pixels
):
    state = _caption_state()
    if legacy_pixels:
        state["notes"][0]["html"] = state["notes"][0]["html"].replace("pt", "px")
    with ExitStack() as stack:
        canvas, service = stack.enter_context(
            offscreen_canvas(state, command="native-caption-copy")
        )
        original = canvas.runtime_state.note_items()[0]
        expected = appearance(original)
        families = _families(original)
        bounds = original.sceneBoundingRect().size()
        original.setSelected(True)
        with patch.object(original, "toHtml", side_effect=AssertionError("view read")):
            payload = SceneClipboardController(canvas).selection_payload_for_clipboard()
        assert payload is not None
        encoded = json.dumps(payload)
        decoded = decode_clipboard_selection_payload(
            [encoded], version=CLIPBOARD_SELECTION_VERSION
        )
        if destination != "same":
            target = (
                parse_cdxml_document(source("")).state
                if destination == "native"
                else compose_document_state(
                    {
                        "format": "chemvas-document-composition",
                        "version": 1,
                        "atoms": [],
                        "bonds": [],
                    }
                )
            )
            target["settings"].update(
                text_font_family="Times New Roman",
                text_font_weight=700,
                text_italic=True,
            )
            canvas, service = stack.enter_context(
                offscreen_canvas(target, command="native-caption-paste")
            )
        controller = SceneClipboardController(canvas)
        assert controller.paste_selection_from_clipboard(
            payload_provider=lambda: decoded
        )
        pasted = canvas.runtime_state.note_items()[-1]
        assert appearance(pasted) == expected
        assert _families(pasted) == families
        assert pasted.sceneBoundingRect().width() == pytest.approx(bounds.width())
        assert pasted.sceneBoundingRect().height() == pytest.approx(bounds.height())
        canvas.services.history_service.undo()
        assert pasted not in canvas.runtime_state.note_items()
        canvas.services.history_service.redo()
        pasted = canvas.runtime_state.note_items()[-1]
        assert appearance(pasted) == expected
        record_id = pasted.record_id
        before_materialize = pasted.note_state()
        sip.delete(pasted)
        pasted = restore_active_projection(canvas, record_id)
        assert appearance(pasted) == expected, (before_materialize, pasted.toHtml())
        assert _families(pasted) == families
        cursor = QTextCursor(pasted.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("I")
        assert appearance(pasted) == expected + [expected[-1]]
        pasted.document().undo()
        assert appearance(pasted) == expected
        saved_bounds = pasted.sceneBoundingRect()
        path = tmp_path / f"pasted-{destination}.cdxml"
        save_cdxml_document(canvas, str(path), service.snapshot_state())
    with offscreen_canvas(
        read_cdxml_document(path).state, command="native-caption-paste-reopen"
    ) as (canvas, _):
        pasted = canvas.runtime_state.note_items()[-1]
        assert appearance(pasted) == expected
        assert _families(pasted) == families
        assert pasted.sceneBoundingRect().width() == pytest.approx(bounds.width())
        assert pasted.sceneBoundingRect().height() == pytest.approx(bounds.height())
    if destination != "new" and not legacy_pixels:
        # The native caption added to a retained-source document also has the
        # correct baseline/rotation when opened without a Chemvas snapshot.
        native = parse_cdxml_document(ET.tostring(ET.parse(path).getroot())).state
        with offscreen_canvas(native, command="pasted-native-reimport") as (canvas, _):
            pasted = canvas.runtime_state.note_items()[-1]
            assert appearance(pasted) == expected
            actual = pasted.sceneBoundingRect()
            for actual_value, expected_value in zip(
                actual.getRect(), saved_bounds.getRect(), strict=True
            ):
                assert actual_value == pytest.approx(expected_value, abs=1e-8)


@pytest.mark.parametrize(
    "placement",
    [
        None,
        [],
        [0, 0, "Left"],
        [0, 0, "Wrong", 0],
        [True, 0, "Left", 0],
        [0, 0, "Left", float("inf")],
    ],
)
def test_clipboard_refuses_invalid_native_caption_placement(placement):
    payload = {
        "format": "chemvas-selection",
        "version": CLIPBOARD_SELECTION_VERSION,
        "atoms": [],
        "bonds": [],
        "rings": [],
        "marks": [],
        "scene_items": [
            {"kind": "note", "text": "A", "x": 0, "y": 0, "native_caption": placement}
        ],
    }
    assert not validate_clipboard_selection_payload(payload)


def _assert_box(item):
    box = item.data(20)
    rect = item.boundingRect()
    scale = math.hypot(item.sceneTransform().m11(), item.sceneTransform().m12())
    assert (rect.left() - box.rect().left()) * scale == pytest.approx(6)
    assert (rect.top() - box.rect().top()) * scale == pytest.approx(6)
    assert (box.rect().right() - rect.right()) * scale == pytest.approx(6)
    assert (box.rect().bottom() - rect.bottom()) * scale == pytest.approx(6)
    assert box.pen().widthF() * scale == pytest.approx(1)


@pytest.mark.parametrize("rotation", [0, 37])
@pytest.mark.parametrize("size", [8.5, 1000])
def test_native_caption_box_scene_dimensions_after_layout_edit_and_undo(rotation, size):
    state = _caption_state(size=size, rotation=rotation)
    state["settings"].update(note_box_enabled=True, note_border_enabled=True)
    with offscreen_canvas(state, command="native-caption-box") as (canvas, _):
        item = canvas.runtime_state.note_items()[0]
        _assert_box(item)
        update_note_box(item, canvas.runtime_state.text_style_state)
        _assert_box(item)
        cursor = QTextCursor(item.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("longer caption")
        _assert_box(item)
        item.document().undo()
        assert item.toPlainText() == "NBI"
        _assert_box(item)
        item.document().redo()
        _assert_box(item)
        item.setRotation(19)
        item.setPos(item.pos() + QPointF(12, 15))
        _assert_box(item)
