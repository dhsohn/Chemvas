from __future__ import annotations

import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chemvas.domain.chemistry_types import RDKitResult
from chemvas.domain.document import state as document_state_module

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QInputMethodEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLineEdit,
)

from chemvas.features.calculation_bundle import (
    calculation_plan_for_document,
    step_readiness,
)
from chemvas.ui.dialogs.calculation_plan_actions import correspondence_suggester_for
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from chemvas.ui.dialogs.calculation_step_widgets import _MappingProductCombo
from tests.calculation_plan_support import _document_state, _plan
from tests.calculation_workflow_support import _legacy_reviewed_precomplex_payload

if TYPE_CHECKING:
    from collections.abc import Mapping


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


def _save(dialog: CalculationStepDialog) -> dict[str, object] | None:
    saved: list[dict[str, object]] = []
    dialog.plan_saved.connect(saved.append)
    dialog.accept()
    return saved[0] if saved else None


def test_dialog_assigns_roles_in_one_document_and_saves_draft_mapping() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    dialog = CalculationStepDialog(state)

    assert "Draft mapping" in dialog.mapping_status.text()
    assert "ready for pack-step" not in dialog.mapping_status.text()
    _configure_separate_endpoints(dialog)

    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
    plan = calculation_plan_for_document(state)
    step = plan.steps[0]
    readiness = step_readiness(plan, step)
    assert step.reactant.roles[0].role == "reactant"
    assert step.product.roles[0].role == "product"
    assert step.reactant.roles[2].role == "spectator"
    assert [entry.reactant_atom_id for entry in step.atom_correspondence] == [4]
    assert readiness.mapping_complete is False
    dialog.deleteLater()


def test_dialog_deserializes_its_source_model_once() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    state["calculation_plan"] = _plan()
    with patch.object(
        document_state_module,
        "MoleculeModel",
        wraps=document_state_module.MoleculeModel,
    ) as model_construction:
        dialog = CalculationStepDialog(state)

    assert len(dialog._atom_elements) == 6
    assert model_construction.call_count == 1
    dialog.reject()
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

    assert "Source mapping complete" in dialog.mapping_status.text()
    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
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

    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
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
    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
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
        "chemvas.ui.dialogs.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    assert "repeated" in dialog.mapping_status.text()
    assert _save(dialog) is None
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
        "chemvas.ui.dialogs.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    assert _save(dialog) is None
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
    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
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
        "chemvas.ui.dialogs.calculation_step_dialog.QMessageBox.warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    assert _save(dialog) is None
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


