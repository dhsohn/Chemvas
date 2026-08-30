from __future__ import annotations

import json
import os
from types import SimpleNamespace

from chemvas.bootstrap import calculation_bundle as calculation_bundle_cli
from chemvas.features.insertion import RDKitResult

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QInputMethodEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QLineEdit,
)

from chemvas.features.calculation_bundle import (
    calculation_plan_for_document,
    step_readiness,
)
from chemvas.ui.calculation_step_dialog import (
    CalculationStepDialog,
    _correspondence_suggester_for,
    _MappingProductCombo,
)
from tests.test_calculation_plan import _document_state, _plan
from tests.test_precomplex_cli import _generate_candidate_fixture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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


def test_reactant_role_disables_product_side_and_reenables_on_role_change() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())

    # Including a component as the reactant (default reactive role) locks the
    # same component's product side, and vice versa.
    _select_component(dialog, "reactant", 0, "included", "reactant")
    assert not dialog._inclusion_combos[("product", 0)].isEnabled()
    assert not dialog._role_combos[("product", 0)].isEnabled()
    assert dialog._inclusion_combos[("reactant", 0)].isEnabled()

    # The lock is visible, not just functional: both locked combos carry the
    # muted style and the lock explanation, while the active side stays plain.
    assert dialog._inclusion_combos[("product", 0)].styleSheet()
    assert dialog._role_combos[("product", 0)].styleSheet()
    assert "consumed species" in dialog._role_combos[("product", 0)].toolTip()
    assert not dialog._inclusion_combos[("reactant", 0)].styleSheet()

    # Turning that component into a catalyst re-enables the product side; the
    # lock is role-aware, not a blanket reactant-implies-off rule.
    dialog._set_combo_data(dialog._role_combos[("reactant", 0)], "catalyst")
    assert dialog._inclusion_combos[("product", 0)].isEnabled()
    assert not dialog._inclusion_combos[("product", 0)].styleSheet()
    assert not dialog._role_combos[("product", 0)].styleSheet()
    assert not dialog._role_combos[("product", 0)].toolTip()

    _select_component(dialog, "product", 1, "included", "product")
    assert not dialog._inclusion_combos[("reactant", 1)].isEnabled()
    assert dialog._inclusion_combos[("reactant", 1)].styleSheet()
    dialog.deleteLater()


def test_catalyst_included_on_both_sides_is_never_cleared() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())

    # A catalyst is included on both endpoints. The locking must only disable a
    # reactive component's opposite side, never clear a catalyst selection.
    _select_component(dialog, "reactant", 2, "included", "catalyst")
    _select_component(dialog, "product", 2, "included", "catalyst")

    assert dialog._inclusion_value("reactant", 2) == "included"
    assert dialog._inclusion_value("product", 2) == "included"
    assert dialog._inclusion_combos[("reactant", 2)].isEnabled()
    assert dialog._inclusion_combos[("product", 2)].isEnabled()

    # A context-only reactant is not consumed, so it does not lock the product.
    _select_component(dialog, "reactant", 3, "context_only", "spectator")
    assert dialog._inclusion_combos[("product", 3)].isEnabled()
    dialog.deleteLater()


def test_mapping_rows_and_used_candidates_read_muted() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    faint = "#9b9b96"

    # With no product included yet, the reactant rows have no candidate to map
    # to, so the atom text reads muted.
    _select_component(dialog, "reactant", 0, "included", "reactant")
    row = dialog._mapping_row_by_reactant[0]
    item = dialog.mapping_table.item(row, 0)
    assert item is not None
    assert item.foreground().color().name() == faint

    # A catalyst on both endpoints supplies same-element candidates; its
    # identity mapping is seeded automatically. Rows with candidates read
    # normal again.
    _select_component(dialog, "reactant", 1, "included", "catalyst")
    _select_component(dialog, "product", 1, "included", "catalyst")
    row = dialog._mapping_row_by_reactant[0]
    item = dialog.mapping_table.item(row, 0)
    assert item is not None
    assert item.foreground().color().name() != faint

    # Product atom 2 is identity-mapped by reactant 2, so in another row's
    # dropdown that candidate shows muted; the owning row's own dropdown keeps
    # it plain.
    assert dialog._mapping_by_reactant[2] == 2
    other_combo = dialog._mapping_combos[0]
    used_index = other_combo.findData(2)
    assert used_index >= 0
    foreground = other_combo.itemData(used_index, Qt.ItemDataRole.ForegroundRole)
    assert foreground is not None and foreground.color().name() == faint
    own_combo = dialog._mapping_combos[2]
    own_index = own_combo.findData(2)
    assert own_combo.itemData(own_index, Qt.ItemDataRole.ForegroundRole) is None

    # Unmapping frees the candidate everywhere.
    own_combo.setCurrentIndex(0)
    assert other_combo.itemData(used_index, Qt.ItemDataRole.ForegroundRole) is None
    dialog.deleteLater()


