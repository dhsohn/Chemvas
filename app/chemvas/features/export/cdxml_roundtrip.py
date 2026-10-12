"""Bounded native CDXML diagnostics and exact eight-bit palette recovery."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.parsers import expat

from .cdxml_consumer_validation import (
    _Scene,
    parse_consumer_xml,
    validate_consumer_paint_colors,
)
from .cdxml_text_layout import MAX_CDXML_CONSUMER_BYTES

NATIVE_COLOR_PROFILE = "ChemDraw 25.0.2.14"
_FOUR_PLACES = Decimal("0.0001")
_SOURCE_LIMIT = Decimal("1e-15")
_STABLE_CHANNELS = tuple(
    n for n in range(256) if int((Decimal(n) / 255).quantize(_FOUR_PLACES) * 255) == n
)
_COLOR_TAG = re.compile(rb"""<color\b(?:[^>"']|"[^"]*"|'[^']*')*>""", re.DOTALL)
_ATTRIBUTE = re.compile(rb"""\s+([^\s=/>]+)\s*=\s*(["'])(.*?)\2""", re.DOTALL)
RGB = tuple[int, int, int]


def _root(raw: bytes) -> ET.Element:
    if len(raw) > MAX_CDXML_CONSUMER_BYTES:
        raise ValueError("CDXML input exceeds the byte limit")
    return parse_consumer_xml(raw)


def _components(row: ET.Element) -> tuple[Decimal, Decimal, Decimal]:
    try:
        values = tuple(Decimal(row.attrib[key]) for key in "rgb")
    except (InvalidOperation, KeyError) as exc:
        raise ValueError("CDXML palette requires numeric RGB components") from exc
    if any(not n.is_finite() or not 0 <= n <= 1 for n in values):
        raise ValueError("CDXML palette components must be finite and within 0..1")
    return values[0], values[1], values[2]


def _rgb8(values: tuple[Decimal, Decimal, Decimal]) -> RGB:
    return round(values[0] * 255), round(values[1] * 255), round(values[2] * 255)


def _palette_color_starts(raw: bytes) -> list[int]:
    """Locate real direct palette children, excluding comments and CDATA."""
    parser = expat.ParserCreate()
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[str] = []
    starts: list[int] = []

    def start(name: str, _attributes: dict[str, str]) -> None:
        if stack == ["CDXML", "colortable"] and name == "color":
            starts.append(parser.CurrentByteIndex)
        stack.append(name)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _name: stack.pop()
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as exc:
        raise ValueError("Native CDXML byte parsing failed") from exc
    return starts


def _component_spans(raw: bytes, start: int) -> list[tuple[str, int, int]]:
    tag = _COLOR_TAG.match(raw, start)
    if tag is None:
        raise ValueError("Native palette color tag cannot be located")
    cursor = start + len(b"<color")
    result = []
    while raw[cursor : tag.end()].strip() not in (b">", b"/>"):
        attribute = _ATTRIBUTE.match(raw, cursor, tag.end())
        if attribute is None:
            raise ValueError("Native color attributes cannot be located")
        if attribute[1] in (b"r", b"g", b"b"):
            result.append(
                (attribute[1].decode("ascii"), attribute.start(3), attribute.end(3))
            )
        cursor = attribute.end()
    if sorted(key for key, _start, _end in result) != list("bgr"):
        raise ValueError("Native color components cannot be located unambiguously")
    return result


def _source_palette(root: ET.Element) -> list[RGB]:
    rows = root.findall("./colortable/color")
    if len(root.findall("colortable")) != 1 or len(rows) < 2:
        raise ValueError("Producer requires one explicit background/foreground palette")
    result = []
    for row in rows:
        values = _components(row)
        rgb = _rgb8(values)
        if any(
            abs(value - Decimal(n) / 255) > _SOURCE_LIMIT
            for value, n in zip(values, rgb, strict=True)
        ):
            raise ValueError("Producer palette must contain canonical eight-bit RGB")
        result.append(rgb)
    return result


def _palette_analysis(colors: list[RGB]) -> list[dict[str, Any]]:
    rows = []
    for index, rgb in enumerate(colors, 2):
        native = tuple(
            int((Decimal(n) / 255).quantize(_FOUR_PLACES) * 255) for n in rgb
        )
        stable = tuple(
            min(_STABLE_CHANNELS, key=lambda value: (abs(value - n), -value))
            for n in rgb
        )
        rows.append(
            {
                "index": index,
                "authored_rgb8": list(rgb),
                "modeled_native_reopen_rgb8": list(native),
                "modeled_native_delta": [
                    b - a for a, b in zip(rgb, native, strict=True)
                ],
                "nearest_stable_rgb8": list(stable),
                "nearest_stable_delta": [
                    b - a for a, b in zip(rgb, stable, strict=True)
                ],
                "stable_without_changing_rgb": native == rgb,
            }
        )
    return rows


def _font_analysis(producer: ET.Element, native: ET.Element) -> dict[str, Any]:
    source, target = _Scene(producer), _Scene(native)
    left, right = source.texts(), target.texts()
    changes = []
    changed_text = []
    for key in sorted(left.keys() & right.keys()):
        a, b = left[key], right[key]
        text = "".join(run.text or "" for run in a.findall("s"))
        if text != "".join(run.text or "" for run in b.findall("s")):
            changed_text.append(list(key))
            continue
        before, after = source.runs(a), target.runs(b)
        pairs = [(x[0], y[0]) for x, y in zip(before, after, strict=True)]
        faces = [(x[2], y[2]) for x, y in zip(before, after, strict=True)]
        if any(a != b for a, b in pairs) or any(a != b for a, b in faces):
            changes.append(
                {
                    "path": list(key),
                    "text": text,
                    "font_pairs": [list(pair) for pair in sorted(set(pairs))],
                    "face_pairs": [list(pair) for pair in sorted(set(faces))],
                    "changed_font_characters": sum(a != b for a, b in pairs),
                    "changed_face_characters": sum(a != b for a, b in faces),
                }
            )
    return {
        "changed_text_objects": changes,
        "changed_text_content": changed_text,
        "missing_text_paths": [list(k) for k in sorted(left.keys() - right.keys())],
        "extra_text_paths": [list(k) for k in sorted(right.keys() - left.keys())],
        "physical_face_identity_verified": False,
        "meaning": "Logical font/style diagnostics; matching names do not prove matching glyphs.",
    }


def inspect_cdxml_roundtrip(
    producer: bytes, native: bytes | None = None
) -> dict[str, Any]:
    """Inspect the measured writer profile without changing RGB or font requests."""
    source = _root(producer)
    result: dict[str, Any] = {
        "version": 1,
        "scope": "font metadata and eight-bit palette only",
        "source_sha256": hashlib.sha256(producer).hexdigest(),
        "writer_profile": NATIVE_COLOR_PROFILE,
        "palette": _palette_analysis(_source_palette(source)),
        "nearest_stable_colors_applied": False,
        "full_fidelity_accepted": False,
    }
    if native is not None:
        target = _root(native)
        result["native_sha256"] = hashlib.sha256(native).hexdigest()
        result["native_creation_program"] = target.get("CreationProgram", "")
        result["fonts"] = _font_analysis(source, target)
    return result


def recover_native_cdxml_palette(
    producer: bytes, native: bytes
) -> tuple[bytes, dict[str, Any]]:
    """Recover a known first native SaveAs, retaining all non-palette bytes.

    The caller must supply the original producer and its first native save, not
    an arbitrary edited or repeatedly degraded document. This operation does not
    certify provenance, fonts, geometry, chemistry, or whole-document fidelity.
    Matching measured writer values cannot reveal byte-identical intentional
    edits or prove save history; it only rejects nonmatching palette numbers.
    """
    report = inspect_cdxml_roundtrip(producer, native)
    source, target = _root(producer), _root(native)
    if target.get("CreationProgram") != NATIVE_COLOR_PROFILE:
        raise ValueError(
            "Palette recovery requires the measured ChemDraw 25.0.2.14 profile"
        )
    validate_consumer_paint_colors(source, target)
    authorized = set(_source_palette(source))
    if len(target.findall("colortable")) != 1:
        raise ValueError("Palette recovery requires one explicit native color table")
    rows = target.findall("./colortable/color")
    starts = _palette_color_starts(native)
    if len(rows) < 2 or len(rows) != len(starts):
        raise ValueError("Native palette structure cannot be recovered unambiguously")
    replacements = []
    recovered = []
    expected_colors = []
    for index, (row, start) in enumerate(zip(rows, starts, strict=True), 2):
        values = _components(row)
        rgb = _rgb8(values)
        if rgb not in authorized:
            raise ValueError("Native palette contains a color absent from the producer")
        if any(
            value != (Decimal(n) / 255).quantize(_FOUR_PLACES)
            for value, n in zip(values, rgb, strict=True)
        ):
            raise ValueError(
                "Native color is not the exact measured native serialization"
            )
        components = {
            key: format(n / 255, ".17g") for key, n in zip("rgb", rgb, strict=True)
        }
        for key, begin, end in _component_spans(native, start):
            replacements.append((begin, end, components[key].encode("ascii")))
        expected_colors.append(rgb)
        recovered.append(
            {"index": index, "rgb8": list(rgb), "authored_rgb_delta": [0, 0, 0]}
        )
    content = native
    for start, end, replacement in reversed(replacements):
        content = content[:start] + replacement + content[end:]
    output_root = _root(content)
    if _source_palette(output_root) != expected_colors:
        raise ValueError("Recovered XML palette does not match the reported RGB")
    original_table = target.find("colortable")
    output_table = output_root.find("colortable")
    assert original_table is not None and output_table is not None
    target.remove(original_table)
    output_root.remove(output_table)
    if ET.tostring(target) != ET.tostring(output_root):
        raise ValueError("Palette recovery changed non-palette document data")
    report["recovery"] = {
        "output_sha256": hashlib.sha256(content).hexdigest(),
        "colors": recovered,
        "output_format": "CDXML",
        "non_palette_bytes_preserved": True,
        "paired_logical_paint_colors_match_producer": True,
        "exact_native_serialization_verified": True,
        "output_palette_verified": True,
        "required_after_each_native_save": True,
        "provenance_runtime_verified": False,
        "scope": "Known first native SaveAs only; cannot recover arbitrary edits or prior loss.",
    }
    return content, report