def test_locked_opposite_endpoint_selection_is_retained_but_not_saved() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    model_state = state["model"]
    assert isinstance(model_state, dict)
    model_state["atom_annotations"] = {4: {"formal_charge": 1}}
    state["marks"] = [{"kind": "plus", "atom_id": 4}]
    dialog = CalculationStepDialog(state)
    _configure_separate_endpoints(dialog)
    component_atom_ids = dialog._components[2].atom_ids

    # The component starts as a catalyst on both sides. Making it reactive on
    # the reactant side locks the product controls without clearing their
    # retained values, so switching back can still restore the catalyst setup.
    dialog._set_combo_data(dialog._role_combos[("reactant", 2)], "reactant")
    assert not dialog._inclusion_combos[("product", 2)].isEnabled()
    assert dialog._inclusion_value("product", 2) == "included"
    assert dialog._role_combos[("product", 2)].currentData() == "catalyst"
    assert dialog.reactant_widgets.charge.value() == 1
    assert dialog.product_widgets.charge.value() == 0

    saved = _save(dialog)

    assert saved is not None
    state["calculation_plan"] = saved
    plan = calculation_plan_for_document(state)
    step = plan.steps[0]
    product_state = next(
        endpoint_state
        for endpoint_state in plan.states
        if endpoint_state.id == step.product.state_id
    )
    assert product_state.charge == 0
    assert component_atom_ids not in {
        member.component_atom_ids for member in product_state.members
    }
    assert component_atom_ids not in {
        role.component_atom_ids for role in step.product.roles
    }
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
    calls: list[tuple[frozenset[int], frozenset[int], dict[int, int]]] = []

    def suggester(
        reactant_ids: frozenset[int],
        product_ids: frozenset[int],
        existing_correspondence: Mapping[int, int],
    ) -> RDKitResult[list[tuple[int, int]]]:
        calls.append((reactant_ids, product_ids, dict(existing_correspondence)))
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
    reactant_ids, product_ids, existing_correspondence = calls[-1]
    assert 0 in reactant_ids and 3 in product_ids
    assert existing_correspondence == {1: 3, 4: 4}
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
        correspondence_suggester=lambda _r, _p, _existing: RDKitResult([]),
    )
    _configure_separate_endpoints(dialog)

    dialog.suggest_mapping_button.click()

    assert "No new structural suggestion" in dialog.suggestion_status.text()
    assert "heuristic found no additional pairs" in dialog.suggestion_status.text()
    assert "no shared substructure" not in dialog.suggestion_status.text()
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
        correspondence_suggester=lambda _r, _p, _existing: RDKitResult(None, message),
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
    expected = RDKitResult(None, "The structural suggestion failed.")
    calls: list[
        tuple[
            object,
            frozenset[int],
            frozenset[int],
            dict[int, int],
        ]
    ] = []

    def suggest_for(
        model,
        reactant_ids,
        product_ids,
        existing_correspondence,
    ):
        calls.append(
            (
                model,
                reactant_ids,
                product_ids,
                dict(existing_correspondence),
            )
        )
        return expected

    canvas = SimpleNamespace(
        rdkit=SimpleNamespace(suggest_atom_correspondence_result=suggest_for)
    )
    suggester = correspondence_suggester_for(canvas, _document_state())
    assert suggester is not None
    reactant_ids = frozenset({0, 1})
    product_ids = frozenset({2, 3})
    existing_correspondence = {0: 2}

    result = suggester(reactant_ids, product_ids, existing_correspondence)

    assert result is expected
    assert len(calls) == 1
    assert calls[0][1:] == (
        reactant_ids,
        product_ids,
        existing_correspondence,
    )


def test_dialog_keeps_reactive_component_as_context_on_the_other_side() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    raw_plan = _plan()
    raw_plan["states"][1]["members"].append(
        {"component_atom_ids": [0, 1], "inclusion": "context_only"}
    )
    raw_plan["steps"][0]["product"]["roles"].append(
        {"component_atom_ids": [0, 1], "role": "spectator"}
    )
    state["calculation_plan"] = raw_plan
    dialog = CalculationStepDialog(state)
    dialog.step_selector.setCurrentIndex(dialog.step_selector.findData("S01"))

    assert _save(dialog) == raw_plan
    dialog.deleteLater()


def _window_editor_canvas(monkeypatch, state):
    import chemvas.ui.dialogs.calculation_plan_actions as dialog_module
    from chemvas.adapters.qt.renderer import Renderer
    from chemvas.ui.canvas.canvas_view import CanvasView

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    session = canvas.services.canvas_document_session_service
    session.apply_state(state)
    monkeypatch.setattr(
        dialog_module, "active_canvas_for_window", lambda _window: canvas
    )
    window = SimpleNamespace(
        services=SimpleNamespace(
            canvas_document_service=SimpleNamespace(
                refresh_tab_title=lambda *_args: None
            ),
            status_service=SimpleNamespace(refresh_status_context=lambda *_args: None),
        )
    )
    return app, canvas, session, window


def test_window_plan_edit_is_one_undoable_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import chemvas.ui.dialogs.calculation_plan_actions as dialog_module
    from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
    from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas

    state = _document_state()
    _app, canvas, session, window = _window_editor_canvas(monkeypatch, state)
    before = session.snapshot_state()
    accepted_plan = _plan()

    assert dialog_module.save_calculation_plan_for_window(window, accepted_plan)
    history = history_service_for_canvas(canvas)
    assert history.can_undo()
    history.undo()
    assert calculation_plan_for(canvas) is None
    assert session.snapshot_state() == before
    history.redo()
    assert calculation_plan_for(canvas) == accepted_plan
    canvas.deleteLater()


def test_mapping_candidate_marks_scan_assignments_once() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    dialog = CalculationStepDialog(_document_state())
    _configure_separate_endpoints(dialog)

    class CountingMappings(dict):
        scans = 0

        def items(self):
            self.scans += 1
            return super().items()

        def values(self):
            self.scans += 1
            return super().values()

    mappings = CountingMappings(dialog._mapping_by_reactant)
    dialog._mapping_by_reactant = mappings
    dialog._refresh_used_candidate_marks()
    assert mappings.scans <= 1
    dialog.deleteLater()


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


