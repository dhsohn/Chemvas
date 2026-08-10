from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QInputMethodEvent
    from PyQt6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QDialog,
        QLineEdit,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.features.calculation_bundle import (
        calculation_plan_for_document,
        step_readiness,
    )
    from chemvas.ui.calculation_step_dialog import CalculationStepDialog

from tests.test_calculation_plan import _document_state, _plan


def _select_component(
    dialog: CalculationStepDialog,
    side: str,
    row: int,
    inclusion: str,
    role: str,
) -> None:
    dialog._set_combo_data(dialog._inclusion_combos[(side, row)], inclusion)
    dialog._set_combo_data(dialog._role_combos[(side, row)], role)


def _configure_separate_endpoints(dialog: CalculationStepDialog) -> None:
    _select_component(dialog, "reactant", 0, "included", "reactant")
    _select_component(dialog, "reactant", 2, "included", "catalyst")
    _select_component(dialog, "reactant", 3, "context_only", "spectator")
    _select_component(dialog, "product", 1, "included", "product")
    _select_component(dialog, "product", 2, "included", "catalyst")
    _select_component(dialog, "product", 3, "context_only", "spectator")


def _set_mapping(
    dialog: CalculationStepDialog,
    reactant_atom_id: int,
    product_atom_id: int | None,
) -> None:
    combo = dialog._mapping_combos[reactant_atom_id]
    index = combo.findData(product_atom_id)
    assert index >= 0
    combo.setCurrentIndex(index)


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_assigns_roles_in_one_document_and_saves_draft_mapping() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    dialog = CalculationStepDialog(state)

    assert "Draft mapping" in dialog.mapping_status.text()
    assert "ready for pack-step" not in dialog.mapping_status.text()
    _configure_separate_endpoints(dialog)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_plan_state is not None
    state["calculation_plan"] = dialog.result_plan_state
    plan = calculation_plan_for_document(state)
    step = plan.steps[0]
    readiness = step_readiness(plan, step)
    assert step.reactant.roles[0].role == "reactant"
    assert step.product.roles[0].role == "product"
    assert step.reactant.roles[2].role == "spectator"
    assert [entry.reactant_atom_id for entry in step.atom_correspondence] == [4]
    assert readiness.mapping_complete is False
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_maps_separately_drawn_endpoints_and_becomes_step_ready() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    dialog = CalculationStepDialog(state)
    _configure_separate_endpoints(dialog)

    assert set(dialog._mapping_combos) == {0, 1, 4}
    assert dialog._mapping_by_reactant[4] == 4
    assert dialog._mapping_combos[0].findData(3) == -1
    assert dialog._mapping_combos[1].findData(2) == -1
    _set_mapping(dialog, 0, 2)
    _set_mapping(dialog, 1, 3)

    assert "ready for pack-step" in dialog.mapping_status.text()
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_plan_state is not None
    state["calculation_plan"] = dialog.result_plan_state
    plan = calculation_plan_for_document(state)
    step = plan.steps[0]
    assert [
        (entry.reactant_atom_id, entry.product_atom_id)
        for entry in step.atom_correspondence
    ] == [(0, 2), (1, 3), (4, 4)]
    assert step_readiness(plan, step).ready_for_step_pack is True
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_preserves_mapping_across_inclusion_toggle_and_respects_unmapped() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    dialog = CalculationStepDialog(state)
    _configure_separate_endpoints(dialog)
    _set_mapping(dialog, 0, 2)
    _set_mapping(dialog, 1, 3)

    _select_component(dialog, "reactant", 0, "unused", "reactant")
    _select_component(dialog, "reactant", 0, "included", "reactant")
    assert dialog._mapping_combos[0].currentData() == 2
    _select_component(dialog, "product", 1, "unused", "product")
    row = dialog._mapping_row_by_reactant[0]
    assert dialog.mapping_table.item(row, 2).text() == "Unmapped"
    _select_component(dialog, "product", 1, "included", "product")
    assert dialog._mapping_combos[0].currentData() == 2

    _set_mapping(dialog, 4, None)
    _select_component(dialog, "reactant", 3, "unused", "spectator")
    _select_component(dialog, "reactant", 3, "context_only", "spectator")
    assert dialog._mapping_combos[4].currentData() is None
    assert "Draft mapping" in dialog.mapping_status.text()

    dialog.accept()

    assert dialog.result_plan_state is not None
    state["calculation_plan"] = dialog.result_plan_state
    plan = calculation_plan_for_document(state)
    assert [
        (entry.reactant_atom_id, entry.product_atom_id)
        for entry in plan.steps[0].atom_correspondence
    ] == [(0, 2), (1, 3)]
    assert step_readiness(plan, plan.steps[0]).ready_for_step_pack is False
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_loads_existing_mapping_exactly_and_allows_removing_one() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    state["calculation_plan"] = _plan()
    dialog = CalculationStepDialog(state)

    dialog.step_selector.setCurrentIndex(1)

    assert dialog._mapping_combos[0].currentData() == 2
    assert dialog._mapping_combos[1].currentData() == 3
    assert dialog._mapping_combos[4].currentData() == 4
    _set_mapping(dialog, 0, None)
    dialog.accept()

    assert dialog.result_plan_state is not None
    state["calculation_plan"] = dialog.result_plan_state
    plan = calculation_plan_for_document(state)
    assert [
        (entry.reactant_atom_id, entry.product_atom_id)
        for entry in plan.steps[0].atom_correspondence
    ] == [(1, 3), (4, 4)]
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_rejects_duplicate_product_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    model = state["model"]
    assert isinstance(model, dict)
    atoms = model["atoms"]
    assert isinstance(atoms, dict)
    atoms[1]["element"] = "C"
    atoms[3]["element"] = "C"
    dialog = CalculationStepDialog(state)
    _configure_separate_endpoints(dialog)
    _set_mapping(dialog, 0, 2)
    _set_mapping(dialog, 1, 2)
    warnings: list[str] = []
    monkeypatch.setattr(
        "chemvas.ui.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    assert "repeated" in dialog.mapping_status.text()
    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.result_plan_state is None
    assert warnings
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_new_mode_rejects_existing_step_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    state["calculation_plan"] = _plan()
    dialog = CalculationStepDialog(state)
    dialog.step_id.setText("S01")
    warnings: list[str] = []
    monkeypatch.setattr(
        "chemvas.ui.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.result_plan_state is None
    assert warnings == ["Step S01 already exists. Select Edit S01 instead."]
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_preserves_product_atom_id_zero() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    dialog = CalculationStepDialog(state)
    _select_component(dialog, "reactant", 1, "included", "reactant")
    _select_component(dialog, "product", 0, "included", "product")
    _set_mapping(dialog, 2, 0)
    _set_mapping(dialog, 3, 1)

    assert dialog._mapping_combos[2].currentData() == 0
    dialog.accept()

    assert dialog.result_plan_state is not None
    state["calculation_plan"] = dialog.result_plan_state
    plan = calculation_plan_for_document(state)
    assert [
        (entry.reactant_atom_id, entry.product_atom_id)
        for entry in plan.steps[0].atom_correspondence
    ] == [(2, 0), (3, 1)]
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_does_not_replace_explicit_unmapped_when_id_becomes_shared() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    _select_component(dialog, "reactant", 0, "included", "reactant")
    _select_component(dialog, "product", 1, "included", "product")
    _set_mapping(dialog, 0, 2)
    _set_mapping(dialog, 0, None)

    _select_component(dialog, "product", 0, "included", "product")

    assert dialog._mapping_by_reactant[0] is None
    assert dialog._mapping_combos[0].currentData() is None
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_identity_seed_ignores_inactive_stashed_mapping() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    model = state["model"]
    assert isinstance(model, dict)
    atoms = model["atoms"]
    assert isinstance(atoms, dict)
    atoms[5]["element"] = "Pt"
    dialog = CalculationStepDialog(state)
    _select_component(dialog, "reactant", 3, "included", "reactant")
    _select_component(dialog, "product", 2, "included", "product")
    _set_mapping(dialog, 5, 4)
    _select_component(dialog, "reactant", 3, "unused", "reactant")

    _select_component(dialog, "reactant", 2, "included", "reactant")

    assert dialog._mapping_combos[4].currentData() == 4
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_clear_and_identity_buttons_update_active_mappings() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    _configure_separate_endpoints(dialog)

    dialog.clear_mapping_button.click()
    assert {atom_id: dialog._mapping_by_reactant[atom_id] for atom_id in (0, 1, 4)} == {
        0: None,
        1: None,
        4: None,
    }

    dialog.identity_mapping_button.click()
    assert dialog._mapping_by_reactant[0] is None
    assert dialog._mapping_by_reactant[1] is None
    assert dialog._mapping_by_reactant[4] == 4
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_rejects_context_only_component_with_reactive_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    dialog._set_combo_data(dialog._inclusion_combos[("reactant", 0)], "context_only")
    # Programmatically restore an invalid choice after the UI's safety default.
    dialog._set_combo_data(dialog._role_combos[("reactant", 0)], "reactant")
    dialog._set_combo_data(dialog._inclusion_combos[("reactant", 2)], "included")
    dialog._set_combo_data(dialog._role_combos[("reactant", 2)], "catalyst")
    dialog._set_combo_data(dialog._inclusion_combos[("product", 1)], "included")
    warnings: list[str] = []
    monkeypatch.setattr(
        "chemvas.ui.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    dialog.accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert any("context-only" in warning for warning in warnings)
    dialog.deleteLater()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_highlights_rows_candidates_and_clears_on_reject() -> None:
    class _Highlighter:
        def __init__(self) -> None:
            self.shown: list[tuple[int, int | None]] = []
            self.clear_count = 0

        def show_mapping(
            self,
            reactant_atom_id: int,
            product_atom_id: int | None,
        ) -> None:
            self.shown.append((reactant_atom_id, product_atom_id))

        def clear(self) -> None:
            self.clear_count += 1

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    highlighter = _Highlighter()
    dialog = CalculationStepDialog(
        _document_state(),
        mapping_highlighter=highlighter,
    )
    _configure_separate_endpoints(dialog)
    clear_count_after_refresh = highlighter.clear_count

    row = dialog._mapping_row_by_reactant[0]
    dialog.mapping_table.setCurrentCell(row, 0)
    assert highlighter.shown[-1] == (0, None)

    combo = dialog._mapping_combos[0]
    product_index = combo.findData(2)
    combo.highlighted.emit(product_index)
    assert highlighter.shown[-1] == (0, 2)
    combo.hidePopup()
    assert highlighter.shown[-1] == (0, None)

    _set_mapping(dialog, 0, 2)
    assert highlighter.shown[-1] == (0, 2)
    dialog.reject()

    assert highlighter.clear_count > clear_count_after_refresh
    dialog.deleteLater()


def test_window_editor_injects_and_finally_clears_canvas_highlighter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import chemvas.ui.calculation_step_dialog as dialog_module

    window = object()
    canvas = object()
    instances: list[object] = []

    class _Highlighter:
        def __init__(self, active_canvas: object) -> None:
            self.canvas = active_canvas
            self.clear_count = 0
            instances.append(self)

        def clear(self) -> None:
            self.clear_count += 1

    class _Dialog:
        result_plan_state = None

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

    received: dict[str, object] = {}

    def factory(document_state, **kwargs):
        received["document_state"] = document_state
        received.update(kwargs)
        return _Dialog()

    monkeypatch.setattr(dialog_module, "CalculationMappingHighlighter", _Highlighter)
    monkeypatch.setattr(
        dialog_module,
        "active_canvas_for_window",
        lambda _window: canvas,
    )
    monkeypatch.setattr(
        dialog_module,
        "document_session_service_for_window",
        lambda _window: SimpleNamespace(snapshot_state=_document_state),
    )

    assert (
        dialog_module.edit_calculation_plan_for_window(
            window,
            dialog_factory=factory,
        )
        is False
    )
    assert received["parent"] is window
    assert received["mapping_highlighter"] is instances[0]
    assert instances[0].canvas is canvas
    assert instances[0].clear_count == 1


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_dialog_tables_reject_input_method_cell_editing() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    _configure_separate_endpoints(dialog)
    dialog.show()

    no_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    assert dialog.table.editTriggers() == no_triggers
    assert dialog.mapping_table.editTriggers() == no_triggers

    # Composition events must be ignored for every cell kind. An item cell
    # could open a phantom editor, and for a cell hosting a combo widget
    # QAbstractItemView::edit focuses the widget before consulting the edit
    # triggers. Either reaction moves focus, and on Wayland the text input
    # re-delivers the composition event on each focus change — that mutual
    # recursion crashed the app under WSLg with a Korean IME (twice: once
    # per cell kind).
    mapping_row = dialog._mapping_row_by_reactant[0]
    for table, row, column in (
        (dialog.table, 0, 2),
        (dialog.mapping_table, mapping_row, 1),
        (dialog.table, 0, 0),
        (dialog.mapping_table, mapping_row, 0),
    ):
        table.setCurrentCell(row, column)
        table.setFocus()
        focus_before = app.focusWidget()
        preedit = QInputMethodEvent("ㅎ", [])
        app.sendEvent(table, preedit)
        commit = QInputMethodEvent()
        commit.setCommitString("하")
        app.sendEvent(table, commit)
        assert not preedit.isAccepted()
        assert not commit.isAccepted()
        assert app.focusWidget() is focus_before
        viewport = table.viewport()
        assert viewport is not None
        assert viewport.findChild(QLineEdit) is None
    dialog.deleteLater()