def test_suggest_button_disabled_without_a_suggester() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    assert not dialog.suggest_mapping_button.isEnabled()
    dialog.deleteLater()


def test_structural_suggestion_fills_only_safe_gaps() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    calls: list[tuple[frozenset[int], frozenset[int]]] = []

    def suggester(
        reactant_ids: frozenset[int], product_ids: frozenset[int]
    ) -> RDKitResult[list[tuple[int, int]]]:
        calls.append((reactant_ids, product_ids))
        # (0,2) fills an unmapped gap; (1,3) must not overwrite the existing
        # mapping; (0,3) would reuse a product already taken by (0,2).
        return RDKitResult([(0, 2), (1, 3), (0, 3)])

    state = _document_state()
    dialog = CalculationStepDialog(state, correspondence_suggester=suggester)
    assert dialog.suggest_mapping_button.isEnabled()
    _configure_separate_endpoints(dialog)
    _set_mapping(dialog, 1, 3)

    dialog.suggest_mapping_button.click()

    assert calls, "the suggester should be invoked"
    reactant_ids, product_ids = calls[-1]
    assert 0 in reactant_ids and 3 in product_ids
    # Gap filled, existing mapping preserved, no product reused.
    assert dialog._mapping_by_reactant[0] == 2
    assert dialog._mapping_by_reactant[1] == 3
    assert "Suggested 1 mapping" in dialog.suggestion_status.text()
    dialog.deleteLater()


def test_mapping_product_combo_popup_scrolls_a_long_candidate_list() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    combo = _MappingProductCombo()
    for atom_id in range(21):
        combo.addItem(f"C #{atom_id}", atom_id)
    assert combo.maxVisibleItems() == 12

    combo.show()
    combo.showPopup()
    app.processEvents()
    scrollbar = combo.view().verticalScrollBar()
    # Capped to maxVisibleItems, so the surplus atoms sit behind a scrollable bar
    # the wheel can reach — not stacked in one over-tall popup that runs off the
    # screen with no scrollbar (the reported bug).
    assert scrollbar.maximum() > scrollbar.minimum()
    combo.hidePopup()
    combo.deleteLater()


def test_structural_suggestion_reports_when_nothing_new() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(
        _document_state(),
        correspondence_suggester=lambda _r, _p: RDKitResult([]),
    )
    _configure_separate_endpoints(dialog)

    dialog.suggest_mapping_button.click()

    assert "No new structural suggestion" in dialog.suggestion_status.text()
    dialog.deleteLater()


def test_structural_suggestion_shows_the_failure_reason() -> None:
    # A failed suggestion must not be presented as "no shared substructure" —
    # that reads as a chemistry claim about the drawing.
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    message = (
        "The substructure search stopped before it finished. Try the suggestion again."
    )
    dialog = CalculationStepDialog(
        _document_state(),
        correspondence_suggester=lambda _r, _p: RDKitResult(None, message),
    )
    _configure_separate_endpoints(dialog)
    _set_mapping(dialog, 1, 3)

    dialog.suggest_mapping_button.click()

    assert dialog.suggestion_status.text() == message
    # A failure applies nothing and disturbs nothing.
    assert dialog._mapping_by_reactant[1] == 3
    assert dialog._mapping_by_reactant.get(0) is None
    dialog.deleteLater()


