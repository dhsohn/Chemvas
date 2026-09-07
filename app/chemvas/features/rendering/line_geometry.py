"""Qt-free geometry for the free line tool: angle lock and wavy strokes."""

from __future__ import annotations

import math

Point2D = tuple[float, float]

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
    for direction in (1.0, -1.0):
        half = start_angle + direction * sweep * 0.5
        probe = (
            center[0] + radius * math.cos(half),
            center[1] + radius * math.sin(half),
        )
        if (probe[0] - mid[0]) * nx + (probe[1] - mid[1]) * ny > 0.0:
            return center, radius, start_angle, direction * sweep
    return center, radius, start_angle, sweep


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
    "nearest_endpoint",
    "snapped_endpoint",
    "snapped_line_end",
    "snapped_to_grid",
    "wavy_line_points",
]
