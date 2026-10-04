from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS
from chemvas.features.annotations import (
    ARROW_LABEL_PREVIEW_POINT_SIZE,
    LABEL_SYNTAX_HINT,
    arrow_label_html,
)
from chemvas.shell.palette import PALETTE


def _label_input(
    layout: QVBoxLayout, caption: str, name: str, text: str
) -> QPlainTextEdit:
    caption_label = QLabel(caption)
    layout.addWidget(caption_label)
    field = QPlainTextEdit()
    field.setObjectName(name)
    field.setAccessibleName(f"{caption.removesuffix(':')} label")
    caption_label.setBuddy(field)
    field.setTabChangesFocus(True)
    field.setPlainText(text)
    initial_text = field.toPlainText()
    field.setFixedHeight(field.fontMetrics().lineSpacing() * 3 + 12)
    layout.addWidget(field)
    counter = QLabel()
    counter.setObjectName(f"{name}Limit")
    counter.setTextFormat(Qt.TextFormat.PlainText)
    counter.setWordWrap(True)
    layout.addWidget(counter)

    preview = QLabel()
    preview.setObjectName(f"{name.removesuffix('Input')}Preview")
    preview.setAccessibleName(f"{caption.removesuffix(':')} label preview")
    preview.setTextFormat(Qt.TextFormat.RichText)
    preview.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    preview.setWordWrap(False)
    preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    preview_font = preview.font()
    preview_font.setPointSize(ARROW_LABEL_PREVIEW_POINT_SIZE)
    preview.setFont(preview_font)
    preview.setMargin(4)
    preview.setMinimumHeight(preview.fontMetrics().height() + 8)
    preview_area = QScrollArea()
    # Preview the paper surface, independent of the operating system's theme.
    preview.setStyleSheet(
        f"background: {PALETTE['surface_canvas']}; color: {PALETTE['text']};"
    )
    viewport = preview_area.viewport()
    if viewport is not None:
        viewport.setStyleSheet(f"background: {PALETTE['surface_canvas']};")
    preview_area.setWidget(preview)
    preview_area.setWidgetResizable(False)
    preview_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    preview_area.setFixedHeight(preview.fontMetrics().lineSpacing() * 2 + 16)
    preview_row = QHBoxLayout()
    preview_row.addWidget(QLabel("Preview:"))
    preview_row.addWidget(preview_area, 1)
    layout.addLayout(preview_row)

    def update_preview() -> None:
        value = field.toPlainText()
        count = len(text if value == initial_text else value)
        suffix = " — shorten before OK" if count > MAX_ARROW_LABEL_CHARS else ""
        counter.setText(f"{count}/{MAX_ARROW_LABEL_CHARS} characters{suffix}")
        preview.setText(arrow_label_html(value) if value else "No label")
        preview.adjustSize()

    field.textChanged.connect(update_preview)
    update_preview()
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
    initial_above = above_input.toPlainText()
    initial_below = below_input.toPlainText()
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

    def label_values() -> dict[str, str]:
        # Qt normalizes CRLF/CR while displaying plain text. An untouched label
        # keeps its original document bytes instead of creating an incidental edit.
        above_text = above_input.toPlainText()
        below_text = below_input.toPlainText()
        return {
            "above": above if above_text == initial_above else above_text,
            "below": below if below_text == initial_below else below_text,
        }

    def update_acceptance() -> None:
        ok_btn.setEnabled(
            all(
                len(value) <= MAX_ARROW_LABEL_CHARS for value in label_values().values()
            )
        )

    above_input.textChanged.connect(update_acceptance)
    below_input.textChanged.connect(update_acceptance)
    update_acceptance()
    above_input.setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return label_values()


__all__ = ["LABEL_SYNTAX_HINT", "prompt_arrow_labels"]
