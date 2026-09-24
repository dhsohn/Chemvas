"""Reviewed shared components must not hide substrate mapping suggestions."""

import importlib.util
from copy import deepcopy
from dataclasses import replace

import pytest
from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialogButtonBox

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel, serialize_model_state
from chemvas.ui.canvas.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.dialogs.calculation_step_dialog import (
    CalculationStepDialog,
    edit_calculation_plan_for_window,
)
from chemvas.ui.scene.scene_decoration_access import add_arrow_for
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)
from tests.calculation_plan_support import _document_state

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)


def _reaction(*, extra_catalyst=False):
    adapter = RDKitAdapter()
    model = MoleculeModel()
    components = []
    for index, smiles in enumerate(
        ("CNC(=S)NC", "CCO", "CC=O", *(("O",) if extra_catalyst else ()))
    ):
        fragment = adapter.smiles_to_2d(smiles)
        assert fragment is not None, adapter.last_error
        assert not fragment.atom_annotations
        offset = model.next_atom_id
        model.atoms.update(
            {
                offset + atom_id: replace(atom, x=atom.x + index * 100)
                for atom_id, atom in fragment.atoms.items()
            }
        )
        model.bonds.extend(
            replace(bond, a=bond.a + offset, b=bond.b + offset)
            for bond in fragment.bonds
            if bond is not None
        )
        model.next_atom_id = max(model.atoms) + 1
        components.append(set(range(offset, model.next_atom_id)))
    catalysts = [components[0], *components[3:]]
    return adapter, model, catalysts, components[1], components[2]


def _draft_state(model, catalysts, reactant, product):
    state = _document_state()
    state["model"] = serialize_model_state(model)
    states = []
    endpoints = {}
    for side, state_id, substrate in (
        ("reactant", "R", reactant),
        ("product", "P", product),
    ):
        members = [*catalysts, substrate]
        states.append(
            {
                "id": state_id,
                "charge": 0,
                "multiplicity": 1,
                "members": [
                    {"component_atom_ids": sorted(ids), "inclusion": "included"}
                    for ids in members
                ],
            }
        )
        endpoints[side] = {
            "state_id": state_id,
            "roles": [
                {
                    "component_atom_ids": sorted(ids),
                    "role": side if ids == substrate else "catalyst",
                }
                for ids in members
            ],
            "precomplex": {"kind": "none"},
        }
    state["calculation_plan"] = {
        "format": "chemvas-calculation-plan",
        "version": 2,
        "states": states,
        "steps": [
            {
                "id": "S",
                **endpoints,
                "atom_correspondence": [
                    {"reactant_atom_id": atom_id, "product_atom_id": atom_id}
                    for atom_id in sorted(set().union(*catalysts))
                ],
            }
        ],
    }
    return state


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.mark.parametrize("accept", [False, True])
@pytest.mark.parametrize("extra_catalyst", [False, True])
def test_actual_dialog_suggests_substrate_without_mutating_until_save(
    app, tmp_path, accept, extra_catalyst
):
    _adapter, model, catalysts, reactant, product = _reaction(
        extra_catalyst=extra_catalyst
    )
    state = _draft_state(model, catalysts, reactant, product)
    window = build_main_window()
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    window.resize(1120, 780)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    documents = canvas.services.canvas_document_session_service
    try:
        documents.apply_state(state)
        add_arrow_for(canvas, QPointF(0, 100), QPointF(40, 100), "arrow")
        history = canvas.services.history_service
        history.undo()
        assert history.can_redo()
        services.canvas_document_service.mark_clean(canvas)
        before = deepcopy(snapshot_canvas_state_for(canvas))
        before_model = canvas.model
        before_atoms = dict(canvas.model.atoms)
        stacks = history.capture_stack_snapshot()
        original = tmp_path / "original.chemvas"
        documents.save_to_file(str(original))
        original_bytes = original.read_bytes()
        failures = []
        visited = []
        expected = {
            **{atom_id: atom_id for atom_id in set().union(*catalysts)},
            **dict(zip(sorted(reactant), sorted(product), strict=True)),
        }

        def interact():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, CalculationStepDialog)
                assert QTest.qWaitForWindowExposed(dialog, 5000)
                visited.append(dialog)
                dialog.step_selector.setFocus()
                QTest.keyClick(dialog.step_selector, Qt.Key.Key_End)
                assert dialog.step_selector.currentData() == "S"
                assert dialog.suggest_mapping_button.isEnabled()
                QTest.mouseClick(
                    dialog.suggest_mapping_button, Qt.MouseButton.LeftButton
                )
                assert dialog._mapping_by_reactant == expected
                assert "Suggested 3 mapping(s)" in dialog.suggestion_status.text()
                assert snapshot_canvas_state_for(canvas) == before
                assert canvas.model is before_model
                assert all(
                    canvas.model.atoms[key] is atom
                    for key, atom in before_atoms.items()
                )
                history.verify_stack_snapshot(stacks)
                buttons = dialog.findChild(QDialogButtonBox)
                assert buttons is not None
                button = buttons.button(
                    QDialogButtonBox.StandardButton.Save
                    if accept
                    else QDialogButtonBox.StandardButton.Cancel
                )
                assert button is not None and button.isEnabled()
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            except Exception as error:
                failures.append(error)
                if isinstance(dialog, CalculationStepDialog):
                    dialog.reject()

        QTimer.singleShot(0, interact)
        changed = edit_calculation_plan_for_window(window)
        assert not failures, failures
        assert len(visited) == 1
        assert changed is accept
        assert original.read_bytes() == original_bytes
        if not accept:
            assert snapshot_canvas_state_for(canvas) == before
            history.verify_stack_snapshot(stacks)
            return
        after = deepcopy(snapshot_canvas_state_for(canvas))
        assert after != before
        assert {
            key: value for key, value in after.items() if key != "calculation_plan"
        } == {key: value for key, value in before.items() if key != "calculation_plan"}
        assert len(history.state.history) == len(stacks.history) + 1
        assert not history.can_redo()
        history.undo()
        assert snapshot_canvas_state_for(canvas) == before
        history.redo()
        assert snapshot_canvas_state_for(canvas) == after
        destination = tmp_path / "mapped.chemvas"
        documents.save_to_file(str(destination))
        documents.apply_state(read_document(destination).state)
        assert snapshot_canvas_state_for(canvas) == after
        assert original.read_bytes() == original_bytes
    finally:
        canvas.scene().clearFocus()
        services.canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()


