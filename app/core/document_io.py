from __future__ import annotations

import json
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, cast

from core.document_state import build_document_payload, extract_document_state


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
    return ChemvasDocument(payload=cast(dict[str, Any], payload), state=state)


def write_document(path: PathType, state: dict[str, Any], version: int) -> ChemvasDocument:
    document = create_document(state, version)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(document.payload, handle, indent=2)
    return document


def read_document(path: PathType) -> ChemvasDocument:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return parse_document(payload)
