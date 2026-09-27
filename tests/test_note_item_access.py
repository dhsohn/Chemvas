from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGraphicsTextItem

from chemvas.ui.scene.note_item_access import (
    committed_note_text_for,
    set_committed_note_text_for,
)


def test_committed_note_text_rejects_objects_without_a_note_contract() -> None:
    class _PlainNote:
        pass

    item = _PlainNote()

    with pytest.raises(
        AttributeError, match=r"^Note item does not implement set_committed_text\(\)\.$"
    ):
        set_committed_note_text_for(item, "Stable")


def test_committed_note_text_uses_qgraphics_item_data_role() -> None:
    app = QApplication.instance() or QApplication([])
    item = QGraphicsTextItem("Stable")

    set_committed_note_text_for(item, "Stable")

    assert committed_note_text_for(item) == "Stable"
    assert not hasattr(item, "_last_text")
    app.processEvents()
