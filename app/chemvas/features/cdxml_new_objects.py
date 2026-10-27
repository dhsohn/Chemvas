"""Native serialization for objects added to a source-preserving document."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any

from chemvas.domain.document.cdxml_charge_edits import MARK_SYMBOLS

_GLYPH_SIZE = 7.5
_MARK_TEXT = {1: {"+", "⊕"}, -1: {"-", "−", "⊖"}}


def append_new_objects(
    root: ET.Element,
    state: dict[str, Any],
    *,
    fresh: Any,
    color_index: Any,
    note_writer: Any,
    atom_native: dict[str, str],
) -> None:
    source = state["cdxml_source"]
    offset = source["offset"]
    page = root.find("page")
    assert page is not None
    atoms = {str(k): v for k, v in state["model"]["atoms"].items()}
    mark_z = _top_z(root)

    def point(value: list[float] | tuple[float, ...]) -> str:
        return f"{value[0] + offset[0]:.12g} {value[1] + offset[1]:.12g} 0"

    def box(record: dict[str, Any]) -> str:
        return f"{record['left'] + offset[0]:.12g} {record['top'] + offset[1]:.12g} {record['right'] + offset[0]:.12g} {record['bottom'] + offset[1]:.12g}"

    for kind in (
        "notes",
        "arrows",
        "shapes",
        "marks",
        "images",
        "orbitals",
        "ts_brackets",
    ):
        records = state.get(kind, [])
        bindings = source["items"].get(kind, [None] * len(records))
        for identity, item in zip(bindings, records, strict=True):
            if identity is not None:
                continue
            if kind == "notes":
                if note_writer is None:
                    raise ValueError("Native caption writer is required.")
                e = ET.SubElement(
                    page,
                    "t",
                    id=fresh(),
                    p=f"{item['x'] + offset[0]:.12g} {item['y'] + offset[1] + float(root.get('CaptionSize', '12')):.12g}",
                )
                note_writer(root, e, item)
            elif kind == "arrows":
                _append_arrow(page, item, point, fresh, color_index)
            elif kind == "shapes":
                if (
                    item["shape_kind"] != "rect"
                    or item.get("stroke_style", "solid") != "solid"
                ):
                    raise ValueError(
                        "This new shape has no native CDXML representation yet."
                    )
                e = ET.SubElement(
                    page,
                    "graphic",
                    id=fresh(),
                    GraphicType="Rectangle",
                    BoundingBox=box(item),
                    RectangleType="Plain",
                )
                if item.get("fill"):
                    if item.get("fill_alpha", 1) != 1:
                        raise ValueError(
                            "Translucent native rectangles are unsupported."
                        )
                    e.set("RectangleType", "Filled")
                    e.set("color", color_index(item["fill"]))
            elif kind == "marks":
                mark_z += 1
                _append_mark(
                    page, item, atoms, offset, fresh, color_index, atom_native, mark_z
                )
            else:
                raise ValueError(
                    f"New {kind} are not yet supported in a preserved CDXML document; the file was not replaced."
                )


def _append_mark(
    page: ET.Element,
    item: dict[str, Any],
    atoms: dict[str, Any],
    offset: Any,
    fresh: Any,
    color_index: Any,
    atom_native: dict[str, str],
    z: int,
) -> None:
    # The atom Charge itself is written by the native writer's charge plan.
    kind = item.get("kind")
    if not isinstance(kind, str) or kind not in MARK_SYMBOLS:
        raise ValueError(
            f"New {kind} marks are not yet supported in a preserved CDXML document; the file was not replaced."
        )
    symbol, charge = MARK_SYMBOLS[kind]
    if item.get("text") not in {None, *_MARK_TEXT[charge]}:
        raise ValueError("Custom charge mark text has no native CDXML representation.")
    x, y = item["x"], item["y"]
    atom_id = item.get("atom_id")
    if atom_id is not None:
        atom = atoms[str(atom_id)]
        dx, dy = item.get("dx"), item.get("dy")
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            x, y = atom["x"] + dx, atom["y"] + dy
    cx, cy = x + offset[0], y + offset[1]
    # Symbol bounds: glyph center first, then a point one glyph size away.
    graphic = ET.SubElement(
        page,
        "graphic",
        id=fresh(),
        GraphicType="Symbol",
        SymbolType=symbol,
        BoundingBox=f"{cx:.12g} {cy:.12g} {cx - _GLYPH_SIZE:.12g} {cy:.12g}",
        color=color_index(item.get("color") or "#000000"),
        Z=str(z),
    )
    if atom_id is not None:
        ET.SubElement(
            graphic,
            "represent",
            attribute="Charge",
            object=atom_native[str(atom_id)],
        )


def _top_z(root: ET.Element) -> int:
    # New marks stack above every existing native object, so reopening keeps
    # them over the molecule instead of behind it (missing Z reads as 0).
    top = 0
    for e in root.iter():
        try:
            z = float(e.get("Z", ""))
        except ValueError:
            continue
        if math.isfinite(z):
            top = max(top, math.floor(z))
    return top


def _append_arrow(
    page: ET.Element, item: dict[str, Any], point: Any, fresh: Any, color_index: Any
) -> None:
    kind = item["kind"]
    color = color_index(item.get("color", "#000000"))
    if kind in {"curved_single", "curved_double"}:
        a, b = item["start"], item["end"]
        control = item.get("control")
        if control is None:
            raise ValueError("Curved arrow requires a control point.")
        c1 = [a[i] + 2 / 3 * (control[i] - a[i]) for i in range(2)]
        c2 = [b[i] + 2 / 3 * (control[i] - b[i]) for i in range(2)]
        coords = " ".join(" ".join(point(p).split()[:2]) for p in (a, a, c1, c2, b, b))
        ET.SubElement(
            page,
            "curve",
            id=fresh(),
            CurvePoints=coords,
            ArrowheadHead="Full" if kind == "curved_double" else "HalfLeft",
            ArrowheadType="Solid",
            color=color,
        )
        return
    head, tail = {
        "arrow": ("Full", "None"),
        "dotted": ("Full", "None"),
        "line": ("None", "None"),
        "line_dashed": ("None", "None"),
        "line_bold": ("None", "None"),
        "equilibrium": ("HalfRight", "HalfRight")
        if item.get("mirrored")
        else ("HalfLeft", "HalfLeft"),
    }.get(kind, (None, None))
    if head is None or tail is None:
        raise ValueError(f"New native arrow type {kind} is unsupported.")
    e = ET.SubElement(
        page,
        "arrow",
        id=fresh(),
        Head3D=point(item["end"]),
        Tail3D=point(item["start"]),
        ArrowheadHead=head,
        ArrowheadTail=tail,
        ArrowheadType="Solid",
        color=color,
    )
    if kind in {"line_dashed", "dotted"}:
        e.set("LineType", "Dashed")
    if kind == "line_bold":
        e.set("LineWidth", "2")
    if any(item.get("labels", {}).values()):
        raise ValueError("Native arrow labels require separate text objects.")
