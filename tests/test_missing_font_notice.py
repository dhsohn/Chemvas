"""A document whose fonts are not installed says so in the status bar."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import Mock

import pytest
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.document_fonts import document_font_families
from chemvas.ui.canvas.document_font_availability import (
    missing_document_fonts,
    missing_font_families,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window

pytestmark = pytest.mark.usefixtures("qt_application")

MISSING = "Chemvas Missing Font Test"


def _installed() -> str:
    return QFontDatabase.families()[0]


def _native(caption_font: str, *, unused: str = "Unused Font Test") -> bytes:
    return f"""<CDXML CaptionFont="3" LabelFont="3"><fonttable><font id="3" name="{caption_font}"/><font id="9" name="{unused}"/></fonttable><page id="1" BoundingBox="0 0 300 200"><fragment id="2"><n id="4" p="50 50" Element="8"><t p="50 50"><s font="3" size="10" face="96">O</s></t></n></fragment><t id="5" p="80 60"><s font="3" size="10" face="0">Caption</s></t></page></CDXML>""".encode()


def test_families_come_from_used_native_fonts_and_note_html():
    state = parse_cdxml_document(_native("Arial")).state
    families = document_font_families(state)
    # The fonttable's unreferenced entry is not text the document draws.
    assert "Unused Font Test" not in families
    assert families[0] == "Arial"
    state["notes"][0]["html"] = (
        "<p><span style=\"font-family:'Foo\\'Bar', Courier New\">x</span>"
        '<span style="font-family:&#x27;ARIAL&#x27;">y</span></p>'
    )
    families = document_font_families(state)
    assert families[0] == "Arial"
    assert {"Foo'Bar", "Courier New"} <= set(families)
    assert len([f for f in families if f.casefold() == "arial"]) == 1


def test_document_text_font_counts_only_with_notes():
    state = parse_cdxml_document(_native("Arial")).state
    state["settings"]["text_font_family"] = MISSING
    assert MISSING in document_font_families(state)
    state["notes"] = []
    state["cdxml_source"] = None
    assert document_font_families(state) == []


def test_missing_font_families_reports_only_substituted_fonts():
    assert missing_font_families([_installed(), MISSING]) == (MISSING,)
    assert missing_font_families([_installed().upper()]) == ()


def test_missing_document_fonts_for_native_caption():
    state = parse_cdxml_document(_native(MISSING)).state
    assert MISSING in missing_document_fonts(state)
    assert "Unused Font Test" not in missing_document_fonts(state)


def _notice(window) -> str:
    label = window.services.status_service.autosave_error_label
    return "" if label.isHidden() else label.text()


def test_opened_document_with_missing_font_shows_notice_per_tab(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = build_main_window()
    window.show()
    service = window.services.document_action_service
    missing_path = tmp_path / "missing.cdxml"
    missing_path.write_bytes(_native(MISSING))
    installed_path = tmp_path / "installed.cdxml"
    installed_path.write_bytes(_native(_installed()))
    box = Mock()
    try:
        assert service.load_canvas_from_path(window, str(missing_path), message_box=box)
        app.processEvents()
        missing_canvas = active_canvas_for_window(window)
        assert MISSING in (
            missing_canvas.runtime_state.document_metadata_state.missing_fonts
        )
        assert f"Missing fonts: {MISSING}" in _notice(window)
        label = window.services.status_service.autosave_error_label
        assert "not installed" in label.toolTip()
        assert "substitute" in label.toolTip()

        # A second document without missing fonts clears the notice on its tab.
        window.services.canvas_document_service.new_canvas(window)
        app.processEvents()
        assert _notice(window) == ""
        assert service.load_canvas_from_path(
            window, str(installed_path), message_box=box
        )
        app.processEvents()
        assert _notice(window) == ""

        tabs = window.tab_references.canvas_tabs
        tabs.setCurrentIndex(tabs.indexOf(missing_canvas))
        app.processEvents()
        assert f"Missing fonts: {MISSING}" in _notice(window)
        assert not box.warning.called
    finally:
        for canvas in window.tab_references.all_canvases():
            window.services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()
