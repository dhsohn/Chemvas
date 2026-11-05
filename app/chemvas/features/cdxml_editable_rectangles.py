"""Map black native ChemDraw rectangles to editable shape records.

Chemvas shapes always stroke with ``renderer.style.bond_color`` (fixed
``#000000``); ``Shape`` has no stroke-color field. A coloured Plain rectangle
would therefore draw black, and a coloured Filled rectangle would gain a black
outline around its fill. Only rectangles Chemvas draws identically import as
shapes: Plain or Filled whose resolved ``reader.color(e)`` (including
``fgcolor`` remapping of index ``0``) is ``#000000``. Every other Plain/Filled
rectangle stays on the raster-image path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

_BLACK = "#000000"


def editable_rectangle(reader: Any, e: ET.Element) -> dict[str, Any] | None:
    """Return a shape record for a round-trippable black native rectangle, else None.

    Chemvas writes new rectangles as ``RectangleType`` Plain (no fill) or Filled
    (``color`` = fill, opaque). Import mirrors that contract only when the
    resolved native color is black so the Chemvas stroke matches. Any other
    rectangle styling stays on the raster-image path.
    """
    if e.tag != "graphic" or e.get("GraphicType") != "Rectangle":
        return None
    if e.get("SupersededBy"):
        return None
    rectangle_type = e.get("RectangleType")
    if rectangle_type not in {"Plain", "Filled"}:
        return None
    if e.get("LineType", "Solid") != "Solid":
        return None
    if "CornerRadius" in e.attrib:
        return None
    resolved = reader.color(e)
    if resolved != _BLACK:
        return None
    bounds = e.get("BoundingBox", "").split()
    if len(bounds) != 4:
        reader.unsupported(e, "rectangle bounds")
    left, top, right, bottom = (reader.number(v, e) for v in bounds)
    left, right = sorted((left - reader.offset[0], right - reader.offset[0]))
    top, bottom = sorted((top - reader.offset[1], bottom - reader.offset[1]))
    record: dict[str, Any] = {
        "kind": "shape",
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "shape_kind": "rect",
        "stroke_style": "solid",
    }
    # Reverse of cdxml_new_objects: Plain → no fill (CDXML ``color`` is the
    # stroke; Shape has no stroke-color field); Filled → fill = black
    # (graphic_image paints stroke and fill with that same color).
    if rectangle_type == "Filled":
        record["fill"] = _BLACK
    return record


def update_rectangle(
    e: ET.Element,
    before: dict[str, Any],
    after: dict[str, Any],
    offset: list[float],
    color_index: Any,
) -> None:
    """Rewrite owned geometry and color; refuse edits with no native form."""
    if (
        after.get("shape_kind", "rect") != "rect"
        or before.get("shape_kind", "rect") != "rect"
    ):
        raise ValueError(
            "Native rectangle shape_kind changes are unsupported; the file was not replaced."
        )
    if (
        after.get("stroke_style", "solid") != "solid"
        or before.get("stroke_style", "solid") != "solid"
    ):
        raise ValueError(
            "Native rectangle stroke_style changes are unsupported; the file was not replaced."
        )
    if after.get("rotation", 0) != before.get("rotation", 0):
        raise ValueError(
            "Rotation of native rectangles is not yet supported; the file was not replaced."
        )
    after_fill = after.get("fill")
    before_fill = before.get("fill")
    after_alpha = after.get("fill_alpha", 1 if after_fill is not None else None)
    before_alpha = before.get("fill_alpha", 1 if before_fill is not None else None)
    if after_fill is not None and after_alpha != 1:
        raise ValueError("Translucent native rectangles are unsupported.")

    e.set(
        "BoundingBox",
        f"{after['left'] + offset[0]:.12g} {after['top'] + offset[1]:.12g} "
        f"{after['right'] + offset[0]:.12g} {after['bottom'] + offset[1]:.12g}",
    )

    color_changed = after_fill != before_fill or after_alpha != before_alpha
    if not color_changed:
        return

    if after_fill is not None:
        # new_objects: fill → Filled with color = fill (stroke matches fill).
        # Recoloring a Plain stroke through Chemvas sets fill and becomes Filled.
        e.set("RectangleType", "Filled")
        e.set("color", color_index(after_fill))
        return

    e.set("RectangleType", "Plain")
    # Explicit black so a document with non-black fgcolor still reopens black
    # (allocate_native_color_index avoids emitting 0 when fgcolor remaps it).
    # Geometry-only edits return above and leave an existing Plain color alone.
    e.set("color", color_index(_BLACK))
