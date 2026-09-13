from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

from chemvas.bootstrap import (
    calculation_bundle,
    document_layout,
    document_layout_check,
    document_patch,
    document_render,
    document_template,
)
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.precomplex_profile import CURRENT_PROFILE_ID
from chemvas.features.document_composition import compose_document_state
from tests.calculation_artifact_support import _StateFakeAdapter
from tests.calculation_plan_support import _document_state, _plan

OPERATIONS = (
    "inspect-document",
    "apply-patch",
    "check-layout",
    "render-document",
    "layout-document",
    "insert-template",
    "generate-precomplex",
    "pack-step",
)


def _write_source(source: Path) -> bytes:
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": index, "element": element, "x": x, "y": 10}
                for index, element, x in (
                    (0, "N", 10),
                    (1, "C", 30),
                    (2, "C", 200),
                    (3, "O", 220),
                )
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}, {"a": 2, "b": 3, "order": 1}],
            "notes": [{"text": "Synthetic Δ", "x": 25, "y": 40}],
            "arrows": [{"kind": "arrow", "start": [60, 10], "end": [100, 10]}],
        }
    )
    write_document(source, state, CANVAS_FILE_VERSION)
    return source.read_bytes()


def _case(directory: Path, operation: str):
    source, output = directory / "source.chemvas", directory / "output.chemvas"
    if operation in {"generate-precomplex", "pack-step"}:
        state = _document_state()
        state["calculation_plan"] = _plan()
        write_document(source, state, CANVAS_FILE_VERSION)
    else:
        _write_source(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if operation == "layout-document":
        request = directory / "layout.json"
        request.write_text(
            json.dumps(
                {
                    "format": "chemvas-scheme-layout",
                    "version": 1,
                    "source_sha256": digest,
                    "gap": 12,
                    "rows": [
                        {
                            "blocks": [{"atoms": [0, 1]}, {"atoms": [2, 3]}],
                            "arrows": [0],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return (
            document_layout,
            source,
            output,
            [operation, str(source), "--layout", str(request), "--output", str(output)],
        )
    if operation == "insert-template":
        request = directory / "template.json"
        request.write_text(
            json.dumps(
                {
                    "format": "chemvas-template-insertion",
                    "version": 1,
                    "source_sha256": digest,
                    "ring_size": 6,
                    "style": "benzene",
                    "position": [100.5, 100],
                    "anchor": {"kind": "free"},
                }
            ),
            encoding="utf-8",
        )
        return (
            document_template,
            source,
            output,
            [
                operation,
                str(source),
                "--request",
                str(request),
                "--output",
                str(output),
            ],
        )
    if operation == "generate-precomplex":
        request = directory / "request.json"
        request.write_text(
            json.dumps(
                {
                    "format": "chemvas-precomplex-request",
                    "version": 2,
                    "profile": CURRENT_PROFILE_ID,
                    "source_document_sha256": digest,
                    "step_id": "S01",
                    "candidate_cap": 2,
                    "environment": {"kind": "gas_phase"},
                    "endpoints": {
                        side: {
                            "contacts": [
                                {
                                    "id": f"{side}-contact",
                                    "first_atom_id": first,
                                    "second_atom_id": 4,
                                    "target_distance_angstrom": 3.0,
                                    "tolerance_angstrom": 0.1,
                                }
                            ]
                        }
                        for side, first in (("reactant", 0), ("product", 3))
                    },
                }
            ),
            encoding="utf-8",
        )
        return (
            calculation_bundle,
            source,
            output,
            [
                operation,
                str(source),
                str(request),
                "--step",
                "S01",
                "--output",
                str(output),
            ],
        )
    if operation == "pack-step":
        output = directory / "machine.json"
        return (
            calculation_bundle,
            source,
            output,
            [operation, str(source), "--step", "S01", "--output", str(output)],
        )
    if operation == "apply-patch":
        request = directory / "patch.json"
        request.write_text(
            json.dumps(
                {
                    "format": "chemvas-graph-patch",
                    "version": 1,
                    "source_sha256": digest,
                    "operations": [
                        {
                            "op": "update_bond",
                            "a": 0,
                            "b": 1,
                            "changes": {"order": 2, "style": "double"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return (
            document_patch,
            source,
            output,
            [operation, str(source), str(request), "--output", str(output)],
        )
    if operation == "render-document":
        output = directory / "output.png"
        return (
            document_render,
            source,
            output,
            [operation, str(source), "--output", str(output), "--dpi", "150"],
        )
    if operation == "check-layout":
        return (
            document_layout_check,
            source,
            None,
            [operation, str(source), "--sheet-only"],
        )
    assert operation == "inspect-document"
    return document_patch, source, None, [operation, str(source)]


def capture_operation(directory: Path, operation: str) -> dict:
    """Actual CLI/report/output boundary; only optional chemistry is deterministic."""
    module, source, output, argv = _case(directory, operation)
    original = source.read_bytes()
    constructor = hashlib.sha256
    source_hashes = []
    source_opens = []
    original_open = Path.open

    def count_hash(content=b"", *args, **kwargs):
        if content == original:
            source_hashes.append(content)
        return constructor(content, *args, **kwargs)

    def count_open(path, *args, **kwargs):
        if path == source:
            source_opens.append(path)
        return original_open(path, *args, **kwargs)

    stdout = io.StringIO()
    with (
        mock.patch.object(hashlib, "sha256", side_effect=count_hash),
        mock.patch.object(Path, "open", count_open),
        mock.patch.object(calculation_bundle, "RDKitAdapter", _StateFakeAdapter),
        redirect_stdout(stdout),
    ):
        code = module.run(argv)
    assert code in ({0, 1} if operation == "check-layout" else {0})
    report = json.loads(stdout.getvalue())
    expected = constructor(original).hexdigest()
    if operation == "generate-precomplex":
        state = json.loads(output.read_bytes())["state"]["calculation_plan"]
        for side in ("reactant", "product"):
            assert (
                state["steps"][0][side]["precomplex"]["source_document_sha256"]
                == expected
            )
    elif operation == "pack-step":
        assert report["payload"]["data"]["source"]["document_sha256"] == expected
        assert report["payload"]["data"]["source"]["document_bytes"] == len(original)
    else:
        assert report["source_sha256"] == expected
    assert source.read_bytes() == original
    artifact = output.read_bytes() if output is not None else None
    return {
        "report": stdout.getvalue().replace(str(directory), "<fixture>"),
        "artifact_sha256": constructor(artifact).hexdigest()
        if artifact is not None
        else None,
        "artifact_bytes": len(artifact) if artifact is not None else None,
        "source_sha256": expected,
        "source_hash_calls": len(source_hashes),
        "source_open_calls": len(source_opens),
    }


@pytest.mark.parametrize("operation", OPERATIONS)
def test_public_cli_hashes_exact_source_once(tmp_path, operation):
    result = capture_operation(tmp_path, operation)
    assert result["source_open_calls"] == 1
    assert result["source_hash_calls"] == 1


@pytest.mark.parametrize("spelling", ["compact", "indent", "bom"])
def test_reader_digest_is_exact_even_when_json_normalizes(tmp_path, spelling):
    source = tmp_path / "원본.chemvas"
    payload = json.loads(_write_source(source))
    payload["state"]["notes"][0]["text"] = "합성 Δ"
    text = json.dumps(
        payload, ensure_ascii=False, indent=None if spelling == "compact" else 2
    )
    original = text.encode("utf-8")
    if spelling == "bom":
        original = b"\xef\xbb\xbf" + original
    source.write_bytes(original)
    exact, document = read_exact_document(source)
    assert exact == original
    assert document.source_sha256 == hashlib.sha256(original).hexdigest()
    # Editing a parsed state must not reinterpret source identity as candidate identity.
    document.state["notes"][0]["text"] = "edited"
    assert document.source_sha256 == hashlib.sha256(original).hexdigest()
    assert source.read_bytes() == original
