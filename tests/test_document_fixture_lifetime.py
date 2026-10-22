"""Repeated CDXML fixture writes keep the Qt application alive."""

import gc
import json
import weakref
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from chemvas.domain.document import CANVAS_FILE_VERSION
from tests.document_file_helpers import write_document


def test_cdxml_fixture_application_survives_between_writes(tmp_path):
    payload = json.loads(
        (Path(__file__).parent / "fixtures/document-v7/minimal.json").read_text()
    )
    from chemvas.core.document_io import parse_document

    state = parse_document(payload).state
    write_document(tmp_path / "first.cdxml", state, CANVAS_FILE_VERSION)
    application = weakref.ref(QApplication.instance())
    gc.collect()
    assert application() is not None
    write_document(tmp_path / "second.cdxml", state, CANVAS_FILE_VERSION)
    gc.collect()
    assert QApplication.instance() is application()
    assert application() is not None
