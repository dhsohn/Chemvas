from __future__ import annotations

import base64
import json
import zlib
from decimal import Decimal
from os import PathLike
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

from chemvas.core.document_io import ChemvasDocument, create_document, parse_document
from chemvas.domain.document import (
    CHEMVAS_FILE_TYPE,
    SUPPORTED_FILE_VERSIONS,
    normalize_json_numbers,
)

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
_FORBIDDEN_XML_DECLARATIONS = ("<!DOCTYPE", "<!ENTITY")


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
    return _validated_editable_svg_payload(payload)


def embed_chemvas_document_in_svg(path: PathType, payload: dict[str, Any]) -> None:
    payload = _validated_editable_svg_payload(payload)
    tree = _parse_svg_tree(path, error_message="Invalid SVG file.")
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
    tree = _parse_svg_tree(
        path, error_message="Invalid editable Chemvas metadata in SVG."
    )
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


def _parse_svg_tree(
    path: PathType, *, error_message: str
) -> ET.ElementTree[ET.Element[str]]:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError(error_message) from exc
    # xml.etree expands internal entities, so a crafted DTD ("billion laughs")
    # could exhaust memory. Chemvas-exported SVGs never carry a DOCTYPE, and
    # entity declarations can only live inside one, so reject them before the
    # XML parser sees the document. A raw ASCII byte scan is insufficient for
    # UTF-16/32 XML because each markup character is separated by NUL bytes.
    try:
        has_forbidden_declaration = _has_forbidden_xml_declaration(data)
    except UnicodeError as exc:
        raise ValueError(error_message) from exc
    if has_forbidden_declaration:
        raise ValueError(error_message)
    try:
        return ET.ElementTree(ET.fromstring(data))
    except (ET.ParseError, LookupError) as exc:
        raise ValueError(error_message) from exc


def _has_forbidden_xml_declaration(data: bytes) -> bool:
    if any(marker.encode("ascii") in data for marker in _FORBIDDEN_XML_DECLARATIONS):
        return True
    encoding = _wide_xml_encoding(data)
    if encoding is None:
        return False
    decoded = data.decode(encoding)
    return any(marker in decoded for marker in _FORBIDDEN_XML_DECLARATIONS)


def _wide_xml_encoding(data: bytes) -> str | None:
    # Check UTF-32 signatures before UTF-16 because the UTF-32LE BOM begins with
    # the UTF-16LE BOM. Explicit-endian XML can be BOM-less and may start with
    # XML whitespace before its first '<', so inspect the first code unit rather
    # than assuming markup is the first character.
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be"
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    xml_initial_ascii = b"\t\n\r <"
    if len(data) >= 4:
        if data[0] == data[1] == data[2] == 0 and data[3] in xml_initial_ascii:
            return "utf-32-be"
        if data[0] in xml_initial_ascii and data[1:4] == b"\x00\x00\x00":
            return "utf-32-le"
    if len(data) >= 2:
        if data[0] == 0 and data[1] in xml_initial_ascii:
            return "utf-16-be"
        if data[0] in xml_initial_ascii and data[1] == 0:
            return "utf-16-le"
    return None


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
        payload = json.loads(raw.decode("utf-8"), parse_float=Decimal)
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
    if (
        len(raw) > _MAX_SVG_PAYLOAD_BYTES
        or not decompressor.eof
        or decompressor.unused_data
    ):
        raise ValueError("Invalid editable Chemvas metadata in SVG.")
    return raw


def _validated_editable_svg_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != {"type", "version", "scope", "document"}:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    if payload.get("type") != CHEMVAS_SVG_PAYLOAD_TYPE:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    if payload.get("version") != CHEMVAS_SVG_PAYLOAD_VERSION:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    scope = payload.get("scope")
    if not isinstance(scope, str) or scope not in CHEMVAS_SVG_SCOPES:
        raise ValueError("Invalid editable Chemvas SVG payload.")
    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError("Invalid editable Chemvas SVG payload.")
    document_version = document.get("version")
    if (
        document.get("type") != CHEMVAS_FILE_TYPE
        or type(document_version) is not int
        or document_version not in SUPPORTED_FILE_VERSIONS
    ):
        raise ValueError("Invalid editable Chemvas SVG payload.")
    try:
        parse_document(document)
    except ValueError as exc:
        raise ValueError("Invalid editable Chemvas SVG payload.") from exc
    return cast(dict[str, Any], normalize_json_numbers(payload))


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
