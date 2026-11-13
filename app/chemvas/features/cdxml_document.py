"""Bounded CDXML document import and integrity-bound editable snapshots.

Native objects are the interchange representation. A snapshot comment preserves
Chemvas-only editing state only while the native XML remains byte-identical.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_DOCUMENT_BYTES,
    build_document_payload,
    extract_document_state,
    normalize_json_numbers,
)
from chemvas.domain.document.cdxml_source import (
    UnsafeCdxmlDeclarationsError,
    reject_unsafe_cdxml_declarations,
)
from chemvas.domain.json_io import strict_json_loads

_MARKER = re.compile(
    rb"\n<!-- ChemvasDocument:([0-9a-f]{64}):([A-Za-z0-9+/=]+) -->[ \t\r\n]*\Z"
)


@dataclass(frozen=True)
class CdxmlDocument:
    state: dict[str, Any]
    source_sha256: str


def embed_document(raw: bytes, state: dict[str, Any]) -> bytes:
    payload = build_document_payload(state, CANVAS_FILE_VERSION)
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True).encode())
    result = (
        raw
        + b"\n<!-- ChemvasDocument:"
        + hashlib.sha256(raw).hexdigest().encode()
        + b":"
        + encoded
        + b" -->\n"
    )
    if len(result) > MAX_DOCUMENT_BYTES:
        raise ValueError("CDXML document exceeds the document byte limit")
    return result


def read_cdxml_document(path: str | Path) -> CdxmlDocument:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    return parse_cdxml_document(raw)


def parse_cdxml_document(raw: bytes) -> CdxmlDocument:
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("CDXML document exceeds the document byte limit")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
        try:
            reject_unsafe_cdxml_declarations(text)
        except UnsafeCdxmlDeclarationsError as exc:
            raise ValueError(
                "CDXML entity declarations and internal DTDs are not supported"
            ) from exc
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as exc:
        raise ValueError("Not a valid UTF-8 CDXML document") from exc

    if root.tag != "CDXML" or len(root.findall("page")) != 1:
        raise ValueError("CDXML editing requires exactly one page")
    match = _MARKER.search(raw)
    if match and hashlib.sha256(raw[: match.start()]).hexdigest().encode() == match[1]:
        payload = strict_json_loads(
            base64.b64decode(match[2], validate=True).decode("utf-8")
        )
        extract_document_state(payload)
        normalized = normalize_json_numbers(payload)
        assert isinstance(normalized, dict)
        from chemvas.features.cdxml_editable_arrows import promote_snapshot_arrows

        promote_snapshot_arrows(normalized["state"])
        build_document_payload(normalized["state"], CANVAS_FILE_VERSION)
        return CdxmlDocument(normalized["state"], digest)
    from chemvas.features.cdxml_preservation import PreservingImporter

    state = PreservingImporter(text).state()
    return CdxmlDocument(state, digest)
