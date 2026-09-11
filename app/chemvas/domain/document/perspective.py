from __future__ import annotations

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
