from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Point2D = tuple[float, float]
LineSegment = tuple[float, float, float, float]
Rect = tuple[float, float, float, float]
TemplatePreviewAction = Literal["clear", "rebuild", "update"]


@dataclass(frozen=True)
class TemplatePreviewGeometry:
    line_segments: list[LineSegment]
    dot_rects: list[Rect]


@dataclass(frozen=True)
class TemplatePreviewPlan:
    action: TemplatePreviewAction
    geometry: TemplatePreviewGeometry | None = None


def build_template_preview_geometry(
    points: Sequence[Point2D],
    atom_radius: float,
) -> TemplatePreviewGeometry:
    point_list = [(x, y) for x, y in points]
    line_segments = []
    dot_rects = []
    for i, (x1, y1) in enumerate(point_list):
        x2, y2 = point_list[(i + 1) % len(point_list)]
        line_segments.append((x1, y1, x2, y2))
        dot_rects.append(
            (
                x1 - atom_radius,
                y1 - atom_radius,
                atom_radius * 2.0,
                atom_radius * 2.0,
            )
        )
    return TemplatePreviewGeometry(line_segments=line_segments, dot_rects=dot_rects)


def plan_template_preview_update(
    points: Sequence[Point2D] | None,
    atom_radius: float | None,
    existing_line_count: int,
    existing_dot_count: int,
) -> TemplatePreviewPlan:
    if not points or atom_radius is None:
        return TemplatePreviewPlan(action="clear")

    geometry = build_template_preview_geometry(points, atom_radius)
    if (
        existing_line_count != len(geometry.line_segments)
        or existing_dot_count != len(geometry.dot_rects)
    ):
        return TemplatePreviewPlan(action="rebuild", geometry=geometry)
    return TemplatePreviewPlan(action="update", geometry=geometry)


__all__ = [
    "TemplatePreviewGeometry",
    "TemplatePreviewPlan",
    "build_template_preview_geometry",
    "plan_template_preview_update",
]
