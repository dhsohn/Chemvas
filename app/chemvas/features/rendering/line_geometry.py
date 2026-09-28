"""Qt-free arrow paths, line strokes and endpoint/grid snapping."""

from __future__ import annotations

import math

from chemvas.domain.document import (
    ARC_KIND_SWEEPS,
    VALID_CURVED_ARROW_KINDS,
    VALID_LINE_KINDS,
)

Point2D = tuple[float, float]
PathCommand = tuple[str, tuple[float, ...]]

# Samples per half-wave of a wavy line; enough that the polyline reads as a
# smooth sine at the on-screen and exported sizes the ACS metrics produce.
_WAVE_SAMPLES_PER_HALF_WAVE = 8
# A document may legally hold a line far longer than any sheet (coordinates are
# only bounded by the JSON number range), so the point count is capped and the
# wave stretches instead of building an unbounded path on load or render.
_MAX_HALF_WAVES = 2048


def snapped_line_end(start: Point2D, end: Point2D, *, step_degrees: float) -> Point2D:
    """Rotate ``end`` about ``start`` onto the nearest multiple of ``step_degrees``.

    The drag length is kept, unlike bond snapping which also fixes the length,
    so an energy-diagram level stays as long as the user drew it.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return end
    angle = math.degrees(math.atan2(dy, dx))
    snapped = math.radians(round(angle / step_degrees) * step_degrees)
    return (
        start[0] + math.cos(snapped) * length,
        start[1] + math.sin(snapped) * length,
    )


def wavy_line_points(
    start: Point2D,
    end: Point2D,
    *,
    half_wavelength: float,
    amplitude: float,
) -> list[Point2D]:
    """Polyline tracing a sine wave along the segment from ``start`` to ``end``.

    The wave is fitted to a whole number of half-waves so both ends sit on the
    axis and the stroke meets whatever it is drawn against cleanly. A
    zero-length segment, or a half-wavelength that underflowed to zero from a
    document's tiny bond length, yields the plain two-point segment.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0.0 or half_wavelength <= 0.0:
        return [start, end]
    half_waves = min(max(1, round(length / half_wavelength)), _MAX_HALF_WAVES)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    steps = half_waves * _WAVE_SAMPLES_PER_HALF_WAVE
    points: list[Point2D] = []
    for index in range(steps):
        t = index / steps
        along = length * t
        offset = amplitude * math.sin(math.pi * half_waves * t)
        points.append(
            (start[0] + ux * along + nx * offset, start[1] + uy * along + ny * offset)
        )
    points.append(end)
    return points


def nearest_endpoint(
    point: Point2D, candidates: list[Point2D], *, radius: float
) -> Point2D | None:
    """The nearest candidate within ``radius`` of ``point``, else ``None``.

    Distinguishing "nothing in range" from "the candidate is exactly here"
    matters to callers that fall back to another snap: inferring it from
    whether the point moved would drag a cursor sitting exactly on an
    endpoint away from it.
    """
    best: Point2D | None = None
    best_distance = radius
    for candidate in candidates:
        distance = math.hypot(candidate[0] - point[0], candidate[1] - point[1])
        if distance <= best_distance:
            best = candidate
            best_distance = distance
    return best


def snapped_endpoint(
    point: Point2D, candidates: list[Point2D], *, radius: float
) -> Point2D:
    """The nearest candidate within ``radius`` of ``point``, else ``point``."""
    found = nearest_endpoint(point, candidates, radius=radius)
    return point if found is None else found


def snapped_to_grid(point: Point2D, *, step: float) -> Point2D:
    """``point`` rounded to the nearest grid intersection of size ``step``.

    A non-positive step means no grid, so the point passes through.
    """
    if step <= 0.0:
        return point
    return (round(point[0] / step) * step, round(point[1] / step) * step)


