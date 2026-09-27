from __future__ import annotations

from chemvas.core.model_commands import SetAtomPositionsCommand
from chemvas.ui.selection.selection_rotation_history import (
    build_selection_rotation_command,
)


def test_build_selection_rotation_command_returns_none_without_position_or_coord_changes() -> (
    None
):
    assert (
        build_selection_rotation_command(
            before_positions={1: (0.0, 0.0)},
            after_positions={1: (0.0, 0.0)},
            before_coords_3d={1: (0.0, 0.0, 0.0)},
            after_coords_3d={1: (0.0, 0.0, 0.0)},
            before_projection_center_3d=(1.0, 2.0, 3.0),
            after_projection_center_3d=(1.0, 2.0, 3.0),
            before_projection_anchor_2d=(4.0, 5.0),
            after_projection_anchor_2d=(4.0, 5.0),
        )
        is None
    )


def test_build_selection_rotation_command_can_capture_coord_only_changes() -> None:
    command = build_selection_rotation_command(
        before_positions={1: (0.0, 0.0)},
        after_positions={1: (0.0, 0.0)},
        before_coords_3d={1: (0.0, 0.0, 0.0)},
        after_coords_3d={1: (0.0, 0.0, 1.0)},
        before_projection_center_3d=None,
        after_projection_center_3d=None,
        before_projection_anchor_2d=None,
        after_projection_anchor_2d=None,
    )

    assert isinstance(command, SetAtomPositionsCommand)
    assert command.before_coords_3d == {1: (0.0, 0.0, 0.0)}
    assert command.after_coords_3d == {1: (0.0, 0.0, 1.0)}
