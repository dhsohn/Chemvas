"""Visible ink bands for Qt-free reaction assembly packing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from chemvas.features.reaction_assembly.geometry import (
    _numbers,
    fragment_atom_bounds,
    parse_point,
    unattached_text_size,
)

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

Rect = tuple[float, float, float, float]
READABLE_CLEARANCE_PT = 4.0


@dataclass(frozen=True, slots=True)
class ContourBand:
    y_bottom: float
    y_top: float
    left: float
    right: float

    def shifted(self, *, dx: float = 0.0, dy: float = 0.0) -> ContourBand:
        return ContourBand(
            self.y_bottom + dy,
            self.y_top + dy,
            self.left + dx,
            self.right + dx,
        )


def _parse_bbox(value: str) -> Rect:
    left, top, right, bottom = _numbers(value, count=4)
    return left, top, right, bottom


def _rect_to_bands(rect: Rect) -> list[ContourBand]:
    left, top, right, bottom = rect
    if right <= left or bottom <= top:
        return []
    return [ContourBand(top, bottom, left, right)]


def _union_bands(bands: list[ContourBand]) -> list[ContourBand]:
    if not bands:
        return []
    events = sorted({band.y_bottom for band in bands} | {band.y_top for band in bands})
    merged: list[ContourBand] = []
    for y0, y1 in pairwise(events):
        if y1 <= y0:
            continue
        left = math.inf
        right = -math.inf
        for band in bands:
            if band.y_bottom < y1 and band.y_top > y0:
                left = min(left, band.left)
                right = max(right, band.right)
        if left < right:
            merged.append(ContourBand(y0, y1, left, right))
    return merged


def _stroke_bounds(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    half_width: float,
) -> Rect:
    x0, y0 = start
    x1, y1 = end
    left = min(x0, x1) - half_width
    right = max(x0, x1) + half_width
    top = min(y0, y1) - half_width
    bottom = max(y0, y1) + half_width
    return left, top, right, bottom


def _contracted_label_rect(node: ET.Element) -> Rect | None:
    node_type = node.get("NodeType")
    if node_type not in {"Nickname", "Fragment"}:
        return None
    text = node.find("t")
    if text is not None and (box := text.get("BoundingBox")):
        return _parse_bbox(box)
    point = parse_point(node.attrib["p"])
    return point[0] - 1.0, point[1] - 1.0, point[0] + 1.0, point[1] + 1.0


def _direct_fragment_rects(fragment: ET.Element) -> list[Rect]:
    rects: list[Rect] = []
    direct_atoms = {
        atom.get("id"): atom for atom in fragment.findall("n") if atom.get("id")
    }
    for atom in direct_atoms.values():
        contracted = _contracted_label_rect(atom)
        if contracted is not None:
            rects.append(contracted)
            continue
        point = parse_point(atom.attrib["p"])
        rects.append((point[0] - 1.0, point[1] - 1.0, point[0] + 1.0, point[1] + 1.0))
        text = atom.find("t")
        if text is not None and (box := text.get("BoundingBox")):
            rects.append(_parse_bbox(box))
    return rects


def fragment_contour_bands(
    fragment: ET.Element, *, half_bond_width: float
) -> list[ContourBand]:
    """Bands from direct atoms, visible labels and bond strokes only."""
    rects = _direct_fragment_rects(fragment)
    direct_atoms = {
        atom.get("id"): parse_point(atom.attrib["p"])
        for atom in fragment.findall("n")
        if atom.get("id")
    }
    for bond in fragment.findall("b"):
        start_id = bond.get("B")
        end_id = bond.get("E")
        if start_id not in direct_atoms or end_id not in direct_atoms:
            continue
        rects.append(
            _stroke_bounds(
                direct_atoms[start_id],
                direct_atoms[end_id],
                half_width=half_bond_width,
            )
        )
    return _union_bands([band for rect in rects for band in _rect_to_bands(rect)])


def fragment_contour_bands_in_placement_coords(
    fragment: ET.Element, *, half_bond_width: float
) -> list[ContourBand]:
    left, top, _, _ = fragment_atom_bounds(fragment)
    return [
        band.shifted(dx=-left, dy=-top)
        for band in fragment_contour_bands(fragment, half_bond_width=half_bond_width)
    ]


def text_contour_bands_in_placement_coords(text: ET.Element) -> list[ContourBand]:
    size = unattached_text_size(text)
    return [ContourBand(0.0, size.height, 0.0, size.width)]


def arrow_contour_bands_in_placement_coords(*, width: float) -> list[ContourBand]:
    return [ContourBand(-2.0, 2.0, 0.0, width)]


def painted_horizontal_extent(bands: list[ContourBand]) -> tuple[float, float]:
    if not bands:
        return 0.0, 0.0
    return min(band.left for band in bands), max(band.right for band in bands)


def line_width_half(root: ET.Element) -> float:
    try:
        width = float(root.get("LineWidth", "1"))
    except ValueError as exc:
        raise ValueError("invalid LineWidth") from exc
    if not math.isfinite(width) or width <= 0:
        raise ValueError("invalid LineWidth")
    return width * 0.5
