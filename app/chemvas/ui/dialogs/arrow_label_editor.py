"""Visual label editor backed by the existing arrow-label storage contract."""

from __future__ import annotations

from typing import Any, override

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFocusEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from chemvas.features.annotations import (
    LabelRun,
    parse_arrow_label,
    serialize_arrow_label,
)

_ALIGNMENTS = {
    "normal": QTextCharFormat.VerticalAlignment.AlignNormal,
    "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
    "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
}


class ArrowLabelEditor(QTextEdit):
    focused = pyqtSignal()

    def __init__(self, source: str) -> None:
        super().__init__()
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        cursor = self.textCursor()
        for run in parse_arrow_label(source):
            format_ = QTextCharFormat()
            format_.setVerticalAlignment(_ALIGNMENTS[run.role])
            cursor.insertText(
                run.text.replace("\r\n", "\n").replace("\r", "\n"), format_
            )
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        document = self.document()
        assert document is not None
        document.clearUndoRedoStacks()
        self._original = source
        self._initial_runs = self.label_runs()

    @override
    def focusInEvent(self, event: QFocusEvent | None) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def label_runs(self) -> tuple[LabelRun, ...]:
        runs: list[LabelRun] = []

        def append(text: str, format_: QTextCharFormat) -> None:
            if not text:
                return
            role = next(
                (
                    key
                    for key, value in _ALIGNMENTS.items()
                    if format_.verticalAlignment() == value
                ),
                "normal",
            )
            if runs and runs[-1].role == role:
                runs[-1] = LabelRun(runs[-1].text + text, role)
            else:
                runs.append(LabelRun(text, role))

        document = self.document()
        assert document is not None
        block = document.begin()
        while block.isValid():
            iterator: Any = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    append(
                        fragment.text().replace("\u2028", "\n"), fragment.charFormat()
                    )
                iterator += 1
            block = block.next()
            if block.isValid():
                append("\n", block.charFormat())
        return tuple(runs)

    def label_value(self) -> str:
        runs = self.label_runs()
        if runs == self._initial_runs:
            return self._original
        return serialize_arrow_label(runs)

    def toggle_script(self, role: str) -> None:
        cursor = self.textCursor()
        target = _ALIGNMENTS[role]
        if cursor.hasSelection():
            probe = QTextCursor(cursor)
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            all_selected = True
            for position in range(start, end):
                probe.setPosition(position)
                probe.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
                if probe.charFormat().verticalAlignment() != target:
                    all_selected = False
                    break
        else:
            all_selected = self.currentCharFormat().verticalAlignment() == target
        format_ = QTextCharFormat()
        format_.setVerticalAlignment(_ALIGNMENTS["normal"] if all_selected else target)
        cursor.beginEditBlock()
        self.mergeCurrentCharFormat(format_)
        cursor.endEditBlock()
