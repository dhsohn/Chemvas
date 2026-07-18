from __future__ import annotations

import math
from collections.abc import Callable

Coords3D = tuple[float, float, float]
RotatePointAroundAxis = Callable[[Coords3D, Coords3D, Coords3D, float], Coords3D]
ROTATION_DRAG_SENSITIVITY = 0.005


def normalize_3d(dx: float, dy: float, dz: float) -> Coords3D | None:
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        return None
    return dx / length, dy / length, dz / length


def center_for_coords_3d(
    atom_ids: set[int],
    coords: dict[int, Coords3D],
) -> Coords3D | None:
    if not atom_ids:
        return None
    points = [coords[atom_id] for atom_id in atom_ids if atom_id in coords]
    if not points:
        return None
    count = len(points)
    return (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
        sum(point[2] for point in points) / count,
    )


def fragment_plane_normal_for(
    atom_ids: set[int],
    coords: dict[int, Coords3D],
) -> Coords3D | None:
    points = [coords[atom_id] for atom_id in atom_ids if atom_id in coords]
    count = len(points)
    if count < 3:
        return None
    for i in range(count - 2):
        ax, ay, az = points[i]
        for j in range(i + 1, count - 1):
            bx, by, bz = points[j]
            ab = (bx - ax, by - ay, bz - az)
            for k in range(j + 1, count):
                cx, cy, cz = points[k]
                ac = (cx - ax, cy - ay, cz - az)
                normal = normalize_3d(
                    ab[1] * ac[2] - ab[2] * ac[1],
                    ab[2] * ac[0] - ab[0] * ac[2],
                    ab[0] * ac[1] - ab[1] * ac[0],
                )
                if normal is not None:
                    return normal
    return 0.0, 0.0, 1.0


def flatten_coords_to_plane(
    coords: dict[int, Coords3D],
    atom_ids: set[int],
    *,
    normal: Coords3D,
    centroid: Coords3D,
) -> dict[int, Coords3D]:
    flattened = dict(coords)
    cx, cy, cz = centroid
    nx, ny, nz = normal
    for atom_id in atom_ids:
        point = flattened.get(atom_id)
        if point is None:
            continue
        px, py, pz = point
        distance = (px - cx) * nx + (py - cy) * ny + (pz - cz) * nz
        flattened[atom_id] = (
            px - nx * distance,
            py - ny * distance,
            pz - nz * distance,
        )
    return flattened


def rotate_point_around_axis(
    point: Coords3D,
    axis_start: Coords3D,
    axis_end: Coords3D,
    angle: float,
) -> Coords3D:
    px, py, pz = point
    ax, ay, az = axis_start
    bx, by, bz = axis_end
    vx = bx - ax
    vy = by - ay
    vz = bz - az
    vlen = math.sqrt(vx * vx + vy * vy + vz * vz)
    if vlen < 1e-9:
        return point
    ux = vx / vlen
    uy = vy / vlen
    uz = vz / vlen
    x = px - ax
    y = py - ay
    z = pz - az
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dot = ux * x + uy * y + uz * z
    cross_x = uy * z - uz * y
    cross_y = uz * x - ux * z
    cross_z = ux * y - uy * x
    rx = x * cos_a + cross_x * sin_a + ux * dot * (1.0 - cos_a)
    ry = y * cos_a + cross_y * sin_a + uy * dot * (1.0 - cos_a)
    rz = z * cos_a + cross_z * sin_a + uz * dot * (1.0 - cos_a)
    return rx + ax, ry + ay, rz + az


def rigid_rotation_angles_from_drag(
    delta_x: float,
    delta_y: float,
    *,
    sensitivity: float = ROTATION_DRAG_SENSITIVITY,
) -> tuple[float, float]:
    return delta_y * sensitivity, delta_x * sensitivity


def dominant_axis_angle_from_drag(
    delta_x: float,
    delta_y: float,
    *,
    sensitivity: float = ROTATION_DRAG_SENSITIVITY,
) -> float:
    dominant_delta = delta_x if abs(delta_x) >= abs(delta_y) else delta_y
    return dominant_delta * sensitivity


def rigid_rotated_coords(
    atom_ids: set[int],
    base_coords: dict[int, Coords3D],
    center: Coords3D,
    *,
    angle_x: float,
    angle_y: float,
) -> dict[int, Coords3D]:
    cx, cy, cz = center
    cos_y = math.cos(angle_y)
    sin_y = math.sin(angle_y)
    cos_x = math.cos(angle_x)
    sin_x = math.sin(angle_x)
    rotated_coords: dict[int, Coords3D] = {}
    for atom_id in atom_ids:
        coords = base_coords.get(atom_id)
        if coords is None:
            continue
        x, y, z = coords
        x -= cx
        y -= cy
        z -= cz
        rx = x * cos_y + z * sin_y
        rz = -x * sin_y + z * cos_y
        ry = y * cos_x - rz * sin_x
        rz2 = y * sin_x + rz * cos_x
        rotated_coords[atom_id] = (rx + cx, ry + cy, rz2 + cz)
    return rotated_coords


def axis_rotated_coords(
    atom_ids: set[int],
    base_coords: dict[int, Coords3D],
    axis_start: Coords3D,
    axis_end: Coords3D,
    angle: float,
    *,
    rotate_point: RotatePointAroundAxis = rotate_point_around_axis,
) -> dict[int, Coords3D]:
    rotated_coords: dict[int, Coords3D] = {}
    for atom_id in atom_ids:
        coords = base_coords.get(atom_id)
        if coords is None:
            continue
        rotated_coords[atom_id] = rotate_point(coords, axis_start, axis_end, angle)
    return rotated_coords


__all__ = [
    "ROTATION_DRAG_SENSITIVITY",
    "Coords3D",
    "RotatePointAroundAxis",
    "axis_rotated_coords",
    "center_for_coords_3d",
    "dominant_axis_angle_from_drag",
    "flatten_coords_to_plane",
    "fragment_plane_normal_for",
    "normalize_3d",
    "rigid_rotated_coords",
    "rigid_rotation_angles_from_drag",
    "rotate_point_around_axis",
]
