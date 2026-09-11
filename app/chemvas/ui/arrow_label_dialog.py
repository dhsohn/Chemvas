from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS
from chemvas.features.annotations import arrow_label_html

LABEL_SYNTAX_HINT = (
    "Use _{...} for subscripts and ^{...} for superscripts. "
    "Examples: K_{2}CO_{3}, H_{2}SO_{4}, ΔG^{‡}.\n"
    "Without braces, _ or ^ applies until the next space, _ or ^. "
    "Braces do not nest and backslash escaping is not supported. "
    "A trailing _ or ^, or one followed by a space, is literal. "
    "Each field is limited to 200 characters; use a Note for longer text. "
    "Leave a field empty to remove that label."
)


def _label_input(layout: QVBoxLayout, caption: str, name: str, text: str) -> QLineEdit:
    caption_label = QLabel(caption)
    layout.addWidget(caption_label)
    field = QLineEdit()
    field.setObjectName(name)
    field.setAccessibleName(f"{caption.removesuffix(':')} label")
    caption_label.setBuddy(field)
    field.setMaxLength(MAX_ARROW_LABEL_CHARS)
    field.setText(text)
    layout.addWidget(field)
    counter = QLabel()
    counter.setObjectName(f"{name}Limit")
    counter.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(counter)

    preview = QLabel()
    preview.setObjectName(f"{name.removesuffix('Input')}Preview")
    preview.setAccessibleName(f"{caption.removesuffix(':')} label preview")
    preview.setTextFormat(Qt.TextFormat.RichText)
    preview.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    preview.setWordWrap(True)
    preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    preview_font = preview.font()
    preview_font.setPointSize(14)
    preview.setFont(preview_font)
    preview.setMargin(4)
    preview.setMinimumHeight(preview.fontMetrics().height() + 8)
    preview_row = QHBoxLayout()
    preview_row.addWidget(QLabel("Preview:"))
    preview_row.addWidget(preview, 1)
    layout.addLayout(preview_row)

    def update_preview(value: str) -> None:
        counter.setText(f"{len(value)}/{MAX_ARROW_LABEL_CHARS} characters")
        preview.setText(arrow_label_html(value) if value else "No label")

    field.textChanged.connect(update_preview)
    update_preview(field.text())
    return field


def prompt_arrow_labels(parent, *, above: str, below: str) -> dict[str, str] | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Arrow Labels")
    dialog.setStyleSheet(parent.window().styleSheet())
    dialog.setMinimumWidth(480)
    dialog.setMaximumWidth(640)
    layout = QVBoxLayout(dialog)

    above_input = _label_input(layout, "Above:", "arrowLabelAboveInput", above)
    below_input = _label_input(layout, "Below:", "arrowLabelBelowInput", below)
    hint = QLabel(LABEL_SYNTAX_HINT)
    hint.setTextFormat(Qt.TextFormat.PlainText)
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
