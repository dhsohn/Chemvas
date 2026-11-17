"""Native stroke metrics applied to the editor's editable arrow graphics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from chemvas.domain.document import Arrow


@dataclass(frozen=True)
class NativeArrowStyle:
    kind: str
    width: float
    bold_width: float
    bold: bool
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
        # CDXML arrowhead dimensions are expressed in hundredths of LineWidth;
        # ChemDraw strokes only the shaft of a Bold line at BoldWidth.
        result[index] = NativeArrowStyle(
            kind=baseline[identity]["kind"],
            width=width,
            bold_width=float(inherited("BoldWidth", "2")),
            bold="Bold" in line.split(),
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
    heads = QPainterPath()
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
            heads.moveTo(*tip)
            heads.lineTo(*wing)
            if style.solid:
                heads.lineTo(
                    tip[0] - style.head_size * dx, tip[1] - style.head_size * dy
                )
                heads.closeSubpath()
        else:
            heads.moveTo(*left)
            heads.lineTo(*tip)
            heads.lineTo(*right)
            if style.solid:
                heads.closeSubpath()

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
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    dashed = (
        style.dashed
        if record.kind == style.kind
        else record.kind in {"line_dashed", "dotted"}
    )
    bold = style.bold if record.kind == style.kind else record.kind == "line_bold"
    brush = QBrush(color) if style.solid else QBrush(Qt.BrushStyle.NoBrush)
    pen.setWidthF(style.width)
    if bold:
        if (
            heads.isEmpty()
            or dashed
            or not style.solid
            or style.bold_width <= style.width
        ):
            pen.setWidthF(style.bold_width)
        else:
            # Keep a solid head at its LineWidth size: thicken only the shaft
            # by filling its outline, then stroke the union at LineWidth.
            stroker = QPainterPathStroker()
            stroker.setWidth(style.bold_width - style.width)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return stroker.createStroke(path).united(heads), pen, brush
    if dashed and bold:
        # ChemDraw keeps a Bold line's dash period at the LineWidth scale, so
        # its dashes read as short bars rather than stretching with BoldWidth.
        # Qt dash lengths are in pen widths; flat caps keep the gaps open.
        dash = 4 * style.width / pen.widthF()
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setDashPattern([dash, dash])
    elif dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    path.addPath(heads)
    return path, pen, brush
