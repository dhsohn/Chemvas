"""File > Export Figure from the browser session, through the native figure owner.

The ``export_figure`` session query answers with the plain SVG that the
desktop's offscreen export writes for the accepted document, refuses what the
native owner refuses, and leaves the session as it was. The server runs that
export in a short-lived child process; this test compares its reply with the
same export run in-process.
"""

from __future__ import annotations

import os
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.bootstrap.web_adapter import BrowserSession, edit_document, new_document
from chemvas.domain.document import extract_document_state

SVG_ROOT = "{http://www.w3.org/2000/svg}svg"


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


def unchanged(session):
    """Everything an export must leave as it was."""
    return (
        session.revision,
        deepcopy(session.info),
        session.saved,
        session.name,
        session.history.can_undo(),
        session.history.can_redo(),
    )


def native_svg(source, tmp_path):
    """The desktop's whole-canvas plain SVG for ``source``, from its offscreen owner."""
    path = tmp_path / "native.svg"
    with offscreen_canvas(
        extract_document_state(source), command="web-figure-export-oracle"
    ) as (_canvas, service):
        service.export_figure(str(path), fmt="svg", scope="sheet")
    return path.read_text(encoding="utf-8")


def test_browser_figure_export_answers_the_native_whole_canvas_svg(tmp_path):
    source = edit_document(
        {"document": new_document(), "edit": {"kind": "ring", "x": 100, "y": 100}}
    )["document"]
    native = native_svg(source, tmp_path)
    oracle = ET.fromstring(native)
    assert oracle.tag == SVG_ROOT and oracle.get("viewBox")

    session = BrowserSession()
    session.dispatch({"revision": 0, "action": "load", "document": source})
    before = unchanged(session)
    reply = session.dispatch(
        {
            "revision": session.revision,
            "action": "export_figure",
            "format": "svg",
            "scope": "sheet",
        }
    )
    assert reply == {"svg": native, "revision": session.revision}
    exported = ET.fromstring(reply["svg"])
    assert [exported.get(key) for key in ("width", "height", "viewBox")] == [
        oracle.get(key) for key in ("width", "height", "viewBox")
    ]
    assert unchanged(session) == before

    # Selection scope without a selection fails closed with the native message.
    with pytest.raises(
        ValueError, match="Select something to export, or choose Whole canvas."
    ):
        session.dispatch(
            {
                "revision": session.revision,
                "action": "export_figure",
                "format": "svg",
                "scope": "selection",
                "selection": [],
            }
        )
    assert unchanged(session) == before
