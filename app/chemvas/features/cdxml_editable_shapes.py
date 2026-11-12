"""Editable projections of filled native rectangles and circles."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from chemvas.features.cdxml_graphics import native_image_z

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
    from collections.abc import Callable

    from chemvas.features.cdxml_preservation import PreservingImporter

_AXIS_KEYS = ("Center3D", "MajorAxisEnd3D", "MinorAxisEnd3D")
# ChemDraw rounds both ends of an axis independently to hundredths of a point.
_AXIS_TOLERANCE = 0.02


def editable_shape(reader: PreservingImporter, e: ET.Element) -> dict[str, Any] | None:
    if e.tag != "graphic" or len(e) or e.get("LineType", "") not in {"", "Solid"}:
        return None
    if e.get("GraphicType") == "Rectangle" and e.get("RectangleType") == "Filled":
        kind = "rect"
    elif e.get("GraphicType") == "Oval" and e.get("OvalType") == "Circle Filled":
        kind = "circle"
    else:
        return None

    width = reader.number(reader.inherited(e, "LineWidth", "0.6"), e)
    if not 0 <= width <= 100:
        reader.unsupported(e, "line width")
    if "LineWidth" in e.attrib and width > 0:
        return None
    # ChemDraw omits local LineWidth when resaving these fill-only graphics,
    # even if the document has a positive default width.
    bounds = _shape_bounds(reader, e, kind)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    ox, oy = reader.offset
    return {
        "kind": "shape",
        "left": left - ox,
        "top": top - oy,
        "right": right - ox,
        "bottom": bottom - oy,
        "shape_kind": kind,
        "stroke_style": "none",
        "fill": reader.color(e),
        "fill_alpha": 1.0,
        "z": native_image_z(reader, e, bounds=bounds),
    }


def _shape_bounds(
    reader: PreservingImporter, e: ET.Element, kind: str
) -> tuple[float, float, float, float] | None:
    raw_box = e.get("BoundingBox", "").split()
    if len(raw_box) != 4:
        return None
    x1, y1, x2, y2 = (reader.number(value, e) for value in raw_box)
    axes = None
    if any(key in e.attrib for key in _AXIS_KEYS):
        points = [e.get(key, "").split() for key in _AXIS_KEYS]
        if any(len(point) != 3 for point in points):
            return None
        try:
            center, major, minor = (
                tuple(reader.number(value, e) for value in point) for point in points
            )
        except ValueError:
            return None
        if any(point[2] != 0 for point in (center, major, minor)):
            return None
        cx, cy = center[:2]
        axes = (major[0] - cx, major[1] - cy, minor[0] - cx, minor[1] - cy)

    if kind == "rect":
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if left == right or top == bottom:
            return None
        if axes is not None:
            ax, ay, bx, by = axes
            half_width, half_height = (right - left) / 2, (bottom - top) / 2
            tol = _AXIS_TOLERANCE
            horizontal_first = (
                max(
                    abs(abs(ax) - half_width),
                    abs(ay),
                    abs(bx),
                    abs(abs(by) - half_height),
                )
                <= tol
            )
            vertical_first = (
                max(
                    abs(ax),
                    abs(abs(ay) - half_height),
                    abs(abs(bx) - half_width),
                    abs(by),
                )
                <= tol
            )
            if (
                abs(cx - (left + right) / 2) > tol
                or abs(cy - (top + bottom) / 2) > tol
                or not (horizontal_first or vertical_first)
            ):
                return None
        return left, top, right, bottom

    if axes is None:
        cx, cy = x2, y2
        radius = math.hypot(x1 - cx, y1 - cy)
    else:
        ax, ay, bx, by = axes
        major_radius, minor_radius = math.hypot(ax, ay), math.hypot(bx, by)
        radius = min(major_radius, minor_radius)
        if abs(major_radius - minor_radius) > _AXIS_TOLERANCE or abs(
            ax * bx + ay * by
        ) > _AXIS_TOLERANCE * (major_radius + minor_radius):
            return None
    if radius == 0:
        return None
    return cx - radius, cy - radius, cx + radius, cy + radius


def update_shape(
    e: ET.Element,
    before: dict[str, Any],
    after: dict[str, Any],
    offset: list[float],
    color_index: Callable[[str], str],
) -> None:
    """Write the supported edits without rewriting unchanged native attributes."""
    if after["shape_kind"] != before["shape_kind"]:
        raise ValueError("Native shape kind change is unsupported.")
    if after["stroke_style"] != "none":
        raise ValueError("Native shape stroke change is unsupported.")
    if not after.get("fill") or after.get("fill_alpha", 1) != 1:
        raise ValueError("Native shapes require an opaque fill.")

    keys = ("left", "top", "right", "bottom")
    if any(before[key] != after[key] for key in keys):
        from chemvas.features.cdxml_native_writer import transform_native

        ox, oy = offset
        left, top, right, bottom = (after[key] for key in keys)
        width, height = right - left, bottom - top
        if min(width, height) <= 0:
            raise ValueError("Degenerate native shape bounds.")
        if after["shape_kind"] == "rect":
            sx = width / (before["right"] - before["left"])
            sy = height / (before["bottom"] - before["top"])
            tx = left + ox - sx * (before["left"] + ox)
            ty = top + oy - sy * (before["top"] + oy)
            transform_native(e, sx=sx, sy=sy, tx=tx, ty=ty)
        else:
            # Match the canvas: an irregular resize box inscribes a circle
            # centred in that box, with the shorter side as its diameter.
            cx, cy = (left + right) / 2 + ox, (top + bottom) / 2 + oy
            radius = min(width, height) / 2
            if max(abs(cx) + radius, abs(cy) + radius) > 1_000_000:
                raise ValueError("Native coordinate transform exceeds limits.")
            e.set("BoundingBox", f"{cx + radius:.12g} {cy:.12g} {cx:.12g} {cy:.12g}")
            e.set("Center3D", f"{cx:.12g} {cy:.12g} 0")
            e.set("MajorAxisEnd3D", f"{cx + radius:.12g} {cy:.12g} 0")
            e.set("MinorAxisEnd3D", f"{cx:.12g} {cy + radius:.12g} 0")
    if after["fill"] != before["fill"]:
        e.set("color", color_index(after["fill"]))
