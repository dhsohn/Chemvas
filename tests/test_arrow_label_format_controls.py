"""Formatting controls preserve the field, cursor, undo and label limits."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QTextEdit,
    QToolButton,
)

from chemvas.domain.document import MAX_ARROW_LABEL_CHARS
from chemvas.features.annotations import LabelRun, parse_arrow_label
from chemvas.ui.dialogs.arrow_label_dialog import prompt_arrow_labels


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _run(monkeypatch, drive, above="", below=""):
    def execute(dialog):
        dialog.show()
        dialog.activateWindow()
        assert QTest.qWaitForWindowActive(dialog, 2000)
        drive(dialog)
        dialog.close()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", execute)
    parent = QDialog()
    return prompt_arrow_labels(parent, above=above, below=below)


def _field(dialog, side):
    field = dialog.findChild(QTextEdit, f"arrowLabel{side}Input")
    assert field is not None
    return field


def _button(dialog, side, control):
    button = dialog.findChild(QToolButton, f"arrowLabel{control}")
    assert button is not None
    assert button.accessibleName()
    return button


@pytest.mark.parametrize("side", ["Above", "Below"])
@pytest.mark.parametrize("control,token", [("Subscript", "_"), ("Superscript", "^")])
def test_format_selected_text_keeps_target_and_undo(
    app, monkeypatch, side, control, token
):
    def drive(dialog):
        field = _field(dialog, side)
        field.setFocus()
        field.setPlainText("K2CO3")
        cursor = field.textCursor()
        cursor.setPosition(1)
        cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
        field.setTextCursor(cursor)
        field.setFocus()
        QTest.mouseClick(_button(dialog, side, control), Qt.MouseButton.LeftButton)
        assert field.toPlainText() == "K2CO3"
        assert field.textCursor().selectedText() == "2"
        assert field.hasFocus()
        other = "Below" if side == "Above" else "Above"
        assert _field(dialog, other).toPlainText() == ""
        expected = (
            QTextCharFormat.VerticalAlignment.AlignSubScript
            if token == "_"
            else QTextCharFormat.VerticalAlignment.AlignSuperScript
        )
        assert field.textCursor().charFormat().verticalAlignment() == expected
        field.undo()
        assert field.toPlainText() == "K2CO3"
        field.redo()
        assert field.toPlainText() == "K2CO3"

    result = _run(monkeypatch, drive)
    assert result[side.lower()] == f"K{token}{{2}}CO3"


@pytest.mark.parametrize("side", ["Above", "Below"])
def test_empty_cursor_script_formats_typing_and_toggle_returns_to_baseline(
    app, monkeypatch, side
):
    def drive(dialog):
        field = _field(dialog, side)
        field.setFocus()
        QTest.keyClicks(field, "K")
        QTest.mouseClick(_button(dialog, side, "Subscript"), Qt.MouseButton.LeftButton)
        assert field.textCursor().position() == 1
        QTest.keyClicks(field, "2")
        assert field.toPlainText() == "K2"
        QTest.mouseClick(_button(dialog, side, "Subscript"), Qt.MouseButton.LeftButton)
        QTest.keyClicks(field, "O")
        assert field.toPlainText() == "K2O"

    assert _run(monkeypatch, drive)[side.lower()] == "K_{2}O"


@pytest.mark.parametrize("side", ["Above", "Below"])
@pytest.mark.parametrize(
    "index,symbol", list(enumerate(("Δ", "°", "±", "‡", "→", "⇌")))
)
def test_symbols_replace_selection_in_own_field(app, monkeypatch, side, index, symbol):
    def drive(dialog):
        field = _field(dialog, side)
        field.setFocus()
        field.setPlainText("heat")
        field.selectAll()
        symbols = _button(dialog, side, "Symbols")
        menu = symbols.menu()
        symbols.setFocus()
        menu.actions()[index].trigger()
        assert field.toPlainText() == symbol
        assert field.hasFocus()
        field.undo()
        assert field.toPlainText() == "heat"

    _run(monkeypatch, drive)


def test_script_preserves_unicode_and_multiline_selection(app, monkeypatch):
    def drive(dialog):
        field = _field(dialog, "Above")
        field.setFocus()
        field.setPlainText("😀\nβ")
        field.selectAll()
        _button(dialog, "Above", "Superscript").click()
        assert field.toPlainText() == "😀\nβ"
        assert field.label_runs() == (LabelRun("😀\nβ", "super"),)
        assert field.textCursor().selectedText() == "😀\u2029β"
        field.undo()
        assert field.toPlainText() == "😀\nβ"

    _run(monkeypatch, drive)


@pytest.mark.parametrize("source", ["MnO_2", "MnO_{2}", "MnO^2", "MnO^{2}"])
def test_existing_script_can_switch_reset_and_undo_to_exact_source(
    app, monkeypatch, source
):
    def drive(dialog):
        field = _field(dialog, "Above")
        field.setFocus()
        assert field.toPlainText() == "MnO2"
        cursor = field.textCursor()
        cursor.setPosition(3)
        cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
        field.setTextCursor(cursor)
        original = "Subscript" if "_" in source else "Superscript"
        other = "Superscript" if original == "Subscript" else "Subscript"
        _button(dialog, "Above", original).click()
        assert (
            field.textCursor().charFormat().verticalAlignment()
            == QTextCharFormat.VerticalAlignment.AlignNormal
        )
        _button(dialog, "Above", other).click()
        expected = (
            QTextCharFormat.VerticalAlignment.AlignSuperScript
            if other == "Superscript"
            else QTextCharFormat.VerticalAlignment.AlignSubScript
        )
        assert field.textCursor().charFormat().verticalAlignment() == expected
        field.undo()
        field.undo()
        assert field.toPlainText() == "MnO2"

    assert _run(monkeypatch, drive, above=source)["above"] == source


@pytest.mark.parametrize(
    "role,control", [("sub", "Subscript"), ("super", "Superscript")]
)
def test_formatting_unicode_multiline_persists_semantic_runs(
    app, monkeypatch, role, control
):
    def drive(dialog):
        field = _field(dialog, "Above")
        field.setFocus()
        field.setPlainText("😀\nβ")
        field.selectAll()
        _button(dialog, "Above", control).click()

    result = _run(monkeypatch, drive)
    assert parse_arrow_label(result["above"]) == (LabelRun("😀\nβ", role),)


@pytest.mark.parametrize("side", ["Above", "Below"])
def test_formatting_over_limit_blocks_ok_and_undo_recovers(app, monkeypatch, side):
    def drive(dialog):
        field = _field(dialog, side)
        field.setFocus()
        field.setPlainText("x" * MAX_ARROW_LABEL_CHARS)
        field.selectAll()
        ok = next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK")
        assert ok.isEnabled()
        _button(dialog, side, "Subscript").click()
        assert not ok.isEnabled()
        assert len(field.toPlainText()) == MAX_ARROW_LABEL_CHARS
        counter = dialog.findChild(QLabel, f"arrowLabel{side}InputLimit")
        assert not counter.isHidden()
        assert "too long" in counter.text()
        field.undo()
        assert ok.isEnabled()
        assert counter.isHidden()

    _run(monkeypatch, drive)


def test_help_and_example_removed_and_field_tab_order_survives(app, monkeypatch):
    def drive(dialog):
        hint = dialog.findChild(QLabel, "arrowLabelSyntaxHelp")
        toggle = dialog.findChild(QToolButton, "arrowLabelSyntaxToggle")
        assert hint is None
        assert toggle is None
        assert len(dialog.findChildren(QToolButton)) == 3
        assert dialog.findChild(QLabel, "arrowLabelAbovePreview") is None
        assert dialog.findChild(QLabel, "arrowLabelBelowPreview") is None
        assert not any(
            label.text() == "Preview:" for label in dialog.findChildren(QLabel)
        )
        assert not any(
            "Example:" in label.text() for label in dialog.findChildren(QLabel)
        )
        above, below = _field(dialog, "Above"), _field(dialog, "Below")
        above.setFocus()
        QTest.keyClick(above, Qt.Key.Key_Tab)
        assert below.hasFocus()
        QTest.keyClick(below, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert above.hasFocus()
        reachable = set()
        for _ in range(20):
            QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
            reachable.add(QApplication.focusWidget())
        for control in ("Subscript", "Superscript", "Symbols"):
            button = _button(dialog, "Above", control)
            assert button in reachable
            assert (
                button.mapTo(dialog, button.rect().bottomLeft()).y()
                < above.mapTo(dialog, above.rect().topLeft()).y()
            )

    assert _run(monkeypatch, drive, above="A\r\nB") == {"above": "A\r\nB", "below": ""}


@pytest.mark.parametrize("undo_format", [False, True])
def test_legacy_scripted_newline_preserves_bytes_when_other_label_changes(
    app, monkeypatch, undo_format
):
    source = "k_{a\r\nb}"

    def drive(dialog):
        above = _field(dialog, "Above")
        above.setFocus()
        assert above.toPlainText() == "ka\nb"
        assert above.label_runs() == (LabelRun("k", "normal"), LabelRun("a\nb", "sub"))
        if undo_format:
            above.selectAll()
            _button(dialog, "Above", "Superscript").click()
            above.undo()
        _field(dialog, "Below").setPlainText("DMSO\nrt")

    assert _run(monkeypatch, drive, above=source) == {
        "above": source,
        "below": "DMSO\nrt",
    }


def test_shared_toolbar_tracks_last_editor_and_preserves_selected_range(
    app, monkeypatch
):
    def drive(dialog):
        above, below = _field(dialog, "Above"), _field(dialog, "Below")
        above.setPlainText("H2O")
        below.setPlainText("Fe3+")
        shared = _button(dialog, "Above", "Subscript")
        assert shared is _button(dialog, "Below", "Subscript")
        for field, start, end in ((below, 2, 4), (above, 1, 2)):
            field.setFocus()
            cursor = field.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            field.setTextCursor(cursor)
            selected = cursor.selectedText()
            QTest.mouseClick(shared, Qt.MouseButton.LeftButton)
            assert field.hasFocus()
            assert field.textCursor().selectedText() == selected
            assert (
                field.textCursor().charFormat().verticalAlignment()
                == QTextCharFormat.VerticalAlignment.AlignSubScript
            )
        assert above.label_runs() == (
            LabelRun("H", "normal"),
            LabelRun("2", "sub"),
            LabelRun("O", "normal"),
        )
        assert below.label_runs() == (LabelRun("Fe", "normal"), LabelRun("3+", "sub"))

    result = _run(monkeypatch, drive)
    assert result == {"above": "H_{2}O", "below": "Fe_{3+}"}


def test_shared_toolbar_defaults_to_above_editor(app, monkeypatch):
    def drive(dialog):
        button = _button(dialog, "Above", "Superscript")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        field = _field(dialog, "Above")
        assert field.hasFocus()
        QTest.keyClicks(field, "2")
        assert _field(dialog, "Below").toPlainText() == ""

    assert _run(monkeypatch, drive) == {"above": "^{2}", "below": ""}
