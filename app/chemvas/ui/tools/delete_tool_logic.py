from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.ui.annotations.state import scene_item_state_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chemvas.ui.scene.scene_delete_session import SceneDeleteTransactionSession

# Every arrow kind the document schema knows, plus the standalone annotation
# items the delete tool erases the same way.
DELETE_SCENE_ITEM_KINDS = VALID_ARROW_KINDS | frozenset(
    {
        "orbital",
        "ts_bracket",
        "shape",
        "note",
        "image",
        "mark",
    }
)


def erase_delete_tool_item(
    canvas, item, *, delete_session: SceneDeleteTransactionSession
) -> tuple[bool, HistoryCommand | None]:
    kind = item.data(0)
    if kind == "atom":
        atom_id = item.data(1)
        if not isinstance(atom_id, int):
            return False, None
        command = delete_session.delete_atom(atom_id)
        return command is not None, command

    if kind == "bond":
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return False, None
        command = delete_session.delete_bond(bond_id)
        return command is not None, command

    if kind == "ring":
        command = delete_session.delete_ring(item)
        return command is not None, command

    if kind not in DELETE_SCENE_ITEM_KINDS:
        return False, None

    command = delete_session.delete_scene_item(item, scene_item_state_for(canvas, item))
    return True, command


def build_delete_tool_history_command(
    commands: Sequence[HistoryCommand],
) -> HistoryCommand | None:
    if not commands:
        return None
    return commands[0] if len(commands) == 1 else CompositeCommand(list(commands))


__all__ = [
    "DELETE_SCENE_ITEM_KINDS",
    "build_delete_tool_history_command",
    "erase_delete_tool_item",
]