def test_dialog_noop_edit_preserves_reviewed_precomplex_pair() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _legacy_reviewed_precomplex_payload()["state"]
    before = deepcopy(state["calculation_plan"]["steps"][0])
    assert before["reactant"]["precomplex"]["kind"] == "candidate_ensemble"
    assert before["product"]["precomplex"]["kind"] == "candidate_ensemble"
    dialog = CalculationStepDialog(state)

    dialog.step_selector.setCurrentIndex(1)
    saved = _save(dialog)

    assert saved is not None
    after = saved["steps"][0]
    assert after["reactant"]["precomplex"] == before["reactant"]["precomplex"]
    assert after["product"]["precomplex"] == before["product"]["precomplex"]
    dialog.deleteLater()


def test_dialog_dependency_edit_invalidates_precomplex_pair() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _legacy_reviewed_precomplex_payload()["state"]
    dialog = CalculationStepDialog(state)
    dialog.step_selector.setCurrentIndex(1)
    dialog._set_combo_data(dialog._role_combos[("reactant", 2)], "spectator")

    saved = _save(dialog)

    assert saved is not None
    step = saved["steps"][0]
    assert step["reactant"]["precomplex"] == {"kind": "none"}
    assert step["product"]["precomplex"] == {"kind": "none"}
    dialog.deleteLater()


def test_noop_window_plan_edit_does_not_add_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import chemvas.ui.dialogs.calculation_plan_actions as dialog_module
    from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas

    state = _document_state()
    state["calculation_plan"] = _plan()
    _app, canvas, session, window = _window_editor_canvas(monkeypatch, state)
    before = session.snapshot_state()

    assert not dialog_module.save_calculation_plan_for_window(window, _plan())
    assert not history_service_for_canvas(canvas).can_undo()
    assert session.snapshot_state() == before
    canvas.deleteLater()


def test_plan_history_publication_failure_restores_plan_and_both_stacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import chemvas.ui.dialogs.calculation_plan_actions as dialog_module
    from chemvas.core.history import HistoryCommand
    from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
    from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas

    _app, canvas, _session, window = _window_editor_canvas(
        monkeypatch, _document_state()
    )
    history = history_service_for_canvas(canvas)
    previous = HistoryCommand()
    redo = HistoryCommand()
    history.state.history.append(previous)
    history.state.redo_stack.append(redo)
    push = history.push

    def fail_after_push(command):
        push(command)
        raise RuntimeError("injected plan history publication failure")

    monkeypatch.setattr(history, "push", fail_after_push)

    with pytest.raises(RuntimeError, match="injected plan history"):
        dialog_module.save_calculation_plan_for_window(window, _plan())
    assert calculation_plan_for(canvas) is None
    assert history.state.history == [previous]
    assert history.state.redo_stack == [redo]
    canvas.deleteLater()


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_plan_history_failure_preserves_exact_plan_and_stacks(
    monkeypatch: pytest.MonkeyPatch, direction: str
) -> None:
    import chemvas.ui.dialogs.calculation_plan_actions as dialog_module
    import chemvas.ui.history.history_operations as command_module
    from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
    from chemvas.ui.canvas.canvas_window_access import history_service_for_canvas

    _app, canvas, _session, window = _window_editor_canvas(
        monkeypatch, _document_state()
    )

    dialog_module.save_calculation_plan_for_window(window, _plan())
    history = history_service_for_canvas(canvas)
    if direction == "redo":
        history.undo()
    before_plan = calculation_plan_for(canvas)
    before_history = tuple(history.state.history)
    before_redo = tuple(history.state.redo_stack)
    setter = command_module.set_calculation_plan_for

    def fail_after_set(canvas, state):
        setter(canvas, state)
        raise RuntimeError("injected plan mutation failure")

    monkeypatch.setattr(command_module, "set_calculation_plan_for", fail_after_set)

    with pytest.raises(RuntimeError, match="injected plan mutation"):
        getattr(history, direction)()
    assert calculation_plan_for(canvas) == before_plan
    assert tuple(history.state.history) == before_history
    assert tuple(history.state.redo_stack) == before_redo
    canvas.deleteLater()
