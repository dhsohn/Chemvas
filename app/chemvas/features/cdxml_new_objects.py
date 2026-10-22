"""Native serialization for objects added to a source-preserving document."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


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
            else:
                raise ValueError(
                    f"New {kind} are not yet supported in a preserved CDXML document; the file was not replaced."
                )


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
