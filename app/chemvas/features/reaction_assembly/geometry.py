from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

Point = tuple[float, float]
Rect = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Size:
    width: float
    height: float


def _numbers(value: str, *, count: int | None = None) -> tuple[float, ...]:
    parts = value.split()
    if count is not None and len(parts) != count:
        raise ValueError(f"expected {count} coordinates, got {len(parts)}")
    result: list[float] = []
    for token in parts:
        try:
            number = float(token)
        except ValueError as exc:
            raise ValueError(f"invalid coordinate {token!r}") from exc
        if not math.isfinite(number):
            raise ValueError(f"non-finite coordinate {token!r}")
        result.append(number)
    return tuple(result)


def parse_point(value: str) -> Point:
    x, y = _numbers(value, count=2)
    return x, y


def format_point(point: Point) -> str:
    return f"{point[0]:.12g} {point[1]:.12g}"


def format_bbox(rect: Rect) -> str:
    left, top, right, bottom = rect
    return f"{left:.12g} {top:.12g} {right:.12g} {bottom:.12g}"


def format_point3(point: Point, z: float = 0.0) -> str:
    return f"{point[0]:.12g} {point[1]:.12g} {z:.12g}"


def fragment_atom_bounds(fragment: ET.Element) -> Rect:
    """Bounding box of drawable atom positions inside a fragment subtree."""
    if value := fragment.get("BoundingBox"):
        left, top, right, bottom = _numbers(value, count=4)
        if right > left and bottom > top:
            return left, top, right, bottom
    points = [parse_point(n.attrib["p"]) for n in fragment.findall("n")]
    for t in fragment.findall("./n/t"):
        if value := t.get("BoundingBox"):
            left, top, right, bottom = _numbers(value, count=4)
            points.extend(((left, top), (right, bottom)))
    if not points:
        raise ValueError("fragment has no positioned atoms")
    xs, ys = zip(*points, strict=True)
    return min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4


def fragment_local_origin(fragment: ET.Element) -> Point:
    left, top, _, _ = fragment_atom_bounds(fragment)
    return left, top


def fragment_drawable_size(fragment: ET.Element) -> Size:
    left, top, right, bottom = fragment_atom_bounds(fragment)
    return Size(right - left, bottom - top)


def _default_size(text: ET.Element) -> float:
    for run in text.findall("s"):
        if run.get("size"):
            return float(run.get("size", "10"))
    return 10.0


def _run_extents(run: ET.Element, *, default_size: float) -> tuple[float, float]:
    text = run.text or ""
    try:
        size = float(run.get("size", str(default_size)))
    except ValueError as exc:
        raise ValueError("invalid text size") from exc
    if not 0 < size <= 1000:
        raise ValueError("text size out of range")
    face = int(run.get("face", "0"))
    width_factor = 0.62 if face & 1 else 0.55
    width = max(len(text), 1) * size * width_factor
    height = size * (1.35 if face & 0x60 else 1.2)
    return width, height


def unattached_text_size(text: ET.Element) -> Size:
    runs = list(text.findall("s"))
    if not runs:
        return Size(width=12.0, height=12.0)
    default = _default_size(text)
    width = 0.0
    height = 0.0
    for run in runs:
        run_width, run_height = _run_extents(run, default_size=default)
        width += run_width
        height = max(height, run_height)
    return Size(width=max(width, 1.0), height=max(height, 1.0))


def plain_text(element: ET.Element) -> str:
    return "".join(run.text or "" for run in element.findall("s")).strip()


def translate_coordinates(element: ET.Element, dx: float, dy: float) -> None:
    for node in element.iter():
        if position := node.get("p"):
            x, y = parse_point(position)
            node.set("p", format_point((x + dx, y + dy)))
        if box := node.get("BoundingBox"):
            left, top, right, bottom = _numbers(box, count=4)
            node.set(
                "BoundingBox",
                format_bbox((left + dx, top + dy, right + dx, bottom + dy)),
            )
        if node.tag == "arrow":
            for key in ("Head3D", "Tail3D"):
                if value := node.get(key):
                    x, y, z = _numbers(value, count=3)
                    node.set(key, format_point3((x + dx, y + dy), z))
        if curve := node.get("CurvePoints"):
            points = _numbers(curve)
            if len(points) % 2:
                raise ValueError("curve points must be paired")
            shifted = [
                value + (dx if index % 2 == 0 else dy)
                for index, value in enumerate(points)
            ]
            node.set("CurvePoints", " ".join(f"{value:.12g}" for value in shifted))
