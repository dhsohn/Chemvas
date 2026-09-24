from __future__ import annotations

from copy import deepcopy

import pytest
from PyQt6.QtGui import QImage

from chemvas.bootstrap import document_render
from chemvas.bootstrap.document_cli_shared import (
    offscreen_canvas,
    offscreen_document_scene,
)
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas.graphics_items import AtomLabelItem

pytestmark = pytest.mark.usefixtures("qt_application")


def _state(text):
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": text, "x": 100, "y": 100},
                {"id": 1, "element": "C", "x": 60, "y": 100},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
        }
    )


@pytest.mark.parametrize(
    "plain,scripted", [("PPh3", "PPh₃"), ("C10H21", "C₁₀H₂₁"), ("(CH3)2", "(CH₃)₂")]
)
def test_subscript_glyphs_and_export_bounds_match_ascii(plain, scripted):
    labels = []
    for text in (plain, scripted):
        item = AtomLabelItem()
        item.setPlainText(text)
        labels.append(item)
    normal, unicode = labels
    assert unicode.toPlainText() == scripted
    assert unicode.glyph_path() == normal.glyph_path()
    assert unicode.boundingRect() == normal.boundingRect()
    assert unicode.shape() == normal.shape()


def test_atom_input_and_generated_document_preserve_unicode_and_render_once(tmp_path):
    scripted = "PPh₃"
    composed = _state(scripted)
    before = deepcopy(composed)
    with offscreen_canvas(_state("N"), command="subscript-test") as (canvas, session):
        canvas.services.atom_label_service.add_or_update_atom_label(0, scripted)
        assert canvas.model.atoms[0].element == scripted
        item = canvas.render_context.state.atom_graphics_state.atom_items[0]
        with offscreen_document_scene(
            _state("PPh3"), command="subscript-test"
        ) as scene:
            reference = scene.state.atom_graphics_state.atom_items[0]
            assert item.glyph_path() == reference.glyph_path()
            assert item.pos() == reference.pos()
        with offscreen_document_scene(composed, command="subscript-test") as scene:
            generated = scene.state.atom_graphics_state.atom_items[0]
            assert item.glyph_path() == generated.glyph_path()
            assert item.pos() == generated.pos()
        path = tmp_path / "unicode.chemvas"
        write_document(path, session.snapshot_state(), CANVAS_FILE_VERSION)
    _, reopened = read_exact_document(path)
    assert reopened.state["model"]["atoms"]["0"]["element"] == scripted
    images = []
    for state in (reopened.state, _state("PPh3")):
        result = document_render._render_offscreen(
            state,
            output_format="png",
            background="white",
            dpi=300,
            width_mm=None,
            max_height_mm=None,
            min_font_pt=None,
        )
        image = QImage.fromData(result.content)
        assert not image.isNull()
        images.append(image)
    assert images[0] == images[1]
    assert composed == before
