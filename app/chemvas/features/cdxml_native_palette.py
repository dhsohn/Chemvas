"""Qt-free native CDXML color-index allocation shared by native writers.

Index 0 is the document foreground: when ``fgcolor`` is absent or ``0`` it is
absolute black; otherwise importers remap ``0`` through ``fgcolor``. Index 1 is
absolute white. Indices ``>= 2`` are ``colortable`` entries; index 2 is the
conventional document/page ``bgcolor`` slot (often white) and index 3 is the
conventional default object color (often black). Writers must not emit ``0`` for
absolute black while ``fgcolor`` names a non-black palette color.
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
    if value == "#000000" and root.get("fgcolor", "0") == "0":
        return "0"
    if value == "#ffffff":
        return "1"
    table = root.find("colortable")
    if table is None:
        table = ET.SubElement(root, "colortable")
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