def test_correspondence_suggester_returns_the_access_result_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas = object()
    expected = RDKitResult(None, "The structural suggestion failed.")
    calls: list[tuple[object, object, frozenset[int], frozenset[int]]] = []

    def suggest_for(active_canvas, model, reactant_ids, product_ids):
        calls.append((active_canvas, model, reactant_ids, product_ids))
        return expected

    monkeypatch.setattr(
        "chemvas.ui.calculation_step_dialog.suggest_atom_correspondence_result_for",
        suggest_for,
    )
    suggester = _correspondence_suggester_for(canvas, _document_state())
    assert suggester is not None
    reactant_ids = frozenset({0, 1})
    product_ids = frozenset({2, 3})

    result = suggester(reactant_ids, product_ids)

    assert result is expected
    assert len(calls) == 1
    assert calls[0][0] is canvas
    assert calls[0][2:] == (reactant_ids, product_ids)


def test_dialog_label_colors_track_mapping_and_clear_on_reject() -> None:
    class _Highlighter:
        def __init__(self) -> None:
            self.labels: list[
                tuple[frozenset[int], frozenset[int], frozenset[int]]
            ] = []
            self.clear_count = 0

        def show_atom_labels(
            self, reactant_atom_ids, product_atom_ids, excluded_atom_ids=()
        ) -> None:
            self.labels.append(
                (
                    frozenset(reactant_atom_ids),
                    frozenset(product_atom_ids),
                    frozenset(excluded_atom_ids),
                )
            )

        def clear_all(self) -> None:
            self.clear_count += 1

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    highlighter = _Highlighter()
    dialog = CalculationStepDialog(
        _document_state(),
        mapping_highlighter=highlighter,
    )
    _configure_separate_endpoints(dialog)

    # Label tints follow the mapping, not mere inclusion: only the identity-
    # seeded catalyst atom is mapped so far, everything else is gray.
    assert highlighter.labels
    assert highlighter.labels[-1] == (
        frozenset({4}),
        frozenset({4}),
        frozenset({0, 1, 2, 3, 5}),
    )

    _set_mapping(dialog, 0, 2)
    assert highlighter.labels[-1] == (
        frozenset({0, 4}),
        frozenset({2, 4}),
        frozenset({1, 3, 5}),
    )

    clear_count_before_reject = highlighter.clear_count
    dialog.reject()

    assert highlighter.clear_count > clear_count_before_reject
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

        def clear_all(self) -> None:
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


def _reviewed_precomplex_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    _source, candidates, raw = _generate_candidate_fixture(
        tmp_path, monkeypatch, capsys
    )
    step = raw["state"]["calculation_plan"]["steps"][0]
    reviewed = tmp_path / "reviewed.chemvas"
    assert (
        calculation_bundle_cli.run(
            [
                "select-precomplex",
                str(candidates),
                "--step",
                "S01",
                "--reactant-candidate",
                step["reactant"]["precomplex"]["candidates"][0]["id"],
                "--product-candidate",
                step["product"]["precomplex"]["candidates"][0]["id"],
                "--reviewer",
                "test-reviewer",
                "--output",
                str(reviewed),
            ]
        )
        == 0
    )
    capsys.readouterr()
    state = json.loads(reviewed.read_text(encoding="utf-8"))["state"]
    assert isinstance(state, dict)
    return state


def test_dialog_noop_edit_preserves_reviewed_precomplex_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _reviewed_precomplex_state(tmp_path, monkeypatch, capsys)
    before = state["calculation_plan"]["steps"][0]
    dialog = CalculationStepDialog(state)

    dialog.step_selector.setCurrentIndex(1)
    dialog.accept()

    assert dialog.result_plan_state is not None
    after = dialog.result_plan_state["steps"][0]
    assert after["reactant"]["precomplex"] == before["reactant"]["precomplex"]
    assert after["product"]["precomplex"] == before["product"]["precomplex"]
    dialog.deleteLater()


def test_dialog_dependency_edit_invalidates_precomplex_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _reviewed_precomplex_state(tmp_path, monkeypatch, capsys)
    dialog = CalculationStepDialog(state)
    dialog.step_selector.setCurrentIndex(1)
    dialog._set_combo_data(dialog._role_combos[("reactant", 2)], "spectator")

    dialog.accept()

    assert dialog.result_plan_state is not None
    step = dialog.result_plan_state["steps"][0]
    assert step["reactant"]["precomplex"] == {"kind": "none"}
    assert step["product"]["precomplex"] == {"kind": "none"}
    dialog.deleteLater()
