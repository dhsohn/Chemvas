"""Native style runs distinguish omitted plain faces from explicit formula faces."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QTextCharFormat, QTextCursor

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.canvas.document_scene import detached_document_scene
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.molecule.native_atom_labels import NativeAtomLabelItem

pytestmark = pytest.mark.usefixtures("qt_application")


def _run(text, face=None):
    style = "" if face is None else f' face="{face}"'
    return f'<s font="3" size="10"{style}>{text}</s>'


def _source(runs, *, root_face="96", caption=False, node_type="GenericNickname"):
    defaults = "" if root_face is None else f' LabelFace="{root_face}"'
    text = f'<t p="50 54" LabelAlignment="Left">{runs}</t>'
    if not caption:
        node = (
            'NodeType="GenericNickname" GenericNickname="R"'
            if node_type == "GenericNickname"
            else 'Element="7" NumHydrogens="2"'
        )
        text = f'<fragment id="2"><n id="3" p="50 50" {node}>{text}</n></fragment>'
    else:
        text = text.replace("<t ", '<t id="2" ', 1)
    return (
        f'<CDXML LabelFont="3" LabelSize="10" CaptionFace="99"{defaults}>'
        '<fonttable><font id="3" name="Arial"/></fonttable>'
        f'<page id="1" BoundingBox="0 0 200 200">{text}</page></CDXML>'
    ).encode()


def _appearance(state, *, caption=False):
    before = deepcopy(state)
    with detached_document_scene(state) as context:
        if caption:
            (item,) = context.state.scene_items_state.note_items.values()
        else:
            item = context.state.atom_graphics_state.atom_items[0]
            assert isinstance(item, NativeAtomLabelItem)
        item.boundingRect()
        block = item.document().begin()
        layout = block.layout()
        styles = []
        sizes = []
        for index in range(len(block.text())):
            cursor = QTextCursor(item.document())
            cursor.setPosition(index)
            cursor.setPosition(index + 1, QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            styles.append(
                (
                    fmt.verticalAlignment(),
                    fmt.font().bold(),
                    fmt.font().italic(),
                    fmt.font().underline(),
                )
            )
            (glyph,) = layout.glyphRuns(index, 1)
            sizes.append(glyph.rawFont().pixelSize() * item.scale())
        # Fixed source rectangle makes this a painted-position and size check,
        # not a comparison that rescales each result to its own text bounds.
        image = QImage(480, 320, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            context.scene.render(
                painter, QRectF(0, 0, 480, 320), QRectF(-70, -65, 60, 40)
            )
        finally:
            painter.end()
        appearance = item.toPlainText(), styles, sizes, image
    assert state == before
    return appearance


@pytest.mark.parametrize("root_face", [None, "96", "99"])
@pytest.mark.parametrize("text", ["R2", "X17", "NH2"])
def test_omitted_face_is_plain_like_explicit_zero_even_under_label_defaults(
    root_face, text
):
    # ChemDraw saves a face=0 numeric nickname as <s font="3" size="10">,
    # even with root LabelFace=96. CDXString's plain style example also omits
    # s.face; LabelStyle inheritance is not the default for an existing run.
    expected = None
    for face in (None, 0):
        state = parse_cdxml_document(
            _source(_run(text, face), root_face=root_face)
        ).state
        appearance = _appearance(state)
        assert appearance[0] == text
        assert appearance[1] == [
            (QTextCharFormat.VerticalAlignment.AlignNormal, False, False, False)
        ] * len(text)
        assert appearance[2] == pytest.approx([10] * len(text))
        if expected is not None:
            assert appearance == expected
        expected = appearance
        saved = update_native_document(state)
        run = ET.fromstring(saved).find(".//n/t/s")
        assert run.get("face") == (None if face is None else "0")
        assert _appearance(parse_cdxml_document(saved).state) == appearance


@pytest.mark.parametrize("node_type", ["GenericNickname", "Element"])
@pytest.mark.parametrize("face", [96, 99])
def test_explicit_formula_keeps_scripted_digit_and_combined_emphasis(node_type, face):
    raw = _source(_run("NH2", face), root_face="0", node_type=node_type)
    state = parse_cdxml_document(raw).state
    appearance = _appearance(state)
    normal = QTextCharFormat.VerticalAlignment.AlignNormal
    sub = QTextCharFormat.VerticalAlignment.AlignSubScript
    emphasized = face == 99
    assert appearance[0] == "NH2"
    assert appearance[1] == [
        (alignment, emphasized, emphasized, False)
        for alignment in (normal, normal, sub)
    ]
    assert appearance[2][:2] == pytest.approx([10, 10])
    assert 0 < appearance[2][2] < appearance[2][0]
    plain = _appearance(parse_cdxml_document(_source(_run("NH2", 0))).state)
    assert appearance[3] != plain[3]
    saved = update_native_document(state)
    assert ET.fromstring(saved).find(".//n/t/s").get("face") == str(face)
    assert _appearance(parse_cdxml_document(saved).state) == appearance


@pytest.mark.parametrize("caption", [False, True], ids=["atom", "caption"])
@pytest.mark.parametrize("plain_face", [None, 0], ids=["omitted", "explicit-zero"])
def test_mixed_run_faces_reset_plain_text_and_keep_explicit_scripts(
    caption, plain_face
):
    raw = _source(
        _run("A", 3)
        + _run("2", 33)
        + _run("+", 66)
        + _run("R2", plain_face)
        + _run("X", 4),
        caption=caption,
    )
    state = parse_cdxml_document(raw).state
    appearance = _appearance(state, caption=caption)
    alignment = QTextCharFormat.VerticalAlignment
    assert appearance[0] == "A2+R2X"
    assert appearance[1] == [
        (alignment.AlignNormal, True, True, False),
        (alignment.AlignSubScript, True, False, False),
        (alignment.AlignSuperScript, False, True, False),
        (alignment.AlignNormal, False, False, False),
        (alignment.AlignNormal, False, False, False),
        (alignment.AlignNormal, False, False, True),
    ]
    assert [appearance[2][i] for i in (0, 3, 4, 5)] == pytest.approx([10] * 4)
    assert all(0 < appearance[2][i] < 10 for i in (1, 2))
    saved = update_native_document(state, note_writer=write_native_caption)
    assert _appearance(parse_cdxml_document(saved).state, caption=caption) == appearance


def test_native_writer_formula_and_native_plain_face_elision_reimport():
    state = parse_cdxml_document(_source(_run("R2", 0))).state
    state["model"]["atoms"][0]["x"] += 7
    saved = update_native_document(state)
    root = ET.fromstring(saved)
    assert root.get("LabelFace") == "96"
    run = root.find(".//n/t/s")
    assert run.get("face") == "0"
    before_elision = _appearance(parse_cdxml_document(saved).state)
    # Reproduce the native writer's observed plain-face elision without
    # claiming this synthetic edit runs an external consumer.
    del run.attrib["face"]
    assert _appearance(parse_cdxml_document(ET.tostring(root)).state) == before_elision

    # NativeWriter emits formula faces for a newly authored numeric label.
    # Keeping that explicit face preserves its established rendering behavior.
    state["model"]["atoms"][0]["element"] = "R3"
    authored = update_native_document(state)
    assert ET.fromstring(authored).find(".//n/t/s").get("face") == "96"
    appearance = _appearance(parse_cdxml_document(authored).state)
    assert appearance[0] == "R3"
    assert appearance[1][1][0] == QTextCharFormat.VerticalAlignment.AlignSubScript
    assert 0 < appearance[2][1] < appearance[2][0]
