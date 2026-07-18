from __future__ import annotations

from chemvas.core.history import SetAtomPositionsCommand

Coords2D = tuple[float, float]
Coords3D = tuple[float, float, float]


def build_selection_rotation_command(
    *,
    before_positions: dict[int, Coords2D],
    after_positions: dict[int, Coords2D],
    before_coords_3d: dict[int, Coords3D],
    after_coords_3d: dict[int, Coords3D],
    before_projection_center_3d: Coords3D | None,
    after_projection_center_3d: Coords3D | None,
    before_projection_anchor_2d: Coords2D | None,
    after_projection_anchor_2d: Coords2D | None,
) -> SetAtomPositionsCommand | None:
    positions_changed = bool(
        before_positions and after_positions and before_positions != after_positions
    )
    coords_changed = bool(
        before_coords_3d and after_coords_3d and before_coords_3d != after_coords_3d
    )
    if not positions_changed and not coords_changed:
        return None
    return SetAtomPositionsCommand(
        before_positions=before_positions,
        after_positions=after_positions,
        before_coords_3d=before_coords_3d or None,
        after_coords_3d=after_coords_3d or None,
        restore_projection_state=True,
        before_projection_center_3d=before_projection_center_3d,
        after_projection_center_3d=after_projection_center_3d,
        before_projection_anchor_2d=before_projection_anchor_2d,
        after_projection_anchor_2d=after_projection_anchor_2d,
    )


__all__ = ["Coords2D", "Coords3D", "build_selection_rotation_command"]
