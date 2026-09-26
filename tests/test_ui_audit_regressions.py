"""User-facing regressions from the macOS 0.21 usage audit."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

from chemvas.domain.document import Atom, Bond, MoleculeModel, serialize_model_state
from chemvas.shell.palette import PALETTE
from chemvas.ui.dialogs import calculation_plan_actions
from chemvas.ui.dialogs.arrow_label_dialog import _label_input
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from chemvas.ui.window.main_window_document_dialogs import prompt_export_options
from tests.calculation_plan_support import _document_state, _plan
from tests.gui_workflow_support import _tool
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing


def test_feedback_has_space_and_pending_recovery_returns(drawing, app):
    window, _canvas = drawing
    window.resize(727, 542)
    status = window.services.status_service
    notice = "Recovery available: use File → Recover Unsaved Work to restore drawings."
    status.set_recovery_notice(window, notice)
    status.show_error_message(
        window, "Invalid SMILES: check the structure", timeout=100
    )
    app.processEvents()
    assert status.autosave_error_label.isVisible()
    assert status.autosave_error_label.width() <= 160
    assert not status.sheet_label.isVisible()
    bar = window.statusBar()
    assert status.grid_button.x() > bar.fontMetrics().horizontalAdvance(
        bar.currentMessage()
    )
    # A new persistent warning must not take the space back during feedback.
    status.set_autosave_error(window, "Autosave paused: disk full")
    assert status.autosave_error_label.isVisible()
    QTest.qWait(150)
    assert status.autosave_error_label.isVisible()
    assert notice in status.autosave_error_label.text()
    assert "disk full" in status.autosave_error_label.toolTip()
    assert status.sheet_label.isVisible()


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


def test_narrow_toolbar_extension_exposes_smiles_input(drawing, app):
    window, _canvas = drawing
    _tool(window, "select")
    window.resize(727, 542)
    app.processEvents()
    bar = window.findChild(QToolBar, "contextOptionsBar")
    extension = bar.findChild(QToolButton, "qt_toolbar_ext_button")
    field = bar.findChild(QLineEdit, "contextSmilesInput")
    assert extension.isVisible()
    QTest.mouseClick(extension, Qt.MouseButton.LeftButton)
    QTest.qWait(250)
    assert field.isVisible()
    assert bar.rect().contains(field.mapTo(bar, field.rect().center()))
    field.setFocus()
    QTest.keyClicks(field, "CCO")
    assert field.text() == "CCO"
    QTest.mouseClick(extension, Qt.MouseButton.LeftButton)


def test_invalid_alias_shows_actionable_error_without_changing_document(
    drawing, monkeypatch
):
    window, _canvas = drawing
    state = _document_state()
    model = MoleculeModel(
        atoms={0: Atom("C", 0, 0), 7: Atom("OH", 20, 0)},
        bonds=[Bond(0, 7, order=1)],
    )
    model.atom_annotations = {7: {"formal_charge": 1}}
    state["model"] = serialize_model_state(model)
    state["marks"] = [{"kind": "plus", "atom_id": 7}]
    before = deepcopy(state)
    monkeypatch.setattr(
        calculation_plan_actions,
        "document_session_service_for_window",
        lambda _: SimpleNamespace(snapshot_state=lambda: state),
    )
    warning = Mock()
    factory = Mock()
    monkeypatch.setattr(calculation_plan_actions.QMessageBox, "warning", warning)
    assert not calculation_plan_actions.edit_calculation_plan_for_window(
        window, dialog_factory=factory
    )
    factory.assert_not_called()
    message = warning.call_args.args[2]
    assert "'OH' on atom 7" in message
    assert "use an element label" in message
    assert state == before


def test_mapping_status_remains_readable_after_rebuild_and_clear(app):
    state = _document_state()
    state["calculation_plan"] = _plan()
    dialog = CalculationStepDialog(state)
    dialog.resize(850, 800)
    dialog.show()
    for operation in (
        dialog._refresh_mapping_table,
        dialog._clear_active_mappings,
        dialog._refresh_mapping_table,
    ):
        operation()
        app.processEvents()
        table = dialog.mapping_table
        for row in range(table.rowCount()):
            item = table.item(row, 2)
            assert (
                table.columnWidth(2)
                >= table.fontMetrics().horizontalAdvance(item.text()) + 10
            )
        assert (
            sum(table.columnWidth(i) for i in range(3)) >= table.viewport().width() - 2
        )
    dialog.close()


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
