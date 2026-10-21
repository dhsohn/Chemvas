"""Bounded display projections for retained native CDXML vector objects.

The PNG is an editor projection only. CDXML save transforms the original vector
object; it never substitutes this raster for native curves, arrows or graphics.
"""

from __future__ import annotations

import io
import math
from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

from chemvas.domain.document.images import MAX_IMAGE_BYTES, image_state_from_bytes


def graphic_image(reader: Any, e: ET.Element) -> dict[str, object] | None:
    if e.tag == "curve" and not e.get("CurvePoints", "").strip():
        # Native files can retain empty drawing records; keep their XML without ink.
        return None
    return _GraphicProjection(reader, e).render()


def native_image_z(reader: Any, e: ET.Element) -> float:
    if e.tag == "ColoredMolecularArea":
        return -3.0
    chemical = reader.nodes + reader.native_bonds
    if chemical and reader.number(e.get("Z", "0"), e) < min(
        reader.number(node.get("Z", "0"), node) for node in chemical
    ):
        return -3.0
    return 1.0


def embedded_image(reader: Any, e: ET.Element) -> dict[str, object]:
    """Display a bounded PNG preview while retaining every native representation."""
    encoded = e.get("PNG", "")
    if not encoded or len(encoded) > 2 * MAX_IMAGE_BYTES:
        reader.unsupported(e, "missing or oversized embedded PNG preview")
    try:
        data = bytes.fromhex(encoded)
    except ValueError as exc:
        raise ValueError("Invalid embedded CDXML PNG encoding.") from exc
    bounds = e.get("BoundingBox", "").split()
    if len(bounds) != 4:
        reader.unsupported(e, "embedded image bounds")
    left, top, right, bottom = [reader.number(v, e) for v in bounds]
    return image_state_from_bytes(
        data,
        x=left - reader.offset[0],
        y=top - reader.offset[1],
        width=right - left,
        height=bottom - top,
        z=native_image_z(reader, e),
    )


