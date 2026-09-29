from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

Coords3D = tuple[float, float, float]


def _perspective_scale(z: float, center_z: float, bond_length_px: float) -> float:
    focal = max(bond_length_px * 8.0, 120.0)
    dz = max(min(z - center_z, focal * 0.7), -focal * 0.8)
    denom = max(focal - dz, focal * 0.2)
    return focal / denom


def project_point_3d(
    point: Coords3D,
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
) -> tuple[float, float]:
    if center_3d is None:
        return point[0], point[1]
    cx, cy, cz = center_3d
    anchor_x, anchor_y = anchor_2d or (cx, cy)
    scale = _perspective_scale(point[2], cz, bond_length_px)
    return (
        anchor_x + (point[0] - cx) * scale,
        anchor_y + (point[1] - cy) * scale,
    )


def unproject_point_3d(
    point: tuple[float, float],
    z: float,
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
) -> Coords3D:
    if center_3d is None:
        return point[0], point[1], z
    cx, cy, cz = center_3d
    anchor_x, anchor_y = anchor_2d or (cx, cy)
    scale = _perspective_scale(z, cz, bond_length_px)
    return (
        cx + (point[0] - anchor_x) / scale,
        cy + (point[1] - anchor_y) / scale,
        z,
    )


def translate_projected_point_3d(
    point: Coords3D,
    dx: float,
    dy: float,
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
) -> Coords3D:
    """Translate the projected point, preserving its depth and projection error.

    Applying the inverse screen delta to the stored point, rather than
    unprojecting the atom's current position, keeps a stale stored point stale.
    The camera center and anchor do not move with a selected fragment.
    """
    scale = (
        _perspective_scale(point[2], center_3d[2], bond_length_px)
        if center_3d is not None
        else 1.0
    )
    return point[0] + dx / scale, point[1] + dy / scale, point[2]


def stored_coords_match_projection(
    point: Coords3D,
    atom_xy: tuple[float, float],
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
) -> bool:
    """Whether a stored 3D point still projects onto its atom.

    2D coordinates are the truth; a stored point is a depth cache that a 2D
    edit leaves stale once its projection drifts from the atom.
    """
    x, y = project_point_3d(
        point, bond_length_px=bond_length_px, center_3d=center_3d, anchor_2d=anchor_2d
    )
    return math.hypot(x - atom_xy[0], y - atom_xy[1]) <= max(1.0, bond_length_px * 0.15)


def current_atom_coords_3d(
    atom_xy: tuple[float, float],
    stored: Coords3D | None,
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
) -> Coords3D:
    """Return the stored point while it is valid, else the flat atom point."""
    if stored is not None and stored_coords_match_projection(
        stored,
        atom_xy,
        bond_length_px=bond_length_px,
        center_3d=center_3d,
        anchor_2d=anchor_2d,
    ):
        return stored
    return atom_xy[0], atom_xy[1], 0.0


def ring_center_3d(
    points: Iterable[Coords3D],
    *,
    screen_delta: tuple[float, float] = (0.0, 0.0),
    bond_length_px: float,
    center_3d: Coords3D | None,
) -> Coords3D | None:
    """Average ring vertices after translating each by the screen delta.

    Vertices are translated before averaging because depth clamping makes the
    inverse scale of an average differ from the average of inverse scales.
    """
    coords = [
        translate_projected_point_3d(
            point,
            *screen_delta,
            bond_length_px=bond_length_px,
            center_3d=center_3d,
        )
        if screen_delta != (0.0, 0.0)
        else point
        for point in points
    ]
    if len(coords) < 3:
        return None
    count = len(coords)
    return (
        sum(c[0] for c in coords) / count,
        sum(c[1] for c in coords) / count,
        sum(c[2] for c in coords) / count,
    )


def bond_offset_unit(
    atom_a: tuple[float, float],
    atom_b: tuple[float, float],
    target: Coords3D | None,
    *,
    bond_length_px: float,
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
) -> tuple[float, float] | None:
    """Unit normal of a bond, turned toward a projected 3D target if given."""
    dx, dy = atom_b[0] - atom_a[0], atom_b[1] - atom_a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    nx, ny = -dy / length, dx / length
    if target is not None:
        tx, ty = project_point_3d(
            target,
            bond_length_px=bond_length_px,
            center_3d=center_3d,
            anchor_2d=anchor_2d,
        )
        if (
            nx * (tx - (atom_a[0] + atom_b[0]) * 0.5)
            + ny * (ty - (atom_a[1] + atom_b[1]) * 0.5)
            < 0
        ):
            nx, ny = -nx, -ny
    return nx, ny


def rescaled_perspective(
    coords: Mapping[int, Coords3D],
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
    *,
    scale: float,
    origin: tuple[float, float],
) -> tuple[dict[int, Coords3D], Coords3D | None, tuple[float, float] | None]:
    """Scale stored points with a bond length change about a 2D origin.

    Depth scales about the camera depth, so projected shapes keep their
    proportions; the camera and anchor move with the drawing in 2D only.
    """
    ox, oy = origin

    def scaled(x: float, y: float) -> tuple[float, float]:
        return ox + (x - ox) * scale, oy + (y - oy) * scale

    z_center = center_3d[2] if center_3d is not None else 0.0
    rescaled = {
        atom_id: (*scaled(x, y), z_center + (z - z_center) * scale)
        for atom_id, (x, y, z) in coords.items()
    }
    center = (*scaled(center_3d[0], center_3d[1]), center_3d[2]) if center_3d else None
    anchor = scaled(*anchor_2d) if anchor_2d is not None else None
    return rescaled, center, anchor


def _finite_point_or_none(point: tuple[float, ...] | None) -> tuple[float, ...] | None:
    if point is None:
        return None
    if all(isinstance(value, (int, float)) and math.isfinite(value) for value in point):
        return point
    return None


def saved_perspective(
    coords: Mapping[int, Coords3D],
    atoms_xy: Mapping[int, tuple[float, float]],
    center_3d: Coords3D | None,
    anchor_2d: tuple[float, float] | None,
    *,
    bond_length_px: float,
) -> dict[str, object] | None:
    """Return the document perspective record, or None when nothing is valid.

    Only points that still project onto a live atom are saved.
    """
    valid = {
        atom_id: point
        for atom_id, point in coords.items()
        if atom_id in atoms_xy
        and stored_coords_match_projection(
            point,
            atoms_xy[atom_id],
            bond_length_px=bond_length_px,
            center_3d=center_3d,
            anchor_2d=anchor_2d,
        )
    }
    if not valid:
        return None
    return {
        "atom_coords_3d": valid,
        "projection_center_3d": _finite_point_or_none(center_3d),
        "projection_anchor_2d": _finite_point_or_none(anchor_2d),
    }
