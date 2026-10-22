"""Native stroke metrics applied to the editor's editable arrow graphics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from chemvas.domain.document import Arrow


@dataclass(frozen=True)
class NativeArrowStyle:
    kind: str
    width: float
    head_size: float
    head_width: float
    spacing: float
    solid: bool
    dashed: bool
    z: float


def native_arrow_styles(state: dict[str, Any]) -> dict[int, NativeArrowStyle]:
    source = state.get("cdxml_source")
    if source is None:
        return {}
    from chemvas.features.cdxml_graphics import native_image_z
    from chemvas.features.cdxml_preservation import PreservingImporter

    reader = PreservingImporter(source["xml"])
    root, parents = reader.root, reader.parents
    byid = {e.get("id"): e for e in root.iter()}
    baseline = dict(
        zip(
            source["baseline_items"].get("arrows", []),
            source["baseline"].get("arrows", []),
            strict=True,
        )
    )
    result = {}
    for index, identity in enumerate(source["items"].get("arrows", [])):
        if identity is None or identity not in baseline:
            continue
        e = byid[identity]

        def inherited(key: str, default: str, node: ET.Element = e) -> float:
            while key not in node.attrib and node in parents:
                node = parents[node]
            return float(node.get(key, default))

        line = e.get("LineType", "Solid")
        width = inherited("LineWidth", "0.6")
        # CDXML arrowhead dimensions are expressed in hundredths of LineWidth.
        result[index] = NativeArrowStyle(
            kind=baseline[identity]["kind"],
            width=width,
            head_size=float(e.get("HeadSize", "600")) * width / 100,
            head_width=float(e.get("ArrowheadWidth", "200")) * width / 100,
            spacing=max(
                3 * width, float(e.get("ArrowShaftSpacing", "300")) * width / 100
            ),
            solid=e.get("ArrowheadType", "Solid") == "Solid",
            dashed="Dashed" in line,
            z=native_image_z(reader, e),
        )
    return result


def native_arrow_paint(record: Arrow, style: NativeArrowStyle):
    """Rebuild vector geometry from live endpoints using the source's metrics."""
    path = QPainterPath()
    a, b = record.start, record.end
    length = math.dist(a, b)
    ux, uy = ((b[0] - a[0]) / length, (b[1] - a[1]) / length) if length else (1.0, 0.0)

    def shaft(start, end):
        path.moveTo(*start)
        path.lineTo(*end)

    def head(tip, dx, dy, half=False):
        left = (
            tip[0] - style.head_size * dx + style.head_width * dy,
            tip[1] - style.head_size * dy - style.head_width * dx,
        )
        right = (
            tip[0] - style.head_size * dx - style.head_width * dy,
            tip[1] - style.head_size * dy + style.head_width * dx,
        )
        if half:
            wing = right if record.mirrored else left
            path.moveTo(*tip)
            path.lineTo(*wing)
            if style.solid:
                path.lineTo(
                    tip[0] - style.head_size * dx, tip[1] - style.head_size * dy
                )
                path.closeSubpath()
        else:
            path.moveTo(*left)
            path.lineTo(*tip)
            path.lineTo(*right)
            if style.solid:
                path.closeSubpath()

    if record.kind == "equilibrium":
        side = 1 if record.mirrored else -1
        nx, ny = -uy * style.spacing / 2 * side, ux * style.spacing / 2 * side
        upper_a, upper_b = (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny)
        lower_a, lower_b = (a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny)
        shaft(upper_a, upper_b)
        shaft(lower_a, lower_b)
        head(upper_b, ux, uy, True)
        head(lower_a, -ux, -uy, True)
    else:
        shaft(a, b)
        if record.kind in {"arrow", "dotted"}:
            head(b, ux, uy)
    color = QColor(record.color or "#000000")
    pen = QPen(color)
    pen.setWidthF(style.width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    dashed = (
        style.dashed
        if record.kind == style.kind
        else record.kind in {"line_dashed", "dotted"}
    )
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    brush = QBrush(color) if style.solid else QBrush(Qt.BrushStyle.NoBrush)
    return path, pen, brush
