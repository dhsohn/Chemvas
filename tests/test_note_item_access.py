from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None
    QGraphicsTextItem = None

from ui.note_item_access import committed_note_text_for, set_committed_note_text_for


class _PublicNote:
    def __init__(self) -> None:
        self.value = ""

    def committed_text(self) -> str:
        return self.value

    def set_committed_text(self, text: str) -> None:
        self.value = text


def test_committed_note_text_uses_public_note_contract() -> None:
    item = _PublicNote()

    set_committed_note_text_for(item, "Mechanism")

    assert committed_note_text_for(item) == "Mechanism"
    assert item.value == "Mechanism"
    assert not hasattr(item, "_last_text")


def test_committed_note_text_keeps_plain_fake_compatibility_with_public_attr() -> None:
    class _PlainNote:
        pass

    item = _PlainNote()

    set_committed_note_text_for(item, "Stable")

    assert committed_note_text_for(item) == "Stable"
    assert item.committed_note_text == "Stable"
    assert not hasattr(item, "_last_text")


def test_committed_note_text_uses_qgraphics_item_data_role() -> None:
    if QApplication is None:
        return
    app = QApplication.instance() or QApplication([])
    item = QGraphicsTextItem("Stable")

    set_committed_note_text_for(item, "Stable")

    assert committed_note_text_for(item) == "Stable"
    assert not hasattr(item, "_last_text")
    app.processEvents()
