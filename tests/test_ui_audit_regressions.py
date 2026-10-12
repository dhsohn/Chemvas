"""User-facing regressions from the macOS 0.21 usage audit."""

from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QPalette, QStatusTipEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
)

from chemvas.domain.document import Atom, Bond, MoleculeModel, serialize_model_state
from chemvas.shell.palette import PALETTE
from chemvas.ui.dialogs.arrow_label_dialog import _label_input
from chemvas.ui.window.main_window_document_dialogs import prompt_export_options
from tests.calculation_plan_support import _document_state
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def _settle(app) -> None:
    # Showing or hiding a context label lays the status bar out on a later pass.
    for _ in range(3):
        app.processEvents()


def _context_in_yield_order(status) -> tuple[QLabel, ...]:
    return (
        status.zoom_caption,
        status.tool_label,
        status.sheet_label,
        status.selection_label,
    )


def test_feedback_has_space_and_pending_recovery_returns(drawing, app):
    window, _canvas = drawing
    window.resize(727, 542)
    status = window.services.status_service
    label = status.autosave_error_label
    context = _context_in_yield_order(status)
    notice = "Recovery available: use File → Recover Unsaved Work to restore drawings."
    status.set_recovery_notice(window, notice)
    _settle(app)
    # The context the notice leaves at this width, which feedback must restore.
    shown = [context_label.isVisible() for context_label in context]
    status.show_error_message(
        window, "Invalid atom label: check the drawing", timeout=10_000
    )
    app.processEvents()
    assert label.isVisible()
    assert label.width() <= 160
    assert not any(context_label.isVisible() for context_label in context)
    bar = window.statusBar()
    assert status.grid_button.x() > bar.fontMetrics().horizontalAdvance(
        bar.currentMessage()
    )
    # A new persistent warning must not take the space back during feedback.
    status.set_autosave_error(window, "Autosave paused: disk full")
    assert label.isVisible()
    assert not any(context_label.isVisible() for context_label in context)
    # Start expiry only after checking the live feedback layout. CI timer
    # delivery can exceed a fixed sleep; wait for the observed UI transition.
    hint = status.active_tool_hint_text(window)
    bar.showMessage(bar.currentMessage(), 1)
    for _ in range(100):
        if bar.currentMessage() == hint:
            break
        QTest.qWait(20)
    assert bar.currentMessage() == hint
    _settle(app)
    # The context returns around the notice, which keeps its compact width.
    assert [context_label.isVisible() for context_label in context] == shown
    assert label.width() == label.compact_width()
    assert label.painted_text().startswith("Autosave paused")
    assert notice in label.text()
    status.set_autosave_error(window, None)
    _settle(app)
    assert [context_label.isVisible() for context_label in context] == shown
    assert label.isVisible()
    assert notice in label.text()


def test_paused_autosave_and_quit_are_painted_ahead_of_recovery_guidance(drawing, app):
    window, _canvas = drawing
    status = window.services.status_service
    label = status.autosave_error_label
    recovery = (
        "Unsaved work is available. Choose File → Recover Unsaved Work… to open copies."
    )
    failures = (
        (
            status.set_autosave_error,
            "Autosave paused",
            "Autosave paused: [Errno 28] No space left on device",
        ),
        (
            status.set_quit_notice,
            "Quit paused",
            "Quit paused: the open windows changed. Try Quit again.",
        ),
    )
    for width in (1120, 727):
        window.resize(width, 542)
        status.set_recovery_notice(window, recovery)
        for set_notice, headline, message in failures:
            set_notice(window, message)
            _settle(app)
            assert label.painted_text().startswith(headline), (
                width,
                label.painted_text(),
            )
            assert recovery in label.toolTip()
            set_notice(window, None)
            _settle(app)
            assert label.text() == recovery


