from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None
    QGraphicsTextItem = None

from chemvas.ui.note_item_access import (
    apply_note_style_for,
    committed_note_text_for,
    set_committed_note_text_for,
)
from tests.runtime_services import canvas_runtime_services


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


def test_committed_note_text_rejects_objects_without_a_note_contract() -> None:
    class _PlainNote:
        pass

    item = _PlainNote()

    with pytest.raises(
        AttributeError, match=r"^Note item does not implement set_committed_text\(\)\.$"
    ):
        set_committed_note_text_for(item, "Stable")


def test_committed_note_text_uses_qgraphics_item_data_role() -> None:
    if QApplication is None:
        return
    app = QApplication.instance() or QApplication([])
    item = QGraphicsTextItem("Stable")

    set_committed_note_text_for(item, "Stable")

    assert committed_note_text_for(item) == "Stable"
    assert not hasattr(item, "_last_text")
    app.processEvents()


def test_note_style_access_requires_and_delegates_to_note_controller() -> None:
    calls = []
    controller = SimpleNamespace(
        apply_note_style=lambda item: calls.append(("apply", item)),
    )
    canvas = SimpleNamespace(
        services=canvas_runtime_services(note_controller=controller),
    )
    item = object()

    apply_note_style_for(canvas, item)

    assert calls == [("apply", item)]

    with pytest.raises(AttributeError):
        apply_note_style_for(SimpleNamespace(), item)
