from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS
from chemvas.shell.palette import PALETTE
from chemvas.ui.dialogs.arrow_label_editor import ArrowLabelEditor

if TYPE_CHECKING:
    from collections.abc import Callable


def _label_format_controls(
    layout: QVBoxLayout, active_field: Callable[[], ArrowLabelEditor]
) -> None:
    format_row = QHBoxLayout()

    def insert_symbol(symbol: str) -> None:
        field = active_field()
        field.insertPlainText(symbol)
        field.setFocus(Qt.FocusReason.OtherFocusReason)

    for title, role, key in (
        ("Subscript x₂", "sub", "Subscript"),
        ("Superscript x²", "super", "Superscript"),
    ):
        button = QToolButton()
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        button.setText(title)
        button.setObjectName(f"arrowLabel{key}")
        button.setAccessibleName(f"Label {key.lower()}")
        button.setToolTip(f"Toggle {key.lower()}")

        def toggle(checked=False, role=role) -> None:
            field = active_field()
            field.toggle_script(role)
            field.setFocus(Qt.FocusReason.OtherFocusReason)

        button.clicked.connect(toggle)
        format_row.addWidget(button)

    symbols = QToolButton()
    symbols.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    symbols.setText("Symbols")
    symbols.setObjectName("arrowLabelSymbols")
    symbols.setAccessibleName("Label symbols")
    symbols.setStyleSheet(
        "QToolButton { padding-right: 22px; }"
        "QToolButton::menu-indicator { subcontrol-origin: padding;"
        " subcontrol-position: right center; right: 6px; }"
    )
    symbols.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(symbols)
    for symbol, description in (
        ("Δ", "Delta / heat"),
        ("°", "Degree"),
        ("±", "Plus or minus"),
        ("‡", "Transition state"),
        ("→", "Right arrow"),
        ("⇌", "Equilibrium"),
    ):
        action = QAction(f"{symbol}  {description}", menu)
        menu.addAction(action)
        action.triggered.connect(
            lambda checked=False, symbol=symbol: insert_symbol(symbol)
        )
    symbols.setMenu(menu)
    format_row.addWidget(symbols)
    format_row.addStretch(1)
    layout.insertLayout(0, format_row)


def _label_input(
    layout: QVBoxLayout, caption: str, name: str, text: str
) -> ArrowLabelEditor:
    caption_label = QLabel(caption)
    layout.addWidget(caption_label)
    field = ArrowLabelEditor(text)
    field.setStyleSheet(
        f"QTextEdit {{ background: {PALETTE['surface_input']};"
        f" color: {PALETTE['text']}; border: 1px solid {PALETTE['border_strong']};"
        " border-radius: 8px; padding: 4px 7px;"
        f" selection-background-color: {PALETTE['checked_bg']};"
        f" selection-color: {PALETTE['checked_text']}; }}"
        f"QTextEdit:focus {{ border-color: {PALETTE['accent']}; }}"
    )
    field.setPlaceholderText(f"Up to {MAX_ARROW_LABEL_CHARS} characters")
    field.setObjectName(name)
    field.setAccessibleName(f"{caption.removesuffix(':')} label")
    caption_label.setBuddy(field)
    field.setTabChangesFocus(True)
    field.setFixedHeight(field.fontMetrics().lineSpacing() * 3 + 20)
    layout.addWidget(field)
    validation_message = QLabel()
    validation_message.setObjectName(f"{name}Limit")
    validation_message.setTextFormat(Qt.TextFormat.PlainText)
    validation_message.setWordWrap(True)
    layout.addWidget(validation_message)

    def update_validation() -> None:
        error = ""
        try:
            if len(field.label_value()) > MAX_ARROW_LABEL_CHARS:
                error = "Label is too long."
        except ValueError as exc:
            error = str(exc)
        validation_message.setText(error)
        validation_message.setVisible(bool(error))

    field.textChanged.connect(update_validation)
    update_validation()
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
    active_input = above_input

    def activate(field: ArrowLabelEditor) -> None:
        nonlocal active_input
        active_input = field

    above_input.focused.connect(lambda: activate(above_input))
    below_input.focused.connect(lambda: activate(below_input))
    _label_format_controls(layout, lambda: active_input)
    QDialog.setTabOrder(above_input, below_input)

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
        return {"above": above_input.label_value(), "below": below_input.label_value()}

    def update_acceptance() -> None:
        try:
            valid = all(
                len(value) <= MAX_ARROW_LABEL_CHARS for value in label_values().values()
            )
        except ValueError:
            valid = False
        ok_btn.setEnabled(valid)

    above_input.textChanged.connect(update_acceptance)
    below_input.textChanged.connect(update_acceptance)
    update_acceptance()
    above_input.setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return label_values()


__all__ = ["prompt_arrow_labels"]
