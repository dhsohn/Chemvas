from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
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
    try:
        payload = build_document_payload(state, version)
    except ValueError as exc:
        # This is the save/export side: the state came from our own snapshot,
        # not from a file, so "Invalid Chemvas file." would mislead the user.
        raise ValueError(
            "Failed to save: the document state did not pass validation. "
            "This is a Chemvas bug — please report it."
        ) from exc
    return ChemvasDocument(payload=payload, state=payload["state"])


def parse_document(payload: object) -> ChemvasDocument:
    state = extract_document_state(payload)
    normalized_payload = cast(dict[str, Any], normalize_json_numbers(payload))
    normalized_state = cast(dict[str, Any], normalize_json_numbers(state))
    return ChemvasDocument(payload=normalized_payload, state=normalized_state)


def write_document(path: PathType, state: dict[str, Any], version: int) -> ChemvasDocument:
    document = create_document(state, version)
    atomic_write_via_temp(
        path,
        lambda tmp: _write_document_payload(tmp, document.payload),
    )
    return document


def _write_document_payload(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def atomic_write_text(path: PathType, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_via_temp(path, lambda tmp: _write_text_payload(tmp, text, encoding=encoding))


def _write_text_payload(path: Path, text: str, *, encoding: str) -> None:
    with path.open("w", encoding=encoding) as handle:
        handle.write(text)


def atomic_write_via_temp(path: PathType, writer: Callable[[Path], None]) -> None:
    target = Path(path)
    # Atomic write: render/write to a sibling temp file, flush to disk, then
    # replace. A crash/IO error mid-write leaves the previous file intact.
    tmp = target.with_name(f".{target.name}.tmp")
    try:
        writer(tmp)
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def read_document(path: PathType) -> ChemvasDocument:
    with Path(path).open("r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle, parse_float=Decimal)
        except (ValueError, RecursionError, UnicodeError) as exc:
            raise ValueError("Invalid Chemvas file.") from exc
    return parse_document(payload)
