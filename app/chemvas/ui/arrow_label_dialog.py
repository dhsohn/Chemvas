from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS

LABEL_SYNTAX_HINT = (
    "_ starts a subscript and ^ a superscript; braces group several characters "
    "(k_-1, K_{eq}, ΔG^‡). Leave a field empty to remove that label."
)


def _label_input(layout: QVBoxLayout, caption: str, name: str, text: str) -> QLineEdit:
    layout.addWidget(QLabel(caption))
    field = QLineEdit()
    field.setObjectName(name)
    field.setMaxLength(MAX_ARROW_LABEL_CHARS)
    field.setText(text)
    layout.addWidget(field)
    return field


def prompt_arrow_labels(parent, *, above: str, below: str) -> dict[str, str] | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Arrow Labels")
    dialog.setStyleSheet(parent.window().styleSheet())
    layout = QVBoxLayout(dialog)

    above_input = _label_input(layout, "Above:", "arrowLabelAboveInput", above)
    below_input = _label_input(layout, "Below:", "arrowLabelBelowInput", below)
    hint = QLabel(LABEL_SYNTAX_HINT)
    hint.setWordWrap(True)
    layout.addWidget(hint)

    action_row = QHBoxLayout()
    action_row.addStretch(1)
    ok_btn = QPushButton("OK")
    cancel_btn = QPushButton("Cancel")
    action_row.addWidget(ok_btn)
    action_row.addWidget(cancel_btn)
    layout.addLayout(action_row)
    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)
    above_input.setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return {"above": above_input.text(), "below": below_input.text()}


__all__ = ["LABEL_SYNTAX_HINT", "prompt_arrow_labels"]
