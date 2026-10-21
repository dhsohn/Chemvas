"""The public CDXML working-document reader; JSON remains internal state only."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_DOCUMENT_BYTES,
    build_document_payload,
)
from chemvas.features.cdxml_document import parse_cdxml_document

PathType = str | PathLike[str]


@dataclass(frozen=True)
class DocumentFile:
    payload: dict[str, Any]
    state: dict[str, Any]
    source_sha256: str


@dataclass(frozen=True)
class ExactDocumentRead:
    source_bytes: bytes
    document: DocumentFile


def read_exact_document(
    path: PathType, *, max_bytes: int = MAX_DOCUMENT_BYTES
) -> ExactDocumentRead:
    with Path(path).open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"input document exceeds the {max_bytes}-byte limit")
    parsed = parse_cdxml_document(raw, preserve_source=True)
    return ExactDocumentRead(
        raw,
        DocumentFile(
            payload=build_document_payload(parsed.state, CANVAS_FILE_VERSION),
            state=parsed.state,
            source_sha256=parsed.source_sha256,
        ),
    )


def read_document(path: PathType) -> DocumentFile:
    return read_exact_document(path).document