def test_notices_take_only_the_context_space_they_need(drawing, app):
    window, _canvas = drawing
    status = window.services.status_service
    bar = window.statusBar()
    label = status.autosave_error_label
    context = _context_in_yield_order(status)
    guidance = (
        "Unsaved work is available. Choose File → Recover Unsaved Work… to open copies."
    )
    # Every status item and the notice at its maximum width fit in this window.
    roomy = (
        bar.sizeHint().width()
        + label.maximumWidth()
        + status.recovery_button.sizeHint().width()
        + 50
    )
    status.set_recovery_notice(window, guidance)
    window.resize(roomy, 542)
    _settle(app)
    assert all(context_label.isVisible() for context_label in context)
    # Narrowing the window by the narrowest context label's width hides at
    # most one more label: the notice takes only the space it is short of.
    step = min(context_label.sizeHint().width() for context_label in context)
    previous = len(context)
    for width in range(roomy - step, window.minimumSizeHint().width() - 1, -step):
        window.resize(width, 542)
        _settle(app)
        shown = [context_label.isVisible() for context_label in context]
        assert previous - sum(shown) <= 1, (width, previous, shown)
        previous = sum(shown)
        # The context labels give up their space in order.
        assert shown == sorted(shown), (width, shown)
        # A context label stays only while the notice keeps its compact width.
        if any(shown):
            assert label.width() == label.compact_width(), (width, label.width())
        if label.width() == label.compact_width():
            assert label.painted_text().startswith("Unsaved work"), (
                width,
                label.painted_text(),
            )
    status.set_recovery_notice(window, None)
    _settle(app)
    assert all(context_label.isVisible() for context_label in context)


def test_zoom_hints_follow_native_shortcuts_and_survive_refresh(drawing):
    window, _canvas = drawing
    status = window.services.status_service
    for button, key in (
        (status.zoom_in_button, "Ctrl++"),
        (status.zoom_out_button, "Ctrl+-"),
    ):
        assert (
            QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
            in button.toolTip()
        )
    for percent in (175, 100, 20):
        status.update_zoom_label(percent)
        assert f"{percent}%" in status.zoom_label.toolTip()
        assert "Space to reset to 100%" in status.zoom_label.toolTip()
        assert "double-click or Enter" in status.zoom_label.statusTip()


def test_arrow_preview_uses_paper_colors_with_dark_system_palette(app):
    dialog = QDialog()
    dark = QPalette(dialog.palette())
    dark.setColor(QPalette.ColorRole.Window, QColor("#202020"))
    dark.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
    dialog.setPalette(dark)
    _label_input(
        QVBoxLayout(dialog), "Above:", "arrowLabelAboveInput", "K_{2}CO_{3}\nΔG^{‡}"
    )
    dialog.show()
    app.processEvents()
    preview = dialog.findChild(QLabel, "arrowLabelAbovePreview")
    viewport = dialog.findChild(QScrollArea).viewport()
    assert preview.palette().color(QPalette.ColorRole.WindowText) == QColor(
        PALETTE["text"]
    )
    assert preview.palette().color(QPalette.ColorRole.Window) == QColor(
        PALETTE["surface_canvas"]
    )
    assert viewport.palette().color(QPalette.ColorRole.Window) == QColor(
        PALETTE["surface_canvas"]
    )
    assert "<sub>2</sub>" in preview.text()
    dialog.close()


def test_mol_alias_refusal_shows_actionable_error_without_changing_document(
    drawing, tmp_path
):
    window, canvas = drawing
    state = _document_state()
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 7: Atom("OH", 20, 0)},
        bonds=[Bond(0, 7, order=1)],
    )
    model.atom_annotations = {7: {"formal_charge": 1}}
    state["model"] = serialize_model_state(model)
    state["marks"] = [
        {
            "kind": "plus",
            "text": "+",
            "atom_id": 7,
            "dx": 8.0,
            "dy": -8.0,
            "x": 28.0,
            "y": -8.0,
        }
    ]
    session = canvas.services.canvas_document_session_service
    session.apply_state(state)
    before = session.snapshot_state()
    output = tmp_path / "drawing.mol"
    picker, message_box = Mock(), Mock()
    picker.getSaveFileName.return_value = (str(output), "MDL Molfile (*.mol)")
    window.services.document_action_service.export_mol(
        window, file_dialog=picker, message_box=message_box
    )
    message_box.warning.assert_called_once()
    message = message_box.warning.call_args.args[2]
    assert "OH" in message
    assert "Replace them with explicit element atoms" in message
    assert not output.exists()
    assert session.snapshot_state() == before


