"""File > Export Figure from the browser session, through the native figure owner.

The ``export_figure`` session query answers with the plain SVG that the
desktop's offscreen export writes for the accepted document, refuses what the
native owner refuses, and leaves the session as it was. The server runs that
export in a short-lived child process; this test compares its reply with the
same export run in a separate oracle process. That process starts the way the
desktop does, because this test process's Qt platform and default font are the
test runner's, not the product's.
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from chemvas.bootstrap.web_adapter import BrowserSession, edit_document, new_document

ROOT = Path(__file__).resolve().parents[1]
SVG_ROOT = "{http://www.w3.org/2000/svg}svg"
# The desktop's offscreen export on the host's export platform at 96 DPI. As in
# bootstrap/application.py, the application pins AA_Use96Dpi and exists before
# the canvas, so it keeps its own default font (Segoe UI on native Windows).
NATIVE_EXPORT = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from chemvas.bootstrap.document_cli_shared import offscreen_canvas, qt_platform
from chemvas.domain.document import extract_document_state
os.environ["QT_QPA_PLATFORM"] = qt_platform()
if sys.platform == "win32":
    os.environ["QT_FONT_DPI"] = "96"
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_Use96Dpi)
application = QApplication(["chemvas-web-figure-export-oracle"])
with open(sys.argv[2], encoding="utf-8") as stream:
    state = extract_document_state(json.load(stream))
with offscreen_canvas(state, command="web-figure-export-oracle") as (_canvas, service):
    service.export_figure(sys.argv[3], fmt="svg", scope="sheet")
"""


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
    document = tmp_path / "source.json"
    document.write_text(json.dumps(source), encoding="utf-8")
    path = tmp_path / "native.svg"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            NATIVE_EXPORT,
            str(ROOT / "app"),
            str(document),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
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
