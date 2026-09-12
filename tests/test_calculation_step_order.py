from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from chemvas.domain.document import calculation_plan_to_state
from chemvas.features.calculation_bundle import (
    apply_calculation_step_edit,
    calculation_state_by_id,
    validate_calculation_plan,
)
from tests.test_calculation_plan import _document_state, _plan


def _multistep_document():
    state = _document_state()
    raw = _plan()
    raw["states"] = []
    raw["steps"] = []
    for number in (1, 2, 3):
        source = _plan()
        for item, prefix in zip(source["states"], ("R", "P"), strict=True):
            item["id"] = f"{prefix}{number:02d}"
            raw["states"].append(item)
        step = source["steps"][0]
        step["id"] = f"S{number:02d}"
        step["reactant"]["state_id"] = f"R{number:02d}"
        step["product"]["state_id"] = f"P{number:02d}"
        raw["steps"].append(step)
    # Serialized state order need not be paired or sorted by step ID.
    raw["states"] = [raw["states"][i] for i in (3, 4, 0, 5, 1, 2)]
    state["calculation_plan"] = raw
    return state


@pytest.mark.parametrize("index", [0, 1, 2])
def test_changed_step_and_states_keep_their_existing_positions(index):
    state = _multistep_document()
    before = deepcopy(state)
    plan = validate_calculation_plan(state, state["calculation_plan"])
    step = plan.steps[index]
    reactant = calculation_state_by_id(plan, step.reactant.state_id)
    product = calculation_state_by_id(plan, step.product.state_id)

    accepted = apply_calculation_step_edit(
        state,
        current_plan=plan,
        selected_step_id=step.id,
        reactant_state=replace(reactant, multiplicity=3),
        product_state=replace(product, multiplicity=3),
        step=step,
    )

    expected = deepcopy(before["calculation_plan"])
    for item in expected["states"]:
        if item["id"] in {reactant.id, product.id}:
            item["multiplicity"] = 3
    assert calculation_plan_to_state(accepted) == expected
    assert state == before


def test_new_endpoint_appends_without_reordering_surviving_states_or_steps():
    state = _multistep_document()
    plan = validate_calculation_plan(state, state["calculation_plan"])
    step = plan.steps[0]
    reactant = calculation_state_by_id(plan, step.reactant.state_id)
    product = calculation_state_by_id(plan, step.product.state_id)
    new_reactant = replace(reactant, id="R04")

    accepted = apply_calculation_step_edit(
        state,
        current_plan=plan,
        selected_step_id=step.id,
        reactant_state=new_reactant,
        product_state=product,
        step=replace(step, reactant=replace(step.reactant, state_id="R04")),
    )

    assert [item.id for item in accepted.steps] == [item.id for item in plan.steps]
    assert accepted.states == tuple(
        item for item in plan.states if item.id != reactant.id
    ) + (new_reactant,)


def test_new_step_appends_without_moving_existing_shared_states():
    state = _multistep_document()
    plan = validate_calculation_plan(state, state["calculation_plan"])
    step = replace(plan.steps[0], id="S04")

    accepted = apply_calculation_step_edit(
        state,
        current_plan=plan,
        selected_step_id=None,
        reactant_state=calculation_state_by_id(plan, step.reactant.state_id),
        product_state=calculation_state_by_id(plan, step.product.state_id),
        step=step,
    )

    assert accepted.states == plan.states
    assert accepted.steps == plan.steps + (step,)


def test_actual_dialog_order_survives_save_reopen_and_undo(tmp_path):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QKeySequence
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QDialogButtonBox

    from chemvas.bootstrap.main_window import build_main_window
    from chemvas.core.document_io import read_document
    from chemvas.ui.calculation_step_dialog import (
        CalculationStepDialog,
        edit_calculation_plan_for_window,
    )
    from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
    from chemvas.ui.main_window_ports import (
        active_canvas_for_window,
        services_for_window,
    )

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    documents = services.canvas_document_service
    documents.replace_canvas_with_state(
        window, canvas, state=_multistep_document(), file_path=None, display_name="Plan"
    )
    window.show()
    assert QTest.qWaitForWindowExposed(window)
    errors = []

    def factory(*args, **kwargs):
        dialog = CalculationStepDialog(*args, **kwargs)

        def submit():
            try:
                dialog.step_selector.setCurrentIndex(1)
                for fields in (dialog.reactant_widgets, dialog.product_widgets):
                    fields.multiplicity.setFocus()
                    fields.multiplicity.selectAll()
                    QTest.keyClicks(fields.multiplicity, "3")
                buttons = dialog.findChild(QDialogButtonBox)
                QTest.mouseClick(
                    buttons.button(QDialogButtonBox.StandardButton.Save),
                    Qt.MouseButton.LeftButton,
                )
            except Exception as error:
                errors.append(error)
                dialog.reject()

        QTimer.singleShot(0, submit)
        return dialog

    try:
        before = snapshot_canvas_state_for(canvas)
        assert edit_calculation_plan_for_window(window, dialog_factory=factory)
        assert not errors
        after = snapshot_canvas_state_for(canvas)
        expected = deepcopy(before)
        for item in expected["calculation_plan"]["states"]:
            if item["id"] in {"R01", "P01"}:
                item["multiplicity"] = 3
        assert after == expected
        path = tmp_path / "ordered-plan.chemvas"
        assert services.document_action_service.save_canvas_to_path(window, str(path))
        assert (
            read_document(path).state["calculation_plan"] == after["calculation_plan"]
        )
        canvas.setFocus()
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
        assert snapshot_canvas_state_for(canvas) == before
        QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
        assert snapshot_canvas_state_for(canvas) == after
        documents.replace_canvas_with_state(
            window,
            canvas,
            state=read_document(path).state,
            file_path=str(path),
            display_name="Reopened plan",
        )
        assert (
            snapshot_canvas_state_for(canvas)["calculation_plan"]
            == after["calculation_plan"]
        )
    finally:
        documents.mark_clean(canvas)
        window.close()
        app.processEvents()