def _arc_frame(
    start: Point2D, end: Point2D, *, sweep_degrees: float, bulge_left: bool
) -> tuple[Point2D, float, float, float] | None:
    """Center, radius, start angle and signed sweep (radians) of the arc.

    The arc through ``start`` and ``end`` subtends ``sweep_degrees`` and bulges
    to the screen-left (or right) of the drag direction. ``None`` for a
    zero-length chord.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    chord = math.hypot(dx, dy)
    if chord == 0.0:
        return None
    sweep = math.radians(sweep_degrees)
    # Screen-left of the drag direction (y grows downward on screen).
    nx, ny = dy / chord, -dx / chord
    if not bulge_left:
        nx, ny = -nx, -ny
    mid = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
    radius = chord / (2.0 * math.sin(sweep * 0.5))
    # Negative for a minor arc (center opposite the bulge), positive past 180.
    center_offset = -(chord * 0.5) / math.tan(sweep * 0.5)
    center = (mid[0] + nx * center_offset, mid[1] + ny * center_offset)
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    # In screen coordinates positive sweep travels through screen-left of
    # the chord. A midpoint-side probe is ambiguous for major arcs: the wrong
    # sweep can put its midpoint on that side too, but misses the endpoint.
    return center, radius, start_angle, sweep if bulge_left else -sweep


def arc_points(
    start: Point2D, end: Point2D, *, sweep_degrees: float, bulge_left: bool
) -> list[Point2D]:
    """Polyline along the arc from ``start`` to ``end``; both ends are exact."""
    frame = _arc_frame(start, end, sweep_degrees=sweep_degrees, bulge_left=bulge_left)
    if frame is None:
        return [start, end]
    center, radius, start_angle, sweep = frame
    steps = max(8, int(abs(sweep_degrees) / 5.0))
    points: list[Point2D] = [start]
    for index in range(1, steps):
        angle = start_angle + sweep * index / steps
        points.append(
            (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
        )
    points.append(end)
    return points


def hex_grid_cells(
    bounds: tuple[float, float, float, float], *, step: float
) -> list[tuple[Point2D, ...]]:
    """Flat-top hexagons shared by painting and endpoint snapping."""
    if step <= 0:
        return []
    left, top, right, bottom = bounds
    height = math.sqrt(3) * step
    cells = []
    for column in range(
        math.floor(left / (1.5 * step)) - 1, math.ceil(right / (1.5 * step)) + 2
    ):
        cx = column * 1.5 * step
        offset = (column % 2) * height / 2
        for row in range(
            math.floor((top - offset) / height) - 1,
            math.ceil((bottom - offset) / height) + 2,
        ):
            cy = row * height + offset
            cells.append(
                tuple(
                    (
                        cx + step * math.cos(i * math.pi / 3),
                        cy + step * math.sin(i * math.pi / 3),
                    )
                    for i in range(6)
                )
            )
    return cells


def snapped_to_hex_grid(point: Point2D, *, step: float) -> Point2D:
    if step <= 0:
        return point
    x, y = point
    vertices = (
        vertex for cell in hex_grid_cells((x, y, x, y), step=step) for vertex in cell
    )
    return min(vertices, key=lambda vertex: (vertex[0] - x) ** 2 + (vertex[1] - y) ** 2)


def arc_midpoint(
    start: Point2D, end: Point2D, *, sweep_degrees: float, bulge_left: bool
) -> Point2D:
    frame = _arc_frame(start, end, sweep_degrees=sweep_degrees, bulge_left=bulge_left)
    if frame is None:
        return start
    center, radius, start_angle, sweep = frame
    angle = start_angle + sweep * 0.5
    return (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))


__all__ = [
    "arc_midpoint",
    "arc_points",
    "arrow_path_commands",
    "curved_control_point",
    "hex_grid_cells",
    "nearest_endpoint",
    "snapped_endpoint",
    "snapped_line_end",
    "snapped_to_grid",
    "snapped_to_hex_grid",
    "wavy_line_points",
]


def curved_control_point(start: Point2D, end: Point2D) -> Point2D:
    """The native curved-arrow handle's initial control point."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    return (
        start[0] + dx * 0.5 + nx * length * 0.3,
        start[1] + dy * 0.5 + ny * length * 0.3,
    )


