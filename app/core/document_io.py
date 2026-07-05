from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from os import PathLike
from pathlib import Path
from typing import Any, cast

from core.document_state import (
    build_document_payload,
    extract_document_state,
    normalize_json_numbers,
)

PathType = str | PathLike[str]


@dataclass(frozen=True)
class ChemvasDocument:
    payload: dict[str, Any]
    state: dict[str, Any]


def create_document(state: dict[str, Any], version: int) -> ChemvasDocument:
    payload = build_document_payload(state, version)
    return ChemvasDocument(payload=payload, state=payload["state"])


def parse_document(payload: object) -> ChemvasDocument:
    state = extract_document_state(payload)
    normalized_payload = cast(dict[str, Any], normalize_json_numbers(payload))
    normalized_state = cast(dict[str, Any], normalize_json_numbers(state))
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def write_document(path: PathType, state: dict[str, Any], version: int) -> ChemvasDocument:
    document = create_document(state, version)
    target = Path(path)
    # Atomic write: render to a sibling temp file, flush to disk, then replace.
    # A crash/IO error mid-write leaves the previous file intact instead of a
    # truncated document.
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(document.payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return document


def read_document(path: PathType) -> ChemvasDocument:
    with Path(path).open("r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle, parse_float=Decimal)
        except (ValueError, RecursionError, UnicodeError) as exc:
            raise ValueError("Invalid Chemvas file.") from exc
    return parse_document(payload)
