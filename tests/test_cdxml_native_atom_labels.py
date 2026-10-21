"""Native source typography is measured independently of global drawing style."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy

import pytest
from PyQt6.QtGui import QFontInfo, QTextCharFormat
from PyQt6.QtWidgets import QApplication

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.canvas.document_scene import detached_document_scene
from chemvas.ui.molecule.native_atom_labels import NativeAtomLabelItem

SOURCE = b"""<CDXML LabelSize="10" LabelFont="3" BondLength="20"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 200 200"><fragment id="2">
<n id="3" p="50 50" Element="7"><t p="51.805 51.95" LabelAlignment="Right" LabelJustification="Right"><s font="3" size="5" face="96">NH</s></t></n>
<n id="4" p="80 50" Element="7"><t p="78.195 51.95" BoundingBox="78.195 47.75 81.805 56.15" LabelAlignment="Below"><s font="3" size="5" face="96">NH</s></t></n>
<n id="5" p="110 50" NodeType="GenericNickname"><t p="108 52.33"><s font="3" size="6" face="1">K</s><s font="3" size="6" face="33">1</s></t></n>
<n id="6" p="140 50" Element="8"><t p="136 53.9"><s font="3" size="10" face="96">O</s></t></n>
</fragment></page></CDXML>"""


@pytest.fixture(scope="module", autouse=True)
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def state():
    return parse_cdxml_document(SOURCE, preserve_source=True).state


def baseline(item):
    item.boundingRect()
    layout = item.document().begin().layout()
    line = layout.lineAt(0)
    return item.y() + (layout.position().y() + line.y() + line.ascent()) * item.scale()


def test_native_sizes_baselines_and_direction_do_not_use_global_style():
    document = state()
    before = deepcopy(document)
    with detached_document_scene(document) as context:
        items = context.state.atom_graphics_state.atom_items
        assert all(isinstance(i, NativeAtomLabelItem) for i in items.values())
        assert items[0].toPlainText() == "HN"
        assert items[1].toPlainText() == "N\nH"
        for atom_id, expected_size in enumerate((5, 5, 6, 10)):
            assert (
                QFontInfo(items[atom_id].font()).pixelSize() * items[atom_id].scale()
                == expected_size
            )
        context.atom_labels.draw_atom(0)
        assert QFontInfo(items[0].font()).pixelSize() * items[0].scale() == 5
        assert baseline(items[0]) == pytest.approx(-48.05)
        line = items[0].document().begin().layout().lineAt(0)
        assert items[0].x() + line.naturalTextWidth() * items[
            0
        ].scale() == pytest.approx(-48.195)
        assert baseline(items[1]) == pytest.approx(-48.05)
        first = items[1].document().begin()
        second = first.next()
        assert (second.layout().position().y() - first.layout().position().y()) * items[
            1
        ].scale() == pytest.approx(4.2, abs=1 / 64)
        assert items[2].document().begin().begin().fragment().charFormat().font().bold()
        iterator = items[2].document().begin().begin()
        iterator += 1
        assert (
            iterator.fragment().charFormat().verticalAlignment()
            == QTextCharFormat.VerticalAlignment.AlignSubScript
        )
        assert document == before
    assert update_native_document(document) == update_native_document(before)


def test_native_label_follows_move_and_edit_then_restores_original_typography():
    with detached_document_scene(state()) as context:
        atom = context.model.atoms[0]
        original = context.state.atom_graphics_state.atom_items[0]
        old_x, old_y = original.x(), original.y()
        atom.x += 7
        atom.y += 9
        context.atom_labels.relayout_atom_label(0)
        assert original.x() == pytest.approx(old_x + 7)
        assert original.y() == pytest.approx(old_y + 9)
        atom.element = "Cl"
        context.atom_labels.relayout_atom_label(0)
        assert not isinstance(
            context.state.atom_graphics_state.atom_items[0], NativeAtomLabelItem
        )
        atom.element = "NH"
        context.atom_labels.relayout_atom_label(0)
        restored = context.state.atom_graphics_state.atom_items[0]
        assert restored.toPlainText() == "HN"
        assert baseline(restored) == pytest.approx(-39.05)


@pytest.mark.parametrize("size", ["nan", "inf", "0", "-2", "1001"])
def test_invalid_native_label_sizes_are_rejected(size):
    source = SOURCE.replace(b'size="5"', f'size="{size}"'.encode())
    document = parse_cdxml_document(source, preserve_source=True).state
    with pytest.raises(ValueError, match="label size"):
        with detached_document_scene(document):
            pass


def test_above_label_and_source_free_scene():
    document = parse_cdxml_document(
        SOURCE.replace(b'LabelAlignment="Below"', b'LabelAlignment="Above"'),
        preserve_source=True,
    ).state
    with detached_document_scene(document) as context:
        assert context.state.atom_graphics_state.atom_items[1].toPlainText() == "H\nN"
    document.pop("cdxml_source")
    with detached_document_scene(document) as context:
        assert not context.state.atom_graphics_state.native_labels
        assert not any(
            isinstance(i, NativeAtomLabelItem)
            for i in context.state.atom_graphics_state.atom_items.values()
        )


def test_fractional_native_font_size_survives_qt_pixel_rounding():
    document = parse_cdxml_document(
        SOURCE.replace(b'size="5"', b'size="4.9"'), preserve_source=True
    ).state
    with detached_document_scene(document) as context:
        item = context.state.atom_graphics_state.atom_items[0]
        assert QFontInfo(item.font()).pixelSize() * item.scale() == pytest.approx(4.9)
        assert baseline(item) == pytest.approx(-48.05)


def test_rotated_native_atom_label_keeps_baseline_anchor():
    from PyQt6.QtCore import QPointF

    document = parse_cdxml_document(
        SOURCE.replace(b'p="136 53.9"', b'p="136 53.9" RotationAngle="5308416"'),
        preserve_source=True,
    ).state
    with detached_document_scene(document) as context:
        item = context.state.atom_graphics_state.atom_items[3]
        layout = item.document().begin().layout()
        local_anchor = QPointF(0, layout.position().y() + layout.lineAt(0).ascent())
        anchor = item.mapToScene(local_anchor)
        assert anchor.x() == pytest.approx(36)
        assert anchor.y() == pytest.approx(-46.1)
        assert item.rotation() == 81
        context.model.atoms[3].x += 3
        context.atom_labels.relayout_atom_label(3)
        assert item.mapToScene(local_anchor) == anchor + QPointF(3, 0)
