"""Shown-canvas chemical conversion through the asynchronous desktop exporter."""

import importlib.util
import time
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
    serialize_model_state,
)
from chemvas.ui.canvas.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.molecule.structure_payload_access import (
    build_selected_3d_conversion_payload_for,
)
from chemvas.ui.preview3d.rdkit_export_job_state import active_rdkit_export_jobs
from chemvas.ui.selection.select_all_access import select_all_scene_items_for
from chemvas.ui.window.main_window_document_action_service import (
    _annotation_mark_states,
)
from chemvas.ui.window.main_window_ports import services_for_window
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)


def _show_model(canvas, model):
    state = snapshot_canvas_state_for(canvas)
    state["model"] = serialize_model_state(model)
    state["marks"] = _annotation_mark_states(model)
    canvas.services.canvas_document_session_service.apply_state(state)
    select_all_scene_items_for(canvas)


def _export(window, path):
    warnings = []
    statuses = []
    services_for_window(window).document_action_service.export_xyz(
        window,
        selected_only=True,
        file_dialog=SimpleNamespace(getSaveFileName=lambda *_args: (str(path), "")),
        message_box=SimpleNamespace(warning=lambda *_args: warnings.append(_args[-1])),
        status_sink=statuses.append,
    )
    for _ in range(500):
        if (
            statuses
            and statuses[-1].startswith(("Exported XYZ:", "Export failed:"))
            and not active_rdkit_export_jobs()
        ):
            break
        QApplication.processEvents()
        time.sleep(0.01)
    assert statuses[-1].startswith(("Exported XYZ:", "Export failed:")), statuses
    assert not active_rdkit_export_jobs()
    return warnings, statuses


def test_six_coordinate_phosphorus_export_warns_and_preserves_document_and_target(
    drawing, qt_errors, tmp_path
):
    window, canvas = drawing
    adapter = RDKitAdapter()
    model = adapter.smiles_to_2d("F[P-](F)(F)(F)(F)F")
    assert model is not None
    _show_model(canvas, model)
    _payload, annotations = build_selected_3d_conversion_payload_for(canvas)
    assert annotations == {1: {"formal_charge": -1}}
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    selected = tuple(canvas.scene().selectedItems())
    target = tmp_path / "existing.xyz"
    target.write_bytes(b"existing user geometry\n")

    warnings, statuses = _export(window, target)

    assert len(warnings) == 1
    assert "six-coordinate phosphorus" in warnings[0].lower()
    assert statuses[-1].startswith("Export failed:")
    assert target.read_bytes() == b"existing user geometry\n"
    assert snapshot_canvas_state_for(canvas) == before
    assert set(canvas.scene().selectedItems()) == set(selected)
    canvas.services.history_service.verify_stack_snapshot(history)
    assert not qt_errors
    saved = tmp_path / "editable.chemvas"
    assert services_for_window(window).document_action_service.save_canvas_to_path(
        window, str(saved)
    )
    assert deserialize_model_state(read_document(saved).state["model"]) == canvas.model


@pytest.mark.parametrize("cis", [True, False])
def test_drawn_double_bond_survives_native_reopen_and_async_xyz(
    drawing, qt_errors, tmp_path, cis
):
    from rdkit import Chem
    from rdkit.Chem import rdMolTransforms

    window, canvas = drawing
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 40.0, 0.0),
            2: Atom("C", -20.0, 34.64),
            3: Atom("C", 60.0, 34.64 if cis else -34.64),
        },
        bonds=[Bond(0, 1, 2), Bond(0, 2), Bond(1, 3)],
    )
    _show_model(canvas, model)
    saved = tmp_path / "drawing.chemvas"
    assert services_for_window(window).document_action_service.save_canvas_to_path(
        window, str(saved)
    )
    canvas.services.canvas_document_session_service.apply_state(
        read_document(saved).state
    )
    select_all_scene_items_for(canvas)
    before = snapshot_canvas_state_for(canvas)
    history = canvas.services.history_service.capture_stack_snapshot()
    payload, annotations = build_selected_3d_conversion_payload_for(canvas)
    payload.atom_annotations = annotations
    identifiers = RDKitAdapter().compute_identifiers(payload)
    reference = Chem.MolFromSmiles("C/C=C\\C" if cis else "C/C=C/C")
    assert identifiers.smiles == Chem.MolToSmiles(reference)
    assert identifiers.inchikey == Chem.MolToInchiKey(reference)

    target = tmp_path / "drawing.xyz"
    warnings, statuses = _export(window, target)

    assert not warnings
    assert statuses[-1].startswith("Exported XYZ:")
    geometry = Chem.MolFromXYZBlock(target.read_text())
    assert geometry is not None
    angle = abs(rdMolTransforms.GetDihedralDeg(geometry.GetConformer(), 2, 0, 1, 3))
    assert angle < 30 if cis else angle > 150
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.verify_stack_snapshot(history)
    assert not qt_errors
