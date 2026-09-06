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


__all__ = ["snapped_line_end", "wavy_line_points"]
