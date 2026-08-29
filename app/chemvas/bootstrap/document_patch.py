from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import atomic_create_bytes, read_exact_document
from chemvas.domain.document import build_document_payload, normalize_json_numbers
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.document_patch import (
    DocumentPatchResult,
    apply_document_patch,
    inspect_document_graph,
)

MAX_PATCH_BYTES = 1024 * 1024


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-document":
            report = _inspect_document(Path(args.document))
        elif args.command == "apply-patch":
            report = _apply_patch(
                Path(args.document),
                patch_path=Path(args.patch),
                output=Path(args.output) if args.output is not None else None,
                dry_run=bool(args.dry_run),
            )
        else:
            parser.error("a command is required")
            return 2
        sys.stdout.write(json_text(report))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Chemvas LLM-safe document inspection and graph patch tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect-document",
        help="inspect the complete chemical graph as deterministic JSON",
    )
    inspect_parser.add_argument("document", help="input .chemvas document")

    patch_parser = subparsers.add_parser(
        "apply-patch",
        help="validate or apply a transactional Chemvas Graph Patch v1",
    )
    patch_parser.add_argument("document", help="input .chemvas document")
    patch_parser.add_argument("patch", help="Chemvas Graph Patch v1 JSON file")
    destination = patch_parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--dry-run",
        action="store_true",
        help="fully validate and report without writing a file",
    )
    destination.add_argument(
        "--output",
        help="new non-overwriting .chemvas output path",
    )
    return parser


def _inspect_document(source: Path) -> dict[str, object]:
    _validate_source(source)
    source_bytes, document = read_exact_document(source)
    return {
        **inspect_document_graph(document.state),
        "source": str(source),
        "source_sha256": _sha256(source_bytes),
        "chemvas_document_version": int(document.payload["version"]),
    }


def _apply_patch(
    source: Path,
    *,
    patch_path: Path,
    output: Path | None,
    dry_run: bool,
) -> dict[str, object]:
    _validate_source(source)
    if not dry_run:
        if output is None:
            raise ValueError("--output is required unless --dry-run is used")
        _validate_new_output(source, output)
    source_bytes, document = read_exact_document(source)
    source_hash = _sha256(source_bytes)
    patch = _read_patch(patch_path)
    result = apply_document_patch(
        document.state,
        patch,
        source_sha256=source_hash,
        document_version=int(document.payload["version"]),
    )
    payload = cast(
        "dict[str, Any]",
        normalize_json_numbers(
            build_document_payload(
                result.state,
                int(document.payload["version"]),
            )
        ),
    )
    candidate_bytes = json_text(payload).encode("utf-8")
    candidate_hash = _sha256(candidate_bytes)
    report = _patch_report(
        result,
        source_sha256=source_hash,
        candidate_sha256=candidate_hash,
        document_version=int(document.payload["version"]),
        dry_run=dry_run,
    )
    if not dry_run:
        assert output is not None
        atomic_create_bytes(output, candidate_bytes)
    return report


def _patch_report(
    result: DocumentPatchResult,
    *,
    source_sha256: str,
    candidate_sha256: str,
    document_version: int,
    dry_run: bool,
) -> dict[str, object]:
    return {
        "format": "chemvas-graph-patch-report",
        "version": 1,
        "source_sha256": source_sha256,
        "candidate_sha256": candidate_sha256,
        "chemvas_document_version": document_version,
        "dry_run": dry_run,
        "written": not dry_run,
        "operation_count": len(result.operations),
        "operations": list(result.operations),
        "before": result.before,
        "after": result.after,
        "calculation_plan": {
            "present": result.calculation_plan_present,
            "validation": "passed"
            if result.calculation_plan_present
            else "not_present",
        },
    }


def _read_patch(path: Path) -> object:
    if not path.is_file():
        raise ValueError(f"patch document does not exist: {path}")
    if path.stat().st_size > MAX_PATCH_BYTES:
        raise ValueError(f"patch document exceeds the {MAX_PATCH_BYTES}-byte limit")
    try:
        return strict_json_loads(path.read_bytes())
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Chemvas Graph Patch JSON file.") from exc


def _validate_source(source: Path) -> None:
    if source.suffix.lower() != ".chemvas":
        raise ValueError("input must use the .chemvas filename extension")
    if not source.is_file():
        raise ValueError(f"input document does not exist: {source}")


def _validate_new_output(source: Path, output: Path) -> None:
    if output.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if output.absolute() == source.absolute():
        raise ValueError(
            "apply-patch writes a new document; output must differ from input"
        )
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


__all__ = ["MAX_PATCH_BYTES", "run"]
