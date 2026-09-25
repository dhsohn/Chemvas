from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import Mock

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
from chemvas.features.document_composition import compose_document_state

if TYPE_CHECKING:
    from pathlib import Path


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


def test_terminal_angle_cli_decimal_and_failure_leave_original_intact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = _state()
    model = state["model"]
    model["atoms"][2] = {
        "element": "C",
        "x": 36.0,
        "y": 0.0,
        "color": "#000000",
        "explicit_label": False,
    }
    model["next_atom_id"] = 3
    model["bonds"].append(
        {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"}
    )
    source, patch_path, output = (
        tmp_path / name for name in ("angle.chemvas", "angle.json", "adjusted.chemvas")
    )
    write_document(source, state, CANVAS_FILE_VERSION)
    before = source.read_bytes()
    patch = _patch(before)
    patch["operations"] = [
        {
            "op": "set_terminal_angle",
            "pivot_id": 1,
            "reference_id": 0,
            "terminal_id": 2,
            "angle_degrees": -120.5,
        }
    ]
    patch_path.write_text(json.dumps(patch))
    assert (
        cli.run(["apply-patch", str(source), str(patch_path), "--output", str(output)])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["operations"][0]["angle_degrees"] == -120.5
    assert report["operations"][0]["bond_length"] == 18
    assert source.read_bytes() == before
    candidate = read_document(output).state
    assert candidate["model"]["bonds"] == state["model"]["bonds"]
    assert candidate["notes"] == state["notes"]
    patch["operations"][0]["angle_degrees"] = 0
    patch_path.write_text(json.dumps(patch))
    bad_output = tmp_path / "rejected.chemvas"
    with pytest.raises(SystemExit) as error:
        cli.run(
            ["apply-patch", str(source), str(patch_path), "--output", str(bad_output)]
        )
    assert error.value.code == 2
    assert not bad_output.exists()
    assert source.read_bytes() == before


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


@pytest.mark.parametrize("command", ["inspect-document", "dry-run", "apply-patch"])
@pytest.mark.parametrize(
    "field,values", [("formal_charge", [1, -1]), ("radical_electrons", [1, 2])]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_document_commands_reject_colliding_annotation_ids_before_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    field: str,
    values: list[int],
    reverse: bool,
) -> None:
    entries = list(zip(("0", "00"), values, strict=True))
    if reverse:
        entries.reverse()
    # Keep the visible mark consistent with the last entry, so the existing
    # semantic charge/radical check cannot hide a missing duplicate-ID guard.
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "O", "x": 0.0, "y": 0.0, field: entries[-1][1]}
            ],
            "bonds": [],
        }
    )
    source = tmp_path / "source.chemvas"
    write_document(source, state, CANVAS_FILE_VERSION)
    payload = json.loads(source.read_text())
    payload["state"]["model"]["atom_annotations"] = {
        key: {field: value} for key, value in entries
    }
    source.write_text(json.dumps(payload))
    source_bytes = source.read_bytes()
    patch = _patch(source_bytes)
    patch["operations"] = [{"op": "move_atom", "atom_id": 0, "x": 1.0, "y": 0.0}]
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(patch))
    patch_bytes = patch_path.read_bytes()
    output = tmp_path / "revised.chemvas"
    if command == "inspect-document":
        argv = [command, str(source)]
    else:
        destination = (
            ["--dry-run"] if command == "dry-run" else ["--output", str(output)]
        )
        argv = ["apply-patch", str(source), str(patch_path), *destination]

    with pytest.raises(SystemExit) as error:
        cli.run(argv)
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Duplicate atom annotation ID: 0" in captured.err
    assert source.read_bytes() == source_bytes
    assert patch_path.read_bytes() == patch_bytes
    assert set(tmp_path.iterdir()) == {source, patch_path}


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


@pytest.mark.parametrize("extra_bytes", [-1, 0, 1])
def test_patch_reader_bounds_actual_bytes_even_when_stat_size_is_stale(
    monkeypatch, extra_bytes
) -> None:
    limit = 16
    monkeypatch.setattr(cli, "MAX_PATCH_BYTES", limit)
    raw = b"{}" + b" " * (limit + extra_bytes - 2)
    path = Mock()
    path.is_file.return_value = True
    path.stat.return_value.st_size = 2
    path.read_bytes.return_value = raw
    stream = io.BytesIO(raw)
    path.open.return_value = stream

    if extra_bytes > 0:
        with pytest.raises(ValueError) as error:
            cli._read_patch(path)
        assert str(error.value) == "patch document exceeds the 16-byte limit"
    else:
        assert cli._read_patch(path) == {}
    path.open.assert_called_once_with("rb")
    path.read_bytes.assert_not_called()
    assert stream.closed


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
    assert not list(tmp_path.glob(".chemvas-create-*"))


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
    assert not list(tmp_path.glob(".chemvas-create-*"))


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


@pytest.mark.parametrize("dry_run", [False, True])
def test_patch_rejects_oversized_candidate_before_reporting_or_writing(
    tmp_path, monkeypatch, capsys, dry_run
):
    source = tmp_path / "source.chemvas"
    original = _write_source(source)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps(_patch(original)), encoding="utf-8")
    reference = tmp_path / "reference.chemvas"
    args = ["apply-patch", str(source), str(patch_path)]
    assert cli.run([*args, "--output", str(reference)]) == 0
    expected = reference.read_bytes()
    capsys.readouterr()
    output = tmp_path / "candidate.chemvas"
    destination = ["--dry-run"] if dry_run else ["--output", str(output)]
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(expected) - 1)
    with pytest.raises(SystemExit) as exc:
        cli.run([*args, *destination])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "byte limit" in captured.err
    assert not captured.out
    assert not output.exists()
    assert source.read_bytes() == original
    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(expected))
    assert cli.run([*args, *destination]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_sha256"] == hashlib.sha256(expected).hexdigest()
    if not dry_run:
        assert output.read_bytes() == expected