class _GraphicProjection:
    def __init__(self, reader: Any, e: ET.Element) -> None:
        self.reader = reader
        self.e = e
        self.color = self.reader.color(self.e)
        self.width = self.reader.number(
            self.reader.inherited(self.e, "LineWidth", "0.6"), self.e
        )
        if not 0 < self.width <= 100:
            self.reader.unsupported(self.e, "line width")
        self.paths: list[tuple[list[tuple[float, float]], bool, str | None]] = []
        self.tag = self.e.tag
        self.kind = self.e.get("GraphicType", "")

    def points(self, value: str) -> list[tuple[float, float]]:
        coords = [self.reader.number(v, self.e) for v in value.split()]
        if len(coords) % 2:
            self.reader.unsupported(self.e, "point array")
        return list(zip(coords[::2], coords[1::2], strict=True))

    def point3(self, name: str) -> tuple[float, float]:
        values = [self.reader.number(v, self.e) for v in self.e.get(name, "").split()]
        if len(values) != 3 or values[2] != 0:
            self.reader.unsupported(self.e, "3D graphic")
        return (values[0], values[1])

    def ellipse(
        self,
        center: tuple[float, float],
        major: tuple[float, float],
        minor: tuple[float, float],
        filled: bool = False,
    ) -> None:
        cx, cy = center
        ux, uy = (major[0] - cx, major[1] - cy)
        vx, vy = (minor[0] - cx, minor[1] - cy)
        ps = [
            (
                cx + ux * math.cos(t) + vx * math.sin(t),
                cy + uy * math.cos(t) + vy * math.sin(t),
            )
            for t in [2 * math.pi * i / 96 for i in range(97)]
        ]
        self.paths.append((ps, True, self.color if filled else None))

    def head(
        self, tip: tuple[float, float], prev: tuple[float, float], kind: str = "Full"
    ) -> None:
        dx, dy = (tip[0] - prev[0], tip[1] - prev[1])
        length = math.hypot(dx, dy)
        if not length:
            return
        ux, uy = (dx / length, dy / length)
        size = (
            self.reader.number(self.e.get("HeadSize", "600"), self.e) * self.width / 100
        )
        spread = (
            self.reader.number(self.e.get("ArrowheadWidth", "200"), self.e)
            * self.width
            / 100
        )
        left = (tip[0] - size * ux + spread * uy, tip[1] - size * uy - spread * ux)
        right = (tip[0] - size * ux - spread * uy, tip[1] - size * uy + spread * ux)
        solid = self.e.get("ArrowheadType", "Solid") == "Solid"
        if kind in ("HalfLeft", "HalfRight"):
            wing = left if kind == "HalfLeft" else right
            points = (
                [tip, wing, (tip[0] - size * ux, tip[1] - size * uy)]
                if solid
                else [tip, wing]
            )
            self.paths.append((points, solid, self.color if solid else None))
        else:
            self.paths.append(
                ([left, tip, right], solid, self.color if solid else None)
            )

    def curve(self) -> None:
        ps = self.points(self.e.get("CurvePoints", ""))
        if len(ps) < 6 or len(ps) % 3:
            self.reader.unsupported(self.e, "Bezier control points")
        curve = [ps[1]]
        for i in range(1, len(ps) - 3, 3):
            a, b, c, d = ps[i : i + 4]
            for step in range(1, 33):
                t = step / 32
                q = 1 - t
                curve.append(
                    (
                        q**3 * a[0]
                        + 3 * q * q * t * b[0]
                        + 3 * q * t * t * c[0]
                        + t**3 * d[0],
                        q**3 * a[1]
                        + 3 * q * q * t * b[1]
                        + 3 * q * t * t * c[1]
                        + t**3 * d[1],
                    )
                )
        closed = self.e.get("Closed", "no") == "yes" or "Closed" in self.e.get(
            "CurveType", ""
        )
        self.paths.append(
            (
                curve,
                closed,
                self.color if "Filled" in self.e.get("CurveType", "") else None,
            )
        )

        head_kind = self.e.get("ArrowheadHead", "None")
        tail_kind = self.e.get("ArrowheadTail", "None")
        if head_kind != "None":
            self.head(curve[-1], curve[-2], head_kind)
        if tail_kind != "None":
            self.head(curve[0], curve[1], tail_kind)

    def arrow(self) -> None:
        tail, tip = (self.point3("Tail3D"), self.point3("Head3D"))
        angle = self.reader.number(self.e.get("AngularSize", "0"), self.e)
        if angle:
            center = self.point3("Center3D")
            radius = math.dist(tail, center)
            start = math.atan2(tail[1] - center[1], tail[0] - center[0])
            # CDXML angles are counterclockwise in Cartesian coordinates;
            # canvas y grows downward, so the visible sweep has the opposite sign.
            delta = -math.radians(angle)
            curve = [
                (
                    center[0] + radius * math.cos(start + delta * i / 96),
                    center[1] + radius * math.sin(start + delta * i / 96),
                )
                for i in range(97)
            ]
        else:
            curve = [tail, tip]
        head_kind = self.e.get("ArrowheadHead", "None")
        tail_kind = self.e.get("ArrowheadTail", "None")
        if head_kind.startswith("Half") and tail_kind.startswith("Half"):
            length = math.dist(tail, tip)
            if not length:
                self.reader.unsupported(self.e, "zero-length equilibrium arrow")
            gap = max(
                self.width * 3,
                self.reader.number(self.e.get("ArrowShaftSpacing", "300"), self.e)
                * self.width
                / 100,
            )
            nx, ny = (
                -(tip[1] - tail[1]) / length * gap / 2,
                (tip[0] - tail[0]) / length * gap / 2,
            )
            upper, lower = [], []
            for i, p in enumerate(curve):
                if angle:
                    prev, following = (
                        curve[max(0, i - 1)],
                        curve[min(len(curve) - 1, i + 1)],
                    )
                    distance = math.dist(prev, following)
                    nx = -(following[1] - prev[1]) / distance * gap / 2
                    ny = (following[0] - prev[0]) / distance * gap / 2
                side = -1 if head_kind == "HalfLeft" else 1
                upper.append((p[0] + side * nx, p[1] + side * ny))
                lower.append((p[0] - side * nx, p[1] - side * ny))
            self.paths.extend(((upper, False, None), (lower, False, None)))
            self.head(upper[-1], upper[-2], head_kind)
            self.head(lower[0], lower[1], tail_kind)
            return
        self.paths.append((curve, False, None))
        if head_kind != "None":
            self.head(curve[-1], curve[-2], head_kind)
        if tail_kind != "None":
            self.head(curve[0], curve[1], tail_kind)

    def area(self) -> None:
        ids = set(self.e.get("BasisObjects", "").split())
        positions = {
            n.get("id"): (
                float(n.get("p", "").split()[0]),
                float(n.get("p", "").split()[1]),
            )
            for n in self.reader.nodes
        }
        atom_ids = set(ids)
        for bond in self.reader.native_bonds:
            if bond.get("id") in ids:
                atom_ids.update((bond.get("B"), bond.get("E")))
        ps = [positions[identity] for identity in atom_ids if identity in positions]
        if ps:
            cx, cy = (
                sum(p[0] for p in ps) / len(ps),
                sum(p[1] for p in ps) / len(ps),
            )
            ps.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        if len(ps) < 3:
            self.reader.unsupported(self.e, "colored molecular area")
        self.color = self.reader.colors[int(self.e.get("bgcolor", "2"))]
        self.paths.append((ps, True, self.color))

    def graphic(self) -> None:
        ps = self.points(self.e.get("BoundingBox", ""))
        if len(ps) != 2:
            self.reader.unsupported(self.e, "graphic bounds")
        a, b = ps
        if self.kind == "Line":
            self.paths.append(([a, b], False, None))
            arrow = self.e.get("ArrowType", "NoHead")
            if arrow == "FullHead":
                self.head(a, b)
            elif arrow != "NoHead":
                self.reader.unsupported(self.e, "legacy arrow style")
        elif self.kind == "Rectangle":
            rectangle = [a, (a[0], b[1]), b, (b[0], a[1])]
            if "RoundEdge" in self.e.get("RectangleType", ""):
                left, right = sorted((a[0], b[0]))
                top, bottom = sorted((a[1], b[1]))
                radius = min(
                    (right - left) / 2,
                    (bottom - top) / 2,
                    self.reader.number(self.e.get("CornerRadius", "600"), self.e)
                    * self.width
                    / 100,
                )
                rectangle = []
                for cx, cy, start in (
                    (right - radius, top + radius, -90),
                    (right - radius, bottom - radius, 0),
                    (left + radius, bottom - radius, 90),
                    (left + radius, top + radius, 180),
                ):
                    rectangle.extend(
                        (
                            cx + radius * math.cos(math.radians(start + i * 90 / 16)),
                            cy + radius * math.sin(math.radians(start + i * 90 / 16)),
                        )
                        for i in range(17)
                    )
            self.paths.append(
                (
                    rectangle,
                    True,
                    self.color if "Filled" in self.e.get("RectangleType", "") else None,
                )
            )
        elif self.kind in {"Oval", "Orbital"}:
            if "Center3D" in self.e.attrib:
                center, major, minor = (
                    self.point3("Center3D"),
                    self.point3("MajorAxisEnd3D"),
                    self.point3("MinorAxisEnd3D"),
                )
            else:
                center = b
                major = a
                minor = (b[0] - (a[1] - b[1]), b[1] + a[0] - b[0])
            if self.kind == "Orbital" and self.e.get("OrbitalType") not in {
                "s",
                "sFilled",
                "sShaded",
                "oval",
            }:
                self.reader.unsupported(self.e, "orbital shape")
            self.ellipse(
                center,
                major,
                minor,
                "Filled" in self.e.get("OvalType", "")
                or "Filled" in self.e.get("OrbitalType", ""),
            )
        elif self.kind == "Bracket":
            dx, dy = (b[0] - a[0], b[1] - a[1])
            length = math.hypot(dx, dy)
            if not length:
                self.reader.unsupported(self.e, "zero bracket")
            lip = max(3, self.width * 5)
            ux, uy = (-dy / length * lip, dx / length * lip)
            self.paths.append(
                ([(a[0] + ux, a[1] + uy), a, b, (b[0] + ux, b[1] + uy)], False, None)
            )
        elif self.kind == "Symbol":
            symbol = self.e.get("SymbolType", "")
            center = b
            radius = max(math.dist(a, b) * 0.4, 1.5)
            if symbol in {"Plus", "Minus", "CirclePlus", "CircleMinus"}:
                cx, cy = center
                self.paths.append(([(cx - radius, cy), (cx + radius, cy)], False, None))
                if "Plus" in symbol:
                    self.paths.append(
                        ([(cx, cy - radius), (cx, cy + radius)], False, None)
                    )
                if symbol.startswith("Circle"):
                    self.ellipse(
                        center,
                        (center[0] + radius * 1.5, center[1]),
                        (center[0], center[1] + radius * 1.5),
                    )
            elif symbol in {"Electron", "LonePair", "Radical"}:
                offsets = [-radius / 2, radius / 2] if symbol == "LonePair" else [0]
                for dx in offsets:
                    self.ellipse(
                        (center[0] + dx, center[1]),
                        (center[0] + dx + 0.7, center[1]),
                        (center[0] + dx, center[1] + 0.7),
                        True,
                    )
            else:
                self.reader.unsupported(self.e, "symbol " + symbol)
        else:
            self.reader.unsupported(self.e, "native graphic " + self.kind)

    def render(self) -> dict[str, object]:
        if self.tag == "curve":
            self.curve()
        elif self.tag == "arrow":
            self.arrow()
        elif self.tag == "ColoredMolecularArea":
            self.area()
        elif self.tag == "graphic":
            self.graphic()
        else:
            self.reader.unsupported(self.e, "native display object")
        allpoints = [p for ps, _, _ in self.paths for p in ps]
        if not allpoints:
            self.reader.unsupported(self.e, "empty native graphic")
        padding = max(self.width, 1.5)
        left = min(p[0] for p in allpoints) - padding
        top = min(p[1] for p in allpoints) - padding
        right = max(p[0] for p in allpoints) + padding
        bottom = max(p[1] for p in allpoints) + padding
        w, h = (right - left, bottom - top)
        scale = 4
        pixels = (max(1, math.ceil(w * scale)), max(1, math.ceil(h * scale)))
        if pixels[0] * pixels[1] > 8000000:
            self.reader.unsupported(self.e, "oversized graphic")
        raster = Image.new("RGBA", pixels, (0, 0, 0, 0))
        draw = ImageDraw.Draw(raster)
        for ps, closed, fill in self.paths:
            coords = [((x - left) * scale, (y - top) * scale) for x, y in ps]
            if fill:
                draw.polygon(coords, fill=fill)
            if closed:
                coords.append(coords[0])
            if self.tag != "ColoredMolecularArea":
                dashed = "Dashed" in self.e.get(
                    "RectangleType", ""
                ) or "Dashed" in self.e.get("LineType", "")
                if dashed and not fill:
                    phase = 0.0
                    dash = max(1.0, self.width * scale * 4)
                    for p, q in pairwise(coords):
                        length = math.dist(p, q)
                        position = 0.0
                        while position < length:
                            dash_index = int((phase + 1e-9) // dash)
                            step = min(
                                length - position, (dash_index + 1) * dash - phase
                            )
                            if dash_index % 2 == 0:
                                endpoints = [
                                    (
                                        p[0] + (q[0] - p[0]) * t / length,
                                        p[1] + (q[1] - p[1]) * t / length,
                                    )
                                    for t in (position, position + step)
                                ]
                                draw.line(
                                    endpoints,
                                    fill=self.color,
                                    width=max(1, round(self.width * scale)),
                                )
                            position += step
                            phase = (phase + step) % (2 * dash)
                else:
                    draw.line(
                        coords,
                        fill=self.color,
                        width=max(1, round(self.width * scale)),
                        joint="curve",
                    )
        output = io.BytesIO()
        raster.save(output, format="PNG")
        z = native_image_z(self.reader, self.e)
        return image_state_from_bytes(
            output.getvalue(),
            x=left - self.reader.offset[0],
            y=top - self.reader.offset[1],
            width=w,
            height=h,
            z=z,
        )
