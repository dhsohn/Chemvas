from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from chemvas.bootstrap import calculation_bundle as cli
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts


def _settings() -> dict[str, object]:
    return serialize_settings(
        bond_length_px=18.0,
        arrow_line_width=1.5,
        arrow_head_scale=0.4,
        orbital_phase_enabled=True,
        text_font_size=13,
        text_font_weight=600,
        text_italic=False,
        sheet_size="A4",
        sheet_orientation="portrait",
    )


def _write_source(
    path: Path, *, charge: int = 0, second_component: bool = False
) -> bytes:
    atoms = {0: Atom("C", 0.0, 0.0), 1: Atom("O", 1.0, 0.0)}
    bonds: list[Bond | None] = [Bond(0, 1)]
    if second_component:
        atoms[5] = Atom("Cl", 5.0, 0.0)
    model = MoleculeModel(atoms=atoms, bonds=bonds)
    marks: list[dict[str, object]] = []
    for _ in range(abs(charge)):
        marks.append(
            {
                "kind": "plus" if charge > 0 else "minus",
                "text": "+" if charge > 0 else "-",
                "atom_id": 0,
                "dx": None,
                "dy": None,
                "x": 0.0,
                "y": 0.0,
            }
        )
    state: dict[str, object] = {
        "model": serialize_model_state(model),
        "ring_fills": [],
        "notes": [],
        "marks": marks,
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }
    write_document(path, state, CANVAS_FILE_VERSION)
    return path.read_bytes()


def _fake_artifacts() -> CalculationArtifacts:
    return CalculationArtifacts(
        mol_block="fake mol\n",
        xyz_block="3\nChemvas geometry v1\nC 0 0 0\nO 1 0 0\nH 0 1 0\n",
        atom_map=(
            AtomMapEntry(1, 1, "C", "chemvas_atom", 0),
            AtomMapEntry(2, 2, "O", "chemvas_atom", 1),
            AtomMapEntry(
                3,
                None,
                "H",
                "implicit_hydrogen",
                None,
                parent_xyz_index=1,
                parent_chemvas_atom_id=0,
            ),
        ),
        rdkit_version="test-rdkit",
        rdkit_formal_charge=0,
        rdkit_radical_electrons=0,
        electron_count=14,
        geometry_embedding="ETKDGv3",
        geometry_random_seed=0xC0FFEE,
        geometry_optimization_policy="MMFF when parameterized, otherwise UFF",
        geometry_optimization_result="not_recorded",
        mol_atom_count=2,
        xyz_atom_count=3,
    )


class _FakeAdapter:
    last_error: str | None = None

    def model_to_calculation_artifacts(self, model, atom_annotations=None):
        assert sorted(model.atoms) == [0, 1]
        return _fake_artifacts()


def test_inspect_emits_machine_readable_component_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source, second_component=True)

    assert cli.run(["inspect", str(source)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["component_count"] == 2
    assert payload["components"][0]["atom_ids"] == [0, 1]
    assert payload["components"][1]["atom_ids"] == [5]


def test_inspect_subprocess_does_not_import_qt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; "
        f"sys.argv=['chemvas','inspect',{str(source)!r}]; "
        "from chemvas.bootstrap.application import main; "
        "code=0; "
        "\ntry: main()"
        "\nexcept SystemExit as exc: code=int(exc.code or 0)"
        "\nassert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
        "for name in sys.modules), sorted(name for name in sys.modules "
        "if name.startswith('PyQt6'))"
        "\nraise SystemExit(code)"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "app")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["component_count"] == 1


def test_attach_plan_refuses_a_plan_number_it_cannot_parse(tmp_path: Path) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text('{"steps": 1e99999999999999999999}', encoding="utf-8")
    output = tmp_path / "mechanism.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(["attach-plan", str(source), str(plan_path), "--output", str(output)])

    assert error.value.code == 2
    assert not output.exists()