def test_export_options_survive_retry_and_cancelled_edits(drawing, monkeypatch):
    window, _canvas = drawing

    def choose(dialog):
        size = dialog.findChild(QComboBox, "exportSizeCombo")
        size.setCurrentIndex(size.findData("custom"))
        dialog.findChild(QDoubleSpinBox, "exportWidthSpin").setValue(83.75)
        dialog.findChild(QCheckBox, "exportMinFontCheck").setChecked(True)
        dialog.findChild(QDoubleSpinBox, "exportMinFontSpin").setValue(72)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", choose)
    original = prompt_export_options(window)

    def reopen(dialog):
        assert dialog.findChild(QDoubleSpinBox, "exportWidthSpin").value() == 83.75
        assert dialog.findChild(QCheckBox, "exportMinFontCheck").isChecked()
        assert dialog.findChild(QDoubleSpinBox, "exportMinFontSpin").value() == 72
        dialog.findChild(QDoubleSpinBox, "exportMinFontSpin").setValue(6)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", reopen)
    assert prompt_export_options(window) is None
    assert window.runtime_state.last_export_options == original


def test_notice_text_in_the_message_area_is_ordinary_feedback(drawing):
    window, _canvas = drawing
    status = window.services.status_service
    bar = window.statusBar()
    warning = "Some recovery files could not be opened; originals have been kept."
    status.set_recovery_notice(window, warning)
    label = status.autosave_error_label
    assert status.sheet_label.isVisible()
    # Hovering the compact notice reads its full text in the message area.
    QApplication.sendEvent(label, QStatusTipEvent(label.statusTip()))
    assert bar.currentMessage() == warning
    assert not status.sheet_label.isVisible()
    QApplication.sendEvent(label, QStatusTipEvent(""))
    assert bar.currentMessage() == status.active_tool_hint_text(window)
    assert status.sheet_label.isVisible()
    assert status.tool_label.isVisible()
    assert status.selection_label.isVisible()
    assert status.zoom_caption.isVisible()
    assert label.isVisible()


def test_recovery_action_is_keyboard_accessible_and_preserves_feedback(
    drawing, app, monkeypatch
):
    from chemvas.ui.window import main_window_status_service as status_module

    window, _canvas = drawing
    status = window.services.status_service
    calls = []
    monkeypatch.setattr(status_module, "recover_unsaved_work_for_window", calls.append)
    message = "Unsaved work is available. Choose File → Recover Unsaved Work…"
    status.set_recovery_notice(window, message)
    _settle(app)
    button = status.recovery_button
    assert button.isVisible()
    assert button.text() == "Recover…"
    assert button.accessibleDescription() == message
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert calls == [window]
    status.set_autosave_error(window, "Autosave paused: disk full")
    window.statusBar().showMessage("Invalid atom label")
    _settle(app)
    assert button.isVisible()
    assert "disk full" in status.autosave_error_label.text()
    assert window.statusBar().currentMessage() == "Invalid atom label"
    status.set_recovery_notice(window, None)
    assert button.isHidden()
    assert "disk full" in status.autosave_error_label.text()


def test_flip_hints_use_platform_native_modifiers(drawing):
    from PyQt6.QtGui import QAction

    window, _canvas = drawing
    for name, title, key in (
        ("flip_horizontal_button", "Flip Horizontal", "Ctrl+Shift+H"),
        ("flip_vertical_button", "Flip Vertical", "Ctrl+Shift+V"),
    ):
        native = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
        button = window.findChild(QToolButton, name)
        assert native in button.toolTip()
        action = next(a for a in window.findChildren(QAction) if a.text() == title)
        assert native in action.statusTip()
