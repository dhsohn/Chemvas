from __future__ import annotations

import base64
import json
import zlib
from os import PathLike
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from core.document_io import ChemvasDocument, create_document, parse_document
from core.document_state import CHEMVAS_FILE_TYPE, SUPPORTED_FILE_VERSIONS

PathType = str | PathLike[str]

CHEMVAS_SVG_PAYLOAD_TYPE = "chemvas-svg-source"
CHEMVAS_SVG_PAYLOAD_VERSION = 1
CHEMVAS_SVG_SCOPE_SHEET = "sheet"
CHEMVAS_SVG_SCOPE_SELECTION = "selection"
CHEMVAS_SVG_SCOPES = frozenset((CHEMVAS_SVG_SCOPE_SHEET, CHEMVAS_SVG_SCOPE_SELECTION))
CHEMVAS_SVG_ENCODING = "base64+zlib+json"
CHEMVAS_SVG_NAMESPACE = "https://chemvas.app/ns/svg-source/1"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"

_SOURCE_TAG = f"{{{CHEMVAS_SVG_NAMESPACE}}}source"
_METADATA_TAG = f"{{{SVG_NAMESPACE}}}metadata"
_MAX_SVG_SOURCE_TEXT_BYTES = 8 * 1024 * 1024
_MAX_SVG_PAYLOAD_BYTES = 32 * 1024 * 1024


ET.register_namespace("", SVG_NAMESPACE)
ET.register_namespace("chemvas", CHEMVAS_SVG_NAMESPACE)
ET.register_namespace("xlink", XLINK_NAMESPACE)


def create_editable_svg_payload(
    state: dict[str, Any],
    *,
    document_version: int,
    scope: str,
) -> dict[str, Any]:
    document = create_document(state, document_version)
    payload: dict[str, Any] = {
        "type": CHEMVAS_SVG_PAYLOAD_TYPE,
        "version": CHEMVAS_SVG_PAYLOAD_VERSION,
        "scope": scope,
        "document": document.payload,
    }
    _validated_editable_svg_payload(payload)
    return payload


def embed_chemvas_document_in_svg(path: PathType, payload: dict[str, Any]) -> None:
    _validated_editable_svg_payload(payload)
    tree = ET.parse(path)
    root = tree.getroot()
    metadata = _metadata_element(root)

    for metadata_element in _root_metadata_elements(root):
        for child in list(metadata_element):
            if child.tag == _SOURCE_TAG:
                metadata_element.remove(child)

    source = ET.Element(
        _SOURCE_TAG,
        {
            "encoding": CHEMVAS_SVG_ENCODING,
            "type": CHEMVAS_SVG_PAYLOAD_TYPE,
            "version": str(CHEMVAS_SVG_PAYLOAD_VERSION),
        },
    )
    source.text = _encode_payload(payload)
    metadata.append(source)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def extract_chemvas_document_from_svg(path: PathType) -> ChemvasDocument:
    payload = extract_chemvas_svg_payload(path)
    return parse_document(payload["document"])


def extract_chemvas_svg_payload(path: PathType) -> dict[str, Any]:
    tree = ET.parse(Path(path))
    root = tree.getroot()
    sources = [
        child
        for metadata in _root_metadata_elements(root)
        for child in list(metadata)
        if child.tag == _SOURCE_TAG
    ]
    if not sources:
        raise ValueError("No editable Chemvas metadata found in SVG.")
    if len(sources) != 1:
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    payload = _decode_source_element(sources[0])
    return _validated_editable_svg_payload(payload)


def _root_metadata_elements(root: ET.Element) -> list[ET.Element]:
    return [child for child in list(root) if child.tag == _METADATA_TAG]


def _metadata_element(root: ET.Element) -> ET.Element:
    metadata = root.find(_METADATA_TAG)
    if metadata is None:
        metadata = ET.Element(_METADATA_TAG)
        root.insert(0, metadata)
    return metadata


def _encode_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def _decode_source_element(source: ET.Element) -> dict[str, Any]:
    if source.get("encoding") != CHEMVAS_SVG_ENCODING:
        raise ValueError("Unsupported editable Chemvas metadata encoding.")
    text = source.text or ""
    if len(text.encode("utf-8")) > _MAX_SVG_SOURCE_TEXT_BYTES:
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    try:
        compressed = base64.b64decode(text.encode("ascii"), validate=True)
        raw = _decompress_svg_payload(compressed)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, OSError, RecursionError, zlib.error, UnicodeError) as exc:
        raise ValueError("Invalid editable Chemvas metadata in SVG.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    return payload


def _decompress_svg_payload(compressed: bytes) -> bytes:
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, _MAX_SVG_PAYLOAD_BYTES + 1)
    if len(raw) > _MAX_SVG_PAYLOAD_BYTES or decompressor.unconsumed_tail:
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    raw += decompressor.flush()
    if len(raw) > _MAX_SVG_PAYLOAD_BYTES or not decompressor.eof or decompressor.unused_data:
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    return raw


def _validated_editable_svg_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") != CHEMVAS_SVG_PAYLOAD_TYPE:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    if payload.get("version") != CHEMVAS_SVG_PAYLOAD_VERSION:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    if payload.get("scope") not in CHEMVAS_SVG_SCOPES:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError("Invalid editable Chemvas SVG payload.")
    if document.get("type") != CHEMVAS_FILE_TYPE or document.get("version") not in SUPPORTED_FILE_VERSIONS:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    parse_document(document)
    return payload


__all__ = [
    "CHEMVAS_SVG_ENCODING",
    "CHEMVAS_SVG_NAMESPACE",
    "CHEMVAS_SVG_PAYLOAD_TYPE",
    "CHEMVAS_SVG_PAYLOAD_VERSION",
    "CHEMVAS_SVG_SCOPE_SELECTION",
    "CHEMVAS_SVG_SCOPE_SHEET",
    "create_editable_svg_payload",
    "embed_chemvas_document_in_svg",
    "extract_chemvas_document_from_svg",
    "extract_chemvas_svg_payload",
]
