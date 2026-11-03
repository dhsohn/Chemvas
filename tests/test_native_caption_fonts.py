"""Edited native captions keep the font they show, not Qt's generic default.

The note record's HTML omits a run's family (and weight or italic) when it
equals the editor's default font, which comes from the document's text
settings. The native caption writer must resolve the record against the same
defaults.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.export.cdxml_native_text import write_native_caption
from tests.canvas_factory import build_canvas_view

CAPTION = """<CDXML CaptionFont="3"><fonttable><font id="3" name="{family}"/><font id="5" name="Times New Roman"/></fonttable><page id="1" BoundingBox="0 0 400 200"><t id="2" p="150 60"><s font="3" size="10" face="0">Short </s><s font="5" size="10" face="0">serif</s></t></page></CDXML>"""


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _fonts(raw: bytes) -> list[str]:
    root = ET.fromstring(raw)
    names = {f.get("id"): f.get("name") for f in root.iter("font")}
    caption = root.find(".//page/t")
    assert caption is not None
    return [names[run.get("font")] for run in caption.findall("s")]


def _edit_caption(canvas, raw: bytes) -> dict:
    session = canvas.services.canvas_document_session_service
    session.apply_state(parse_cdxml_document(raw).state)
    (item,) = canvas.runtime_state.scene_items_state.note_items.values()
    cursor = QTextCursor(item.document())
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.insertText("Edited ")
    QApplication.processEvents()
    return session.snapshot_state()


@pytest.mark.parametrize("family", ["Arial", "Helvetica"])
def test_edited_caption_keeps_source_fonts(canvas, family):
    state = _edit_caption(canvas, CAPTION.format(family=family).encode())
    # Native import makes CaptionFont the document's text family, so its runs
    # lose their family in the note HTML; the other run keeps it explicitly.
    raw = update_native_document(state, note_writer=write_native_caption)
    assert set(_fonts(raw)) == {family, "Times New Roman"}
    assert _fonts(raw)[-1] == "Times New Roman"
    names = [f.get("name") for f in ET.fromstring(raw).iter("font")]
    assert names == [family, "Times New Roman"]


def test_default_family_follows_document_text_settings(canvas):
    state = _edit_caption(canvas, CAPTION.format(family="Arial").encode())
    assert state["settings"]["text_font_family"] == "Arial"
    assert "Arial" not in state["notes"][0]["html"]
    # Changing the document's text family changes what the omitted runs mean.
    state["settings"]["text_font_family"] = "Courier New"
    raw = update_native_document(state, note_writer=write_native_caption)
    assert _fonts(raw) == ["Courier New", "Times New Roman"]


def test_writer_without_text_defaults_keeps_previous_contract():
    root = ET.fromstring(CAPTION.format(family="Arial").encode())
    node = root.find(".//page/t")
    assert node is not None
    write_native_caption(
        root,
        node,
        {
            "text": "x",
            "html": "<p><span style=\"font-family:'Courier New'\">x</span></p>",
        },
    )
    assert [run.get("font") for run in node.findall("s")] == ["6"]
    assert root.find("./fonttable/font[@id='6']").get("name") == "Courier New"