def arrow_path_commands(
    start: Point2D,
    end: Point2D,
    kind: str,
    *,
    bond_length: float,
    bond_spacing: float,
    wave_spacing: float,
    line_width: float,
    head_scale: float,
    control: Point2D | None = None,
    double: bool = False,
    mirrored: bool = False,
) -> list[PathCommand]:
    """ArrowRenderer's path construction, shared by Qt and SVG output."""
    commands: list[PathCommand] = []

    def polyline(points: list[Point2D]) -> None:
        # QPainterPath discards zero-length lines; SVG round caps would paint dots.
        if all(point == points[0] for point in points[1:]):
            return
        commands.append(("M", points[0]))
        commands.extend(("L", point) for point in points[1:])

    def head(a: Point2D, b: Point2D, *, half: bool = False) -> None:
        for points in arrow_head_polylines(
            a,
            b,
            head_len=bond_length * head_scale,
            line_width=line_width,
            double=False,
            half=half,
            mirrored=mirrored if half else False,
        ):
            polyline(points)

    if kind in VALID_LINE_KINDS:
        polyline(
            wavy_line_points(
                start, end, half_wavelength=wave_spacing, amplitude=wave_spacing * 0.5
            )
            if kind == "line_wavy"
            else [start, end]
        )
    elif kind in ARC_KIND_SWEEPS:
        sweep_degrees, bulge_left = ARC_KIND_SWEEPS[kind]
        points = arc_points(
            start, end, sweep_degrees=sweep_degrees, bulge_left=bulge_left
        )
        polyline(points)
        head(points[-2], end)
    elif kind in VALID_CURVED_ARROW_KINDS:
        if control is None:
            control = curved_control_point(start, end)
            double = kind == "curved_double"
        if start != control or control != end:
            commands.extend([("M", start), ("Q", (*control, *end))])
        head(control, end)
        if double:
            head(control, start)
    elif kind.startswith("equilibrium"):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        offset = max(bond_spacing * 0.5, line_width)
        if mirrored:
            offset = -offset
        forward_start = (start[0] - nx * offset, start[1] - ny * offset)
        forward_end = (end[0] - nx * offset, end[1] - ny * offset)
        reverse_start = (end[0] + nx * offset, end[1] + ny * offset)
        reverse_end = (start[0] + nx * offset, start[1] + ny * offset)
        for a, b, shortened in (
            (forward_start, forward_end, kind == "equilibrium_reverse"),
            (reverse_start, reverse_end, kind == "equilibrium_forward"),
        ):
            if shortened:
                mid_x, mid_y = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
                a, b = (
                    (mid_x + (a[0] - mid_x) * 0.5, mid_y + (a[1] - mid_y) * 0.5),
                    (mid_x + (b[0] - mid_x) * 0.5, mid_y + (b[1] - mid_y) * 0.5),
                )
            polyline([a, b])
            head(a, b, half=True)
    else:
        polyline([start, end])
        if kind == "inhibit":
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            bar = bond_length * 0.2
            polyline(
                [
                    (end[0] - nx * bar, end[1] - ny * bar),
                    (end[0] + nx * bar, end[1] + ny * bar),
                ]
            )
        else:
            head(start, end)
            if kind == "resonance":
                head(end, start)
    return commands


def arrow_head_polylines(
    start: Point2D,
    end: Point2D,
    *,
    head_len: float,
    line_width: float,
    double: bool,
    half: bool = False,
    mirrored: bool = False,
) -> list[list[Point2D]]:
    """ArrowRenderer's existing head construction, with tuple drawing outputs."""
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_angle = math.radians(-25 if mirrored else 25)
    offsets = [0.0]
    if double:
        offset_mag = max(1.4, line_width * 1.2)
        offsets = [-offset_mag, offset_mag]
    polylines = []
    for offset in offsets:
        dx = math.cos(angle + math.pi / 2) * offset
        dy = math.sin(angle + math.pi / 2) * offset
        tip = (end[0] + dx, end[1] + dy) if double else end
        right = (
            tip[0] - head_len * math.cos(angle + head_angle),
            tip[1] - head_len * math.sin(angle + head_angle),
        )
        if half:
            polylines.append([right, tip])
            continue
        left = (
            tip[0] - head_len * math.cos(angle - head_angle),
            tip[1] - head_len * math.sin(angle - head_angle),
        )
        polylines.append([left, tip, right])
    return polylines
