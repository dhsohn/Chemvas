from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from chemvas.bootstrap import document_patch as cli
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)


def _state() -> dict[str, object]:
    return {
        "model": serialize_model_state(
            MoleculeModel(
                atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", 18.0, 0.0)},
                bonds=[Bond(0, 1)],
            )
        ),
        "ring_fills": [],
        "notes": [{"text": "preserve", "x": 3.0, "y": 4.0}],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
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


def _write_source(path: Path, *, version: int = CANVAS_FILE_VERSION) -> bytes:
    write_document(path, _state(), version)
    return path.read_bytes()


def _patch(source_bytes: bytes) -> dict[str, object]:
    return {
        "format": "chemvas-graph-patch",
        "version": 1,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "operations": [
            {
                "op": "update_bond",
                "a": 0,
                "b": 1,
                "changes": {"order": 2, "style": "double"},
            }
        ],
    }


def test_inspect_document_hashes_exact_bytes_and_lists_full_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)

    assert cli.run(["inspect-document", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert [atom["id"] for atom in report["atoms"]] == [0, 1]
    assert report["bonds"][0]["a"] == 0


def test_dry_run_and_apply_share_candidate_hash_without_overwriting_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(_patch(source_bytes)))

    assert cli.run(["apply-patch", str(source), str(patch_path), "--dry-run"]) == 0
    dry_report = json.loads(capsys.readouterr().out)
    assert dry_report["written"] is False
    assert set(tmp_path.iterdir()) == {source, patch_path}

    output = tmp_path / "revised.chemvas"
    assert (
        cli.run(
            [
                "apply-patch",
                str(source),
                str(patch_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    apply_report = json.loads(capsys.readouterr().out)

    assert source.read_bytes() == source_bytes
    assert apply_report["candidate_sha256"] == dry_report["candidate_sha256"]
    assert (
        apply_report["candidate_sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert apply_report["operations"][0]["changed_fields"] == ["order", "style"]
    revised = read_document(output)
    assert revised.state["model"]["bonds"][0]["order"] == 2
    assert revised.state["notes"] == [{"text": "preserve", "x": 3.0, "y": 4.0}]


@pytest.mark.parametrize(
    "patch_text",
    [
        '{"format":"chemvas-graph-patch","format":"duplicate","version":1,"source_sha256":"x","operations":[]}',
        '{"format":"chemvas-graph-patch","version":1,"source_sha256":"x","operations":[{"op":"move_atom","atom_id":0,"x":NaN,"y":0}]}',
    ],
)
def test_patch_parser_rejects_duplicate_keys_and_nonstandard_numbers(
    tmp_path: Path, patch_text: str
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(patch_text)

    with pytest.raises(SystemExit) as error:
        cli.run(["apply-patch", str(source), str(patch_path), "--dry-run"])
    assert error.value.code == 2


def test_failure_after_an_earlier_operation_leaves_no_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    patch = _patch(source_bytes)
    patch["operations"] = [
        {
            "op": "add_atom",
            "atom_id": 2,
            "element": "N",
            "x": 36,
            "y": 0,
            "color": "#000000",
            "explicit_label": True,
        },
        {"op": "remove_bond", "a": 0, "b": 999},
    ]
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(patch))
    output = tmp_path / "must-not-exist.chemvas"

    with pytest.raises(SystemExit) as error:
        cli.run(["apply-patch", str(source), str(patch_path), "--output", str(output)])
    assert error.value.code == 2
    assert source.read_bytes() == source_bytes
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


def test_existing_file_and_directory_outputs_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(_patch(source_bytes)))
    targets = [tmp_path / "file.chemvas", tmp_path / "directory.chemvas"]
    targets[0].write_text("keep")
    targets[1].mkdir()

    for target in targets:
        with pytest.raises(SystemExit) as error:
            cli.run(
                ["apply-patch", str(source), str(patch_path), "--output", str(target)]
            )
        assert error.value.code == 2
    assert targets[0].read_text(encoding="utf-8") == "keep"
    assert targets[1].is_dir()


def test_existing_symlink_output_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(_patch(source_bytes)))
    output = tmp_path / "link.chemvas"
    try:
        output.symlink_to(tmp_path / "missing")
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires developer privileges")
        raise

    with pytest.raises(SystemExit) as error:
        cli.run(["apply-patch", str(source), str(patch_path), "--output", str(output)])

    assert error.value.code == 2
    assert output.is_symlink()


def test_atomic_publish_rejects_a_target_created_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(_patch(source_bytes)))
    output = tmp_path / "raced.chemvas"
    original_atomic_create = cli.atomic_create_bytes

    def race_create(path: Path, content: bytes) -> None:
        path.write_text("racer owns this path")
        original_atomic_create(path, content)

    monkeypatch.setattr(cli, "atomic_create_bytes", race_create)

    with pytest.raises(SystemExit) as error:
        cli.run(["apply-patch", str(source), str(patch_path), "--output", str(output)])
    assert error.value.code == 2
    assert output.read_text(encoding="utf-8") == "racer owns this path"
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


def test_headless_module_imports_neither_qt_nor_rdkit() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import chemvas.bootstrap.document_patch; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules); "
                "assert not any(name == 'rdkit' or name.startswith('rdkit.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_apply_patch_refuses_a_patch_number_it_cannot_parse(tmp_path: Path) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        '{"format":"chemvas-graph-patch","scale":1e99999999999999999999}',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as error:
        cli.run(["apply-patch", str(source), str(patch_path), "--dry-run"])

    assert error.value.code == 2