@pytest.mark.parametrize("partial_endpoint", ["reactant", "product", "both"])
def test_partial_endpoint_component_is_not_treated_as_reviewed_catalyst(
    partial_endpoint,
):
    adapter, model, catalysts, reactant, product = _reaction()
    catalyst = catalysts[0]
    subset = catalyst - {max(catalyst)}
    left = reactant | (subset if partial_endpoint in {"reactant", "both"} else catalyst)
    right = product | (subset if partial_endpoint in {"product", "both"} else catalyst)
    anchors = {atom_id: atom_id for atom_id in left & right}
    before = deepcopy(model)

    assert (
        adapter._conversion_helper._mapped_shared_components(
            model, left, right, anchors
        )
        == set()
    )
    result = adapter.suggest_atom_correspondence_result(model, left, right, anchors)

    assert result.error is None
    assert all(
        left_id in left and right_id in right for left_id, right_id in result.value
    )
    assert all(
        model.atoms[left_id].element == model.atoms[right_id].element
        for left_id, right_id in result.value
    )
    assert all(
        dict(result.value).get(left_id) == right_id
        for left_id, right_id in anchors.items()
    )
    assert model == before


def test_cross_component_anchor_is_not_silently_removed():
    adapter, model, catalysts, reactant, product = _reaction(extra_catalyst=True)
    shared = set().union(*catalysts)
    anchors = {atom_id: atom_id for atom_id in shared}
    anchors[min(reactant)] = min(catalysts[0])
    before = deepcopy(model)

    result = adapter.suggest_atom_correspondence_result(
        model, reactant | shared, product | shared, anchors
    )

    assert result.value is None
    assert "existing atom mappings" in result.error
    assert model == before
