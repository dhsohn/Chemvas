from __future__ import annotations

import json
from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    find_spec("rdkit") is None,
    reason="RDKit is required for calculation-bundle integration tests",
)

from chemvas.bootstrap.calculation_bundle import run
from chemvas.core.document_io import write_document
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)


def test_calculation_artifacts_preserve_ids_and_map_implicit_hydrogens() -> None:
    model = MoleculeModel(
        atoms={7: Atom("C", 0.0, 0.0), 9: Atom("O", 1.0, 0.0)},
        bonds=[Bond(7, 9)],
    )

    artifacts = RDKitAdapter().model_to_calculation_artifacts(model)

    assert artifacts is not None
    assert artifacts.rdkit_version != "unknown"
    assert artifacts.rdkit_formal_charge == 0
    assert artifacts.rdkit_radical_electrons == 0
    assert artifacts.electron_count == 18
    assert artifacts.geometry_optimization_result != "not_recorded"
    assert artifacts.mol_atom_count == 2
    assert artifacts.xyz_atom_count > artifacts.mol_atom_count
    assert [entry.chemvas_atom_id for entry in artifacts.atom_map[:2]] == [7, 9]
    implicit_hydrogens = [
        entry for entry in artifacts.atom_map if entry.origin == "implicit_hydrogen"
    ]
    assert implicit_hydrogens
    assert all(entry.mol_index is None for entry in implicit_hydrogens)
    assert all(entry.parent_xyz_index is not None for entry in implicit_hydrogens)
    assert artifacts.xyz_block.splitlines()[0] == str(artifacts.xyz_atom_count)


def test_calculation_artifacts_explain_alias_expansion_and_are_deterministic() -> None:
    model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0), 4: Atom("Ph", 1.0, 0.0)},
        bonds=[Bond(0, 4)],
    )
    adapter = RDKitAdapter()

    first = adapter.model_to_calculation_artifacts(model)
    second = adapter.model_to_calculation_artifacts(model)

    assert first is not None
    assert second is not None
    alias_entries = [entry for entry in first.atom_map if entry.chemvas_atom_id == 4]
    assert {entry.origin for entry in alias_entries} == {
        "alias_attachment",
        "alias_expansion",
    }
    assert first.mol_block == second.mol_block
    assert first.xyz_block == second.xyz_block
    assert first.atom_map == second.atom_map


def test_real_rdkit_pack_writes_self_consistent_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "methanol.chemvas"
    output = tmp_path / "methanol.bundle"
    model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 1.0, 0.0)},
        bonds=[Bond(0, 1)],
    )
    state: dict[str, object] = {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }
    write_document(source, state, CANVAS_FILE_VERSION)

    exit_code = run(
        [
            "pack",
            str(source),
            "--component",
            "0",
            "--species-id",
            "methanol",
            "--charge",
            "0",
            "--multiplicity",
            "1",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    manifest = json.loads(capsys.readouterr().out)
    atom_map = json.loads((output / "atom_map.json").read_text(encoding="utf-8"))
    xyz_count = int(
        (output / "geometry.xyz").read_text(encoding="utf-8").splitlines()[0]
    )
    assert manifest["structure"]["atom_counts"]["xyz"] == xyz_count
    assert len(atom_map["entries"]) == xyz_count
    assert manifest["structure"]["geometry_generation"]["random_seed"] == 12648430
