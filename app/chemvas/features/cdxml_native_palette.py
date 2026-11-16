"""Qt-free native CDXML color-index allocation shared by native writers.

Indices 0/1 are absolute black/white, independent of document attributes.
Indices 2/3 are the default background/foreground. When creating a table,
materialize its implicit white/black defaults before allocating other colors.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from chemvas.domain.document.state_values import is_hex_color


def allocate_native_color_index(root: ET.Element, color: str) -> str:
    """Return a CDXML color index for ``color``, allocating a table row if needed."""
    if not is_hex_color(color):
        raise ValueError(
            f"native color must be #rgb or #rrggbb hexadecimal, got {color!r}"
        )
    value = color.lower()
    if len(value) == 4:
        value = "#" + "".join(digit * 2 for digit in value[1:])
    if value == "#000000":
        return "0"
    if value == "#ffffff":
        return "1"
    table = root.find("colortable")
    if table is None:
        table = ET.SubElement(root, "colortable")
        ET.SubElement(table, "color", r="1", g="1", b="1")
        ET.SubElement(table, "color", r="0", g="0", b="0")
    target = tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    for i, entry in enumerate(table):
        if (
            tuple(round(float(entry.get(k, "0")) * 255) for k in ("r", "g", "b"))
            == target
        ):
            return str(i + 2)
    ET.SubElement(
        table,
        "color",
        {
            k: f"{channel / 255:.12g}"
            for k, channel in zip(("r", "g", "b"), target, strict=True)
        },
    )
    return str(len(table) + 1)
