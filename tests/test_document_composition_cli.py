from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from chemvas.bootstrap import document_composition
from chemvas.core.document_io import read_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.calculation_bundle import inspect_components


def _composition() -> dict[str, object]:
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [
            {"id": 0, "element": "C", "x": 0.0, "y": 0.0},
            {"id": 1, "element": "O", "x": 18.0, "y": 0.0},
        ],
        "bonds": [{"a": 0, "b": 1, "order": 1}],
    }


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_compose_document_public_cli_writes_reopenable_canonical_document(
    tmp_path: Path,
) -> None:
    request = tmp_path / "scheme.json"
    request.write_text(json.dumps(_composition()), encoding="utf-8")
    output = tmp_path / "scheme.chemvas"

    result = _run("compose-document", str(request), "--output", str(output))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["format"] == "chemvas-document-composition-report"
    assert report["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert report["atom_count"] == 2
    assert report["bond_count"] == 1
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    document = read_document(output)
    assert document.payload["version"] == CANVAS_FILE_VERSION
    assert document.state["model"]["atoms"]["1"]["element"] == "O"
    assert document.state["model"]["bonds"][0]["a"] == 0


def test_compose_document_synchronizes_atom_annotations_and_electronic_marks(
    tmp_path: Path,
) -> None:
    composition = _composition()
    atoms = composition["atoms"]
    assert isinstance(atoms, list)
    atoms[0]["formal_charge"] = -1
    atoms[1]["formal_charge"] = 1
    atoms[1]["radical_electrons"] = 1
    request = tmp_path / "charged.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    output = tmp_path / "charged.chemvas"

    result = _run("compose-document", str(request), "--output", str(output))

    assert result.returncode == 0, result.stderr
    document = read_document(output)
    annotations = document.state["model"]["atom_annotations"]
    assert annotations == {
        "0": {"formal_charge": -1},
        "1": {"formal_charge": 1, "radical_electrons": 1},
    }
    attached = sorted(
        (mark["atom_id"], mark["kind"])
        for mark in document.state["marks"]
        if mark["atom_id"] is not None
    )
    assert attached == [(0, "minus"), (1, "plus"), (1, "radical")]
    components = inspect_components(document.state)
    assert components[0].formal_charge == 0
    assert components[0].radical_electrons == 1


def test_compose_document_builds_scene_objects_and_structured_note_style(
    tmp_path: Path,
) -> None:
    composition = _composition()
    atoms = composition["atoms"]
    bonds = composition["bonds"]
    assert isinstance(atoms, list)
    assert isinstance(bonds, list)
    atoms.append({"id": 2, "element": "N", "x": 9.0, "y": 15.588})
    bonds[0]["style"] = "hash"
    bonds.extend(
        [
            {"a": 1, "b": 2, "order": 1},
            {"a": 2, "b": 0, "order": 1},
        ]
    )
    composition.update(
        {
            "notes": [
                {
                    "text": "Title & scope",
                    "x": 5.0,
                    "y": -20.0,
                    "style": {
                        "font_size": 15,
                        "font_weight": 700,
                        "italic": True,
                        "color": "#2f6ed3",
                    },
                }
            ],
            "arrows": [{"kind": "arrow", "start": [30.0, 0.0], "end": [60.0, 0.0]}],
            "shapes": [
                {
                    "shape_kind": "rounded_rect",
                    "left": -10.0,
                    "top": -10.0,
                    "right": 20.0,
                    "bottom": 25.0,
                    "stroke_style": "dashed",
                }
            ],
            "ring_fills": [{"atom_ids": [0, 1, 2], "color": "#f5ead4", "alpha": 0.5}],
            "settings": {"sheet_orientation": "landscape", "text_font_size": 15},
        }
    )
    request = tmp_path / "scene.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    output = tmp_path / "scene.chemvas"

    result = _run("compose-document", str(request), "--output", str(output))

    assert result.returncode == 0, result.stderr
    state = read_document(output).state
    assert state["model"]["bonds"][0]["style"] == "hash"
    assert state["ring_fills"][0]["points"] == [
        [0.0, 0.0],
        [18.0, 0.0],
        [9.0, 15.588],
    ]
    assert state["notes"][0]["text"] == "Title & scope"
    assert '<span style="' in state["notes"][0]["html"]
    assert "font-size:15pt" in state["notes"][0]["html"]
    assert "font-weight:700" in state["notes"][0]["html"]
    assert "color:#2f6ed3" in state["notes"][0]["html"]
    assert "Title &amp; scope" in state["notes"][0]["html"]
    assert state["arrows"][0]["kind"] == "arrow"
    assert state["shapes"][0]["kind"] == "shape"
    assert state["settings"]["sheet_orientation"] == "landscape"
    assert state["settings"]["text_font_size"] == 15


def test_compose_document_rejects_wrongly_typed_settings_value_cleanly(
    tmp_path: Path,
) -> None:
    composition = _composition()
    composition["settings"] = {"bond_length_px": None}
    request = tmp_path / "scheme.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    output = tmp_path / "scheme.chemvas"

    result = _run("compose-document", str(request), "--output", str(output))

    assert result.returncode == 2
    assert result.stderr.startswith("chemvas: error:")
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert not output.exists()


def test_read_composition_enforces_size_limit_during_the_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = tmp_path / "growing.json"
    request.write_bytes(b"0" * (document_composition.MAX_COMPOSITION_BYTES + 1))
    real_stat = Path.stat

    def stale_stat(path: Path, *args: object, **kwargs: object) -> object:
        if path == request:
            return SimpleNamespace(st_size=0)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stale_stat)

    with pytest.raises(ValueError, match="exceeds"):
        document_composition._read_composition(request)
