from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

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
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }
    write_document(path, state, CANVAS_FILE_VERSION)
    return path.read_bytes()


def _fake_artifacts() -> CalculationArtifacts:
    return CalculationArtifacts(
        mol_block="fake mol\n",
        xyz_block="3\nChemvas Calculation Bundle v1\nC 0 0 0\nO 1 0 0\nH 0 1 0\n",
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


def test_pack_creates_complete_hashed_non_overwriting_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.chemvas"
    original = _write_source(source)
    output = tmp_path / "species-a.bundle"
    monkeypatch.setattr(cli, "RDKitAdapter", _FakeAdapter)

    assert (
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "species-a",
                "--charge",
                "0",
                "--multiplicity",
                "1",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    stdout_manifest = json.loads(capsys.readouterr().out)
    disk_manifest = json.loads((output / "manifest.json").read_text())

    assert stdout_manifest == disk_manifest
    assert set(path.name for path in output.iterdir()) == {
        "source.chemvas",
        "structure.mol",
        "geometry.xyz",
        "atom_map.json",
        "manifest.json",
    }
    assert (output / "source.chemvas").read_bytes() == original
    assert disk_manifest["chemical_state"]["multiplicity_validation"] == (
        "electron_count_parity_only"
    )
    assert disk_manifest["chemical_state"]["spin_state_inference"] == "not_performed"
    for name, metadata in disk_manifest["artifacts"].items():
        content = (output / name).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(content).hexdigest()
        assert metadata["bytes"] == len(content)

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "species-a",
                "--charge",
                "0",
                "--multiplicity",
                "1",
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert (output / "source.chemvas").read_bytes() == original


def test_pack_rejects_charge_mismatch_before_rdkit_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "charged.chemvas"
    _write_source(source, charge=1)
    output = tmp_path / "bundle"

    class _ShouldNotConstruct:
        def __init__(self) -> None:
            raise AssertionError("RDKit must not run after charge mismatch")

    monkeypatch.setattr(cli, "RDKitAdapter", _ShouldNotConstruct)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "charged",
                "--charge",
                "0",
                "--multiplicity",
                "1",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_pack_reports_optional_rdkit_dependency_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "bundle"

    class _UnavailableAdapter:
        last_error = "RDKit is not available in this environment."

        def model_to_calculation_artifacts(self, model, atom_annotations=None):
            return None

    monkeypatch.setattr(cli, "RDKitAdapter", _UnavailableAdapter)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "species-a",
                "--charge",
                "0",
                "--multiplicity",
                "1",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_pack_rejects_unsafe_species_id_and_nonpositive_multiplicity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    for species_id, multiplicity in (("../escape", "1"), ("valid", "0")):
        with pytest.raises(SystemExit) as error:
            cli.run(
                [
                    "pack",
                    str(source),
                    "--component",
                    "0",
                    "--species-id",
                    species_id,
                    "--charge",
                    "0",
                    "--multiplicity",
                    multiplicity,
                    "--output",
                    str(tmp_path / f"bundle-{multiplicity}"),
                ]
            )
        assert error.value.code == 2


def test_pack_rejects_inconsistent_rdkit_artifacts_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "bundle"

    class _WrongChargeAdapter(_FakeAdapter):
        def model_to_calculation_artifacts(self, model, atom_annotations=None):
            artifacts = _fake_artifacts()
            return CalculationArtifacts(
                mol_block=artifacts.mol_block,
                xyz_block=artifacts.xyz_block,
                atom_map=artifacts.atom_map,
                rdkit_version=artifacts.rdkit_version,
                rdkit_formal_charge=1,
                rdkit_radical_electrons=0,
                electron_count=artifacts.electron_count,
                geometry_embedding=artifacts.geometry_embedding,
                geometry_random_seed=artifacts.geometry_random_seed,
                geometry_optimization_policy=artifacts.geometry_optimization_policy,
                geometry_optimization_result=artifacts.geometry_optimization_result,
                mol_atom_count=artifacts.mol_atom_count,
                xyz_atom_count=artifacts.xyz_atom_count,
            )

    monkeypatch.setattr(cli, "RDKitAdapter", _WrongChargeAdapter)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "species-a",
                "--charge",
                "0",
                "--multiplicity",
                "1",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_pack_rejects_multiplicity_with_wrong_electron_count_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "bundle"
    monkeypatch.setattr(cli, "RDKitAdapter", _FakeAdapter)

    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "pack",
                str(source),
                "--component",
                "0",
                "--species-id",
                "species-a",
                "--charge",
                "0",
                "--multiplicity",
                "2",
                "--output",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_atomic_writer_removes_staging_directory_after_write_failure(
    tmp_path: Path,
) -> None:
    output = tmp_path / "bundle"
    original_open = Path.open
    calls = 0

    def failing_open(path: Path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        return original_open(path, *args, **kwargs)

    with mock.patch.object(Path, "open", failing_open):
        with pytest.raises(OSError, match="injected write failure"):
            cli._atomic_create_directory(output, {"one": b"1", "two": b"2"})

    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


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
