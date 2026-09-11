from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document import MoleculeModel
from chemvas.features.document_composition import compose_document_state
from chemvas.features.insertion import annotation_mark_direction, plan_smiles_commit
from chemvas.ui.layout_qa_service import check_canvas_layout


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def nitro_composition():
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [
            {"id": 0, "element": "C", "x": -40.0, "y": 0.0},
            {
                "id": 1,
                "element": "N",
                "x": -20.0,
                "y": 0.0,
                "explicit_label": True,
                "formal_charge": 1,
            },
            {"id": 2, "element": "O", "x": -10.0, "y": -17.32, "explicit_label": True},
            {
                "id": 3,
                "element": "O",
                "x": -10.0,
                "y": 17.32,
                "explicit_label": True,
                "formal_charge": -1,
            },
        ],
        "bonds": [
            {"a": 0, "b": 1, "order": 1},
            {"a": 1, "b": 2, "order": 2},
            {"a": 1, "b": 3, "order": 1},
        ],
    }


def empty_state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )


def ammonium_composition():
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [{"id": 0, "element": "N", "x": 0.0, "y": 0.0, "formal_charge": 1}]
        + [
            {"id": index, "element": "C", "x": x, "y": y}
            for index, (x, y) in enumerate(
                [(14.14, -14.14), (-14.14, -14.14), (14.14, 14.14), (-14.14, 14.14)], 1
            )
        ],
        "bonds": [{"a": 0, "b": index, "order": 1} for index in range(1, 5)],
    }


@pytest.mark.parametrize("build", [nitro_composition, ammonium_composition])
def test_composition_charge_avoids_bonds_without_changing_chemistry(build):
    request = build()
    original = copy.deepcopy(request)
    state = compose_document_state(request)
    with offscreen_canvas(state, command="test-default-mark-placement") as (
        canvas,
        session,
    ):
        before = session.snapshot_state()
        report = check_canvas_layout(canvas)
        assert report["counts"]["charge-bond-overlap"] == 0, report
        assert session.snapshot_state() == before
        expected = {
            atom["id"]: {"formal_charge": atom["formal_charge"]}
            for atom in request["atoms"]
            if "formal_charge" in atom
        }
        assert before["model"]["atom_annotations"] == expected
    assert request == original


@pytest.mark.parametrize("build", [nitro_composition, ammonium_composition])
def test_compose_then_check_layout_public_cli_accepts_default_charges(tmp_path, build):
    source = tmp_path / "composition.json"
    output = tmp_path / "charged.chemvas"
    source.write_text(json.dumps(build()), encoding="utf-8")
    original = source.read_bytes()
    prefix = [
        sys.executable,
        "-c",
        "from chemvas.bootstrap.application import main; main()",
    ]
    composed = subprocess.run(
        [*prefix, "compose-document", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert composed.returncode == 0, composed.stderr
    document = output.read_bytes()
    checked = subprocess.run(
        [*prefix, "check-layout", str(output)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert checked.returncode == 0, (checked.stdout, checked.stderr)
    assert json.loads(checked.stdout)["counts"]["charge-bond-overlap"] == 0
    assert output.read_bytes() == document
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "smiles", ["O=[N+]([O-])c1ccccc1", "C[N+](=O)[O-]", "C[N+](C)(C)C"]
)
@pytest.mark.parametrize("route", ["load", "insert"])
def test_smiles_charge_avoids_bonds_and_exact_undo_redo(smiles, route):
    pytest.importorskip("rdkit")
    with offscreen_canvas(empty_state(), command="test-smiles-mark-placement") as (
        canvas,
        session,
    ):
        before = session.snapshot_state()
        controller = canvas.services.structure.insert_controller
        if route == "load":
            controller.smiles_service.load_smiles(smiles)
        else:
            controller.begin_smiles_insert(smiles)
            controller.commit_smiles_insert(QPointF(50.0, 60.0))
        after = session.snapshot_state()
        assert after["model"]["atoms"]
        assert after["marks"]
        assert check_canvas_layout(canvas)["counts"]["charge-bond-overlap"] == 0
        canvas.services.history_service.undo()
        assert session.snapshot_state() == before
        canvas.services.history_service.redo()
        assert session.snapshot_state() == after
        # Existing, manually moved mark state is restoration data, not a new default.
        moved = copy.deepcopy(after)
        moved["marks"][0].update(dx=41.25, dy=-37.75)
        atom = moved["model"]["atoms"][moved["marks"][0]["atom_id"]]
        moved["marks"][0].update(x=atom["x"] + 41.25, y=atom["y"] - 37.75)
        session.apply_state(moved)
        assert session.snapshot_state()["marks"] == moved["marks"]


def test_default_directions_are_distinct_and_ignore_bond_storage_order():
    model = MoleculeModel()
    center = model.add_atom("N", 0.0, 0.0)
    for x, y in [(-20.0, 0.0), (10.0, -17.32), (10.0, 17.32)]:
        other = model.add_atom("C", x, y)
        model.add_bond(center, other, 1)
    model.atom_annotations = {center: {"formal_charge": 1, "radical_electrons": 7}}
    before = copy.deepcopy(model)
    directions = [
        annotation_mark_direction(index, model=model, atom_id=center)
        for index in range(8)
    ]
    assert len(set(directions)) == 8
    assert directions[0][0] > 0 and directions[0][1] == 0
    assert all(math.hypot(x, y) == pytest.approx(math.sqrt(2)) for x, y in directions)
    plan = plan_smiles_commit(model, (0.0, 0.0), (0.0, 0.0))
    assert [(mark.x, mark.y) for mark in plan.marks] == directions
    assert model == before
    model.bonds.reverse()
    assert [
        annotation_mark_direction(index, model=model, atom_id=center)
        for index in range(8)
    ] == directions
