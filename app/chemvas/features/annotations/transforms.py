"""Geometry edits on document annotation records, independent of Qt items."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import overload

from chemvas.domain.document import (
    VALID_ARC_KINDS,
    VALID_EQUILIBRIUM_KINDS,
    Arrow,
    Shape,
    TSBracket,
    mirrored_arc_kind,
)

from .arrow_label import arrow_label_normal


@overload
def rotate_annotation(
    record: Shape, *, center: tuple[float, float], angle_degrees: float
) -> Shape: ...


@overload
def rotate_annotation(
    record: TSBracket, *, center: tuple[float, float], angle_degrees: float
) -> TSBracket: ...


@overload
def rotate_annotation(
    record: Arrow, *, center: tuple[float, float], angle_degrees: float
) -> Arrow: ...


def rotate_annotation(
    record: Shape | TSBracket | Arrow,
    *,
    center: tuple[float, float],
    angle_degrees: float,
) -> Shape | TSBracket | Arrow:
    angle = math.radians(angle_degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    def rotate(point: tuple[float, float]) -> tuple[float, float]:
        dx, dy = point[0] - center[0], point[1] - center[1]
        return center[0] + dx * cos_a - dy * sin_a, center[1] + dx * sin_a + dy * cos_a

    if isinstance(record, Arrow):
        return replace(
            record,
            start=rotate(record.start),
            end=rotate(record.end),
            control=None if record.control is None else rotate(record.control),
        )
    # Shapes and brackets stay axis-aligned; their centers orbit the pivot.
    width, height = record.right - record.left, record.bottom - record.top
    x, y = rotate((record.left + width * 0.5, record.top + height * 0.5))
    left, top = x - width * 0.5, y - height * 0.5
    return replace(record, left=left, top=top, right=left + width, bottom=top + height)


@overload
def flip_annotation(
    record: Shape, *, center: tuple[float, float], horizontal: bool
) -> Shape: ...


@overload
def flip_annotation(
    record: TSBracket, *, center: tuple[float, float], horizontal: bool
) -> TSBracket: ...


@overload
def flip_annotation(
    record: Arrow, *, center: tuple[float, float], horizontal: bool
) -> Arrow: ...


def flip_annotation(
    record: Shape | TSBracket | Arrow, *, center: tuple[float, float], horizontal: bool
) -> Shape | TSBracket | Arrow:
    def flip(point: tuple[float, float]) -> tuple[float, float]:
        return (
            (2 * center[0] - point[0], point[1])
            if horizontal
            else (point[0], 2 * center[1] - point[1])
        )

    if not isinstance(record, Arrow):
        first = flip((record.left, record.top))
        second = flip((record.right, record.bottom))
        return replace(
            record,
            left=min(first[0], second[0]),
            top=min(first[1], second[1]),
            right=max(first[0], second[0]),
            bottom=max(first[1], second[1]),
        )
    start, end = flip(record.start), flip(record.end)
    labels = record.labels
    equilibrium = record.kind in VALID_EQUILIBRIUM_KINDS
    if equilibrium:
        nx, ny = arrow_label_normal(
            record.end[0] - record.start[0], record.end[1] - record.start[1]
        )
        mirrored_normal = (-nx, ny) if horizontal else (nx, -ny)
        ax, ay = arrow_label_normal(end[0] - start[0], end[1] - start[1])
        if mirrored_normal[0] * ax + mirrored_normal[1] * ay < 0:
            labels = tuple(
                ("below" if side == "above" else "above", text) for side, text in labels
            )
    return replace(
        record,
        kind=mirrored_arc_kind(record.kind)
        if record.kind in VALID_ARC_KINDS
        else record.kind,
        start=start,
        end=end,
        control=None if record.control is None else flip(record.control),
        mirrored=not record.mirrored if equilibrium else record.mirrored,
        labels=labels,
    )
