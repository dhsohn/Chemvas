from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, cast

Point2D = tuple[float, float]
TemplateRingStyle = Literal["regular", "benzene", "chair", "chair_flip", "boat"]
TemplateGenerator = Literal[
    "benzene",
    "free_regular_ring",
    "free_template_shape",
    "atom_regular_ring",
    "bond_regular_ring",
    "bond_template_shape",
]
TemplateRadiusMode = Literal["regular_polygon", "bond_length"]
TemplateShape = Literal["chair", "chair_flip", "boat"]


@dataclass(frozen=True)
class TemplateInsertRequest:
    ring_size: int
    cursor_pos: Point2D
    bond_id: int | None = None
    ring_style: str | None = None
    atom_id: int | None = None


@dataclass(frozen=True)
class TemplateInsertPlan:
    generator: TemplateGenerator
    ring_size: int
    ring_style: TemplateRingStyle
    bond_id: int | None
    atom_id: int | None = None
    radius_mode: TemplateRadiusMode | None = None
    template_shape: TemplateShape | None = None


@dataclass(frozen=True)
class TemplateInsertResolution:
    plan: TemplateInsertPlan
    points: list[Point2D] | None


@dataclass(frozen=True)
class TemplatePointResolvers:
    regular_ring_radius: Callable[[int], float]
    ring_points: Callable[[Point2D, int, float | None], Sequence[Point2D]]
    regular_ring_points_for_atom: Callable[[int, int], Sequence[Point2D] | None]
    regular_ring_points_for_bond: Callable[[int, int, Point2D], Sequence[Point2D] | None]
    chair_points: Callable[[Point2D], Sequence[Point2D]]
    chair_flipped_points: Callable[[Point2D], Sequence[Point2D]]
    boat_points: Callable[[Point2D], Sequence[Point2D]]
    template_points_for_bond: Callable[[Sequence[Point2D], int, Point2D], Sequence[Point2D] | None]


def plan_template_commit(request: TemplateInsertRequest) -> TemplateInsertPlan | None:
    return _plan_template_insert(request, benzene_special_case=True)


def plan_template_preview(request: TemplateInsertRequest) -> TemplateInsertPlan | None:
    # Preview keeps benzene on the generic point-resolution path so fused/free
    # placement can be resolved before aromatic preview segments are added.
    return _plan_template_insert(request, benzene_special_case=False)


def resolve_template_insert(
    request: TemplateInsertRequest,
    plan: TemplateInsertPlan,
    resolvers: TemplatePointResolvers,
) -> TemplateInsertResolution | None:
    if plan.generator == "benzene":
        return TemplateInsertResolution(plan=plan, points=None)

    cursor_pos = request.cursor_pos
    points: Sequence[Point2D] | None

    if plan.generator == "free_regular_ring":
        radius = None
        if plan.radius_mode == "regular_polygon":
            radius = resolvers.regular_ring_radius(plan.ring_size)
        points = resolvers.ring_points(cursor_pos, plan.ring_size, radius)
    elif plan.generator == "atom_regular_ring":
        if plan.atom_id is None:
            return None
        points = resolvers.regular_ring_points_for_atom(plan.ring_size, plan.atom_id)
    elif plan.generator == "free_template_shape":
        points = _template_shape_points(plan, cursor_pos, resolvers)
    elif plan.generator == "bond_regular_ring":
        if plan.bond_id is None:
            return None
        points = resolvers.regular_ring_points_for_bond(plan.ring_size, plan.bond_id, cursor_pos)
    elif plan.generator == "bond_template_shape":
        if plan.bond_id is None:
            return None
        local_points = _template_shape_points(plan, (0.0, 0.0), resolvers)
        points = resolvers.template_points_for_bond(local_points, plan.bond_id, cursor_pos)
    else:
        return None

    if points is None:
        return None
    return TemplateInsertResolution(plan=plan, points=[(x, y) for x, y in points])


def _plan_template_insert(
    request: TemplateInsertRequest,
    benzene_special_case: bool,
) -> TemplateInsertPlan | None:
    ring_style = normalize_template_ring_style(request.ring_style)
    if request.ring_size < 3 or ring_style is None:
        return None

    if benzene_special_case and ring_style == "benzene" and request.ring_size == 6:
        return TemplateInsertPlan(
            generator="benzene",
            ring_size=request.ring_size,
            ring_style=ring_style,
            bond_id=request.bond_id,
            atom_id=request.atom_id,
        )

    if ring_style == "chair" or ring_style == "chair_flip" or ring_style == "boat":
        return TemplateInsertPlan(
            generator="bond_template_shape" if request.bond_id is not None else "free_template_shape",
            ring_size=request.ring_size,
            ring_style=ring_style,
            bond_id=request.bond_id,
            template_shape=ring_style,
        )

    if request.bond_id is not None:
        return TemplateInsertPlan(
            generator="bond_regular_ring",
            ring_size=request.ring_size,
            ring_style=ring_style,
            bond_id=request.bond_id,
        )

    if request.atom_id is not None:
        return TemplateInsertPlan(
            generator="atom_regular_ring",
            ring_size=request.ring_size,
            ring_style=ring_style,
            bond_id=None,
            atom_id=request.atom_id,
        )

    return TemplateInsertPlan(
        generator="free_regular_ring",
        ring_size=request.ring_size,
        ring_style=ring_style,
        bond_id=None,
        radius_mode="regular_polygon" if ring_style == "regular" else "bond_length",
    )


def normalize_template_ring_style(ring_style: str | None) -> TemplateRingStyle | None:
    normalized = (ring_style or "regular").strip().lower()
    if normalized in {"regular", "benzene", "chair", "chair_flip", "boat"}:
        return cast(TemplateRingStyle, normalized)
    return None


def _template_shape_points(
    plan: TemplateInsertPlan,
    center: Point2D,
    resolvers: TemplatePointResolvers,
) -> Sequence[Point2D]:
    if plan.template_shape == "chair":
        return resolvers.chair_points(center)
    if plan.template_shape == "chair_flip":
        return resolvers.chair_flipped_points(center)
    if plan.template_shape == "boat":
        return resolvers.boat_points(center)
    raise ValueError(f"template_shape is required for {plan.generator}")


__all__ = [
    "Point2D",
    "TemplateInsertPlan",
    "TemplateInsertRequest",
    "TemplateInsertResolution",
    "TemplatePointResolvers",
    "normalize_template_ring_style",
    "plan_template_commit",
    "plan_template_preview",
    "resolve_template_insert",
]
