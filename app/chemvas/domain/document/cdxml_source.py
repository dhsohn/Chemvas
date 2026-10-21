"""Validated native CDXML provenance retained by document saves and recovery.

This is document content, not a pointer to a mutable file on disk. Bindings use
source object IDs; collection bindings are parallel to the saved item arrays.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

from .state_values import _is_number

MAX_CDXML_SOURCE_BYTES = 16 * 1024 * 1024
COLLECTIONS = frozenset(
    ("notes", "arrows", "shapes", "images", "marks", "orbitals", "ts_brackets")
)


def parse_native_xml(xml: str) -> ET.Element:
    if not isinstance(xml, str) or len(xml.encode("utf-8")) > MAX_CDXML_SOURCE_BYTES:
        raise ValueError("Invalid or oversized native CDXML source.")
    if "<!ENTITY" in xml or re.search(r"<!DOCTYPE[^>]*\[", xml):
        raise ValueError(
            "CDXML entity declarations and internal DTDs are not supported."
        )
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("Invalid native CDXML source.") from exc
    if root.tag != "CDXML" or len(root.findall("page")) != 1:
        raise ValueError("Native CDXML editing requires one page.")
    objects = list(root.iter())
    if len(objects) > 100_000:
        raise ValueError("Too many native CDXML objects.")
    return root


def validate_cdxml_source(source: object, state: Mapping[str, object]) -> None:
    if not isinstance(source, dict) or set(source) != {
        "xml",
        "offset",
        "atoms",
        "bonds",
        "items",
        "baseline",
        "baseline_items",
    }:
        raise ValueError("Invalid CDXML source fields.")
    root = parse_native_xml(source["xml"])
    object_ids = [
        e.attrib["id"]
        for e in root.iter()
        if e.tag not in {"font", "objecttag"} and e.get("id") is not None
    ]
    ids = set(object_ids)
    if len(ids) != len(object_ids):
        raise ValueError("Duplicate native CDXML object IDs.")
    offset = source["offset"]
    if (
        not isinstance(offset, (list, tuple))
        or len(offset) != 2
        or any(not _is_number(v) for v in offset)
    ):
        raise ValueError("Invalid CDXML coordinate offset.")
    for key in ("atoms", "bonds"):
        values = source[key]
        if not isinstance(values, dict) or any(
            not all(part.isdigit() for part in str(k).split(":"))
            or not isinstance(v, str)
            or v not in ids
            for k, v in values.items()
        ):
            raise ValueError(f"Invalid CDXML {key} bindings.")
        if len(set(values.values())) != len(values):
            raise ValueError(f"Duplicate CDXML {key} binding.")
    _validate_item_bindings(source["items"], state, ids)
    baseline = source["baseline"]
    if not isinstance(baseline, dict) or "cdxml_source" in baseline:
        raise ValueError("Invalid recursive CDXML baseline.")
    from .state_validation import _validate_canvas_state

    _validate_canvas_state(baseline)
    _validate_item_bindings(source["baseline_items"], baseline, ids)


def _validate_item_bindings(
    items: object, state: Mapping[str, object], ids: set[str]
) -> None:
    if not isinstance(items, dict) or not set(items) <= COLLECTIONS:
        raise ValueError("Invalid CDXML item bindings.")
    for key, bindings in items.items():
        values = state.get(key, [])
        if (
            not isinstance(values, list)
            or not isinstance(bindings, list)
            or len(bindings) != len(values)
            or any(
                v is not None and (not isinstance(v, str) or v not in ids)
                for v in bindings
            )
        ):
            raise ValueError(f"Invalid CDXML {key} bindings.")
        present = [v for v in bindings if v is not None]
        if len(set(present)) != len(present):
            raise ValueError(f"Duplicate CDXML {key} binding.")
