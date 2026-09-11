from __future__ import annotations

from copy import deepcopy

import pytest
from PyQt6.QtWidgets import QApplication

from chemvas.core.document_io import read_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
)
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch
from chemvas.features.insertion import plan_smiles_commit
from chemvas.ui.insert_commit_service import InsertCommitService
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()


def _state(atoms, bonds=(), **fields):
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": index, "element": element, "x": x, "y": y}
                for index, (element, x, y) in enumerate(atoms)
            ],
            "bonds": [{"a": a, "b": b, "order": 1} for a, b in bonds],
            **fields,
        }
    )


def _patch(state, *operations):
    return apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": "a" * 64,
            "operations": list(operations),
        },
        source_sha256="a" * 64,
        document_version=CANVAS_FILE_VERSION,
    ).state


@pytest.mark.parametrize(
    ("atoms", "bonds", "settings"),
    [
        ([("C", 100, 100), ("O", 100, 100), ("C", 120, 100)], [(0, 2), (1, 2)], {}),
        ([("C", 72, 72), ("O", 92, 72)], [(0, 1)], {"bond_length_px": 400}),
        ([("N", 100, 100), ("O", 100, 100)], [], {}),
    ],
)
def test_open_and_save_preserve_overlapping_atoms(
    canvas, tmp_path, atoms, bonds, settings
):
    state = _state(atoms, bonds, settings=settings)
    original = deepcopy(state)
    documents = canvas.services.document.canvas_document_session_service

    documents.apply_state(state)
    output = tmp_path / "reopened.chemvas"
    assert documents.save_to_file(str(output)) == []

    assert state == original
    assert deserialize_model_state(
        read_document(output).state["model"]
    ) == deserialize_model_state(state["model"])
    documents.apply_state(read_document(output).state)
    assert documents.snapshot_state()["model"] == state["model"]


def test_patch_move_preserves_projected_depth_through_desktop_save(canvas, tmp_path):
    state = _state([("C", 100, 100), ("C", 120, 100)], [(0, 1)])
    state["perspective"] = {
        "atom_coords_3d": {"0": [100, 100, 0], "1": [112.5, 100, 60]},
        "projection_center_3d": [100, 100, 0],
        "projection_anchor_2d": [100, 100],
    }
    patched = _patch(state, {"op": "move_atom", "atom_id": 1, "x": 130, "y": 100})
    assert patched["perspective"]["atom_coords_3d"]["1"] == [118.75, 100, 60]

    documents = canvas.services.document.canvas_document_session_service
    documents.apply_state(patched)
    output = tmp_path / "perspective.chemvas"
    assert documents.save_to_file(str(output)) == []
    assert read_document(output).state["perspective"] == patched["perspective"]


@pytest.mark.parametrize("operation", ["paste", "smiles"])
def test_insert_overlapping_heteroatom_preserves_original_and_undo(canvas, operation):
    state = _state([("C", 100, 100), ("N", 120, 100)], [(0, 1)])
    documents = canvas.services.document.canvas_document_session_service
    documents.apply_state(state)
    before = documents.snapshot_state()
    if operation == "paste":
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 0, "element": "C", "x": 82, "y": 82},
                {"id": 1, "element": "O", "x": 102, "y": 82},
            ],
            "bonds": [
                {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"}
            ],
            "rings": [],
            "marks": [],
            "scene_items": [],
        }
        controller = canvas.services.scene_operations.scene_clipboard_controller
        assert controller.paste_selection_from_clipboard(
            payload_provider=lambda: (payload, "overlapping-paste")
        )
    else:
        model = MoleculeModel(
            atoms={0: Atom("C", 100, 100), 1: Atom("O", 120, 100)},
            bonds=[Bond(0, 1)],
        )
        plan = plan_smiles_commit(model, (110, 100), (110, 100))
        assert InsertCommitService(canvas).apply_smiles_commit(
            plan, after_smiles_input="CO"
        )

    after = documents.snapshot_state()
    assert len(canvas.model.atoms) == 4
    assert canvas.model.atoms[1].element == "N"
    assert canvas.model.bonds[0].a == 0 and canvas.model.bonds[0].b == 1
    canvas.services.history_service.undo()
    assert documents.snapshot_state() == before
    canvas.services.history_service.redo()
    assert documents.snapshot_state() == after
