from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from chemvas.bootstrap.calculation_bundle import _parse_precomplex_request

ROOT = Path(__file__).resolve().parents[1]


def _examples(language: str) -> list[dict]:
    guide = (ROOT / "docs" / f"AGENT_CLI{language}.md").read_text(encoding="utf-8")
    return [
        json.loads(block)
        for block in re.findall(r"```json\n(.*?)\n```", guide, re.DOTALL)
    ]


def _example(language: str, format_name: str) -> dict:
    return next(
        item for item in _examples(language) if item.get("format") == format_name
    )


def _run(*arguments: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-m", "chemvas", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _write(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_translations_keep_all_json_examples_identical() -> None:
    assert _examples("") == _examples(".ko")


@pytest.mark.parametrize("language", ["", ".ko"])
def test_documented_composition_template_patch_chain(
    language: str, tmp_path: Path
) -> None:
    source = tmp_path / "scheme.chemvas"
    _run(
        "compose-document",
        _write(
            tmp_path / "scheme.json", _example(language, "chemvas-document-composition")
        ),
        "--output",
        str(source),
    )
    original = source.read_bytes()
    template = _example(language, "chemvas-template-insertion")
    template["source_sha256"] = hashlib.sha256(original).hexdigest()
    ring = tmp_path / "ring-added.chemvas"
    _run(
        "insert-template",
        str(source),
        "--request",
        _write(tmp_path / "ring.json", template),
        "--output",
        str(ring),
    )
    ring_bytes = ring.read_bytes()
    inspection = _run("inspect-document", str(ring))
    assert inspection["next_atom_id"] == 8
    patch = _example(language, "chemvas-graph-patch")
    patch["source_sha256"] = inspection["source_sha256"]
    patch_path = _write(tmp_path / "patch.json", patch)
    _run("apply-patch", str(ring), patch_path, "--dry-run")
    revised = tmp_path / "revised.chemvas"
    _run("apply-patch", str(ring), patch_path, "--output", str(revised))
    result = _run("inspect-document", str(revised))
    assert result["atom_count"] == 9
    for atom in result["atoms"]:
        if atom["element"] == "C":
            assert (
                sum(
                    bond["order"]
                    for bond in result["bonds"]
                    if atom["id"] in (bond["a"], bond["b"])
                )
                <= 4
            )
    _run(
        "render-document",
        str(source),
        "--output",
        str(tmp_path / "journal.svg"),
        "--width-mm",
        "70",
        "--max-height-mm",
        "120",
    )
    assert source.read_bytes() == original
    assert ring.read_bytes() == ring_bytes


@pytest.mark.parametrize("language", ["", ".ko"])
def test_documented_precomplex_request_is_complete_v2(language: str) -> None:
    request = _example(language, "chemvas-precomplex-request")
    request["source_document_sha256"] = "a" * 64
    cap, profile, environment, contacts = _parse_precomplex_request(
        request,
        step_id="S01",
        source_document_sha256="a" * 64,
    )
    assert cap == 16
    assert profile == "chemvas-rigid-precomplex-placement/2"
    assert environment == {"kind": "gas_phase"}
    assert set(contacts) == {"reactant", "product"}
    assert contacts["reactant"][0].first_atom_id == 2
    request["environment"] = {"kind": "solvent", "model": "CPCM", "name": "THF"}
    _parse_precomplex_request(request, step_id="S01", source_document_sha256="a" * 64)


@pytest.mark.parametrize(
    "section,field",
    [
        ("root", "profile"),
        ("endpoints", "product"),
        ("reactant", "contacts"),
        ("contact", "tolerance_angstrom"),
        ("environment", "name"),
    ],
)
def test_precomplex_field_errors_identify_the_missing_and_misspelled_key(
    section, field
):
    request = _example("", "chemvas-precomplex-request")
    request["source_document_sha256"] = "a" * 64
    request["environment"] = {"kind": "solvent", "model": "CPCM", "name": "THF"}
    target = {
        "root": request,
        "endpoints": request["endpoints"],
        "reactant": request["endpoints"]["reactant"],
        "contact": request["endpoints"]["reactant"]["contacts"][0],
        "environment": request["environment"],
    }[section]
    target[field + "_typo"] = target.pop(field)
    with pytest.raises(ValueError) as error:
        _parse_precomplex_request(
            request, step_id="S01", source_document_sha256="a" * 64
        )
    assert f"missing=['{field}']" in str(error.value)
    assert f"unexpected=['{field}_typo']" in str(error.value)


def test_composition_diagnostics_name_keys_and_supported_arrow_kinds():
    from chemvas.features.document_composition import compose_document_state

    manifest = {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [],
        "bonds": [],
    }
    with pytest.raises(ValueError, match="missing=.*stroke_style.*unknown=.*outline"):
        compose_document_state(
            {
                **manifest,
                "shapes": [
                    {
                        "shape_kind": "rect",
                        "left": 0,
                        "top": 0,
                        "right": 20,
                        "bottom": 20,
                        "outline": "solid",
                    }
                ],
            }
        )
    with pytest.raises(ValueError, match="settings has unknown keys.*font_typo"):
        compose_document_state({**manifest, "settings": {"font_typo": 12}})
    with pytest.raises(ValueError, match="kind is not supported.*dotted"):
        compose_document_state(
            {
                **manifest,
                "arrows": [{"kind": "dashed", "start": [0, 0], "end": [30, 0]}],
            }
        )
