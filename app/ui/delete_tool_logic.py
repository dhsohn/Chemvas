from __future__ import annotations

from collections.abc import Sequence

from core.history import CompositeCommand, HistoryCommand, SetSmilesInputCommand

from ui.history_commands import DeleteSceneItemsCommand
from ui.scene_item_access import remove_scene_item
from ui.scene_item_state import scene_item_state_for

DELETE_SCENE_ITEM_KINDS = frozenset(
    {
        "arrow",
        "equilibrium",
        "resonance",
        "curved_single",
        "curved_double",
        "inhibit",
        "dotted",
        "orbital",
        "ts_bracket",
        "note",
    }
)


def erase_delete_tool_item(canvas, item, *, scene_ops=None):
    kind = item.data(0)
    scene_ops = scene_ops or canvas
    if kind == "atom":
        atom_id = item.data(1)
        if not isinstance(atom_id, int):
            return False, None
        return True, scene_ops.delete_atom(atom_id, record=False)

    if kind == "bond":
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return False, None
        return True, scene_ops.delete_bond(bond_id, record=False)

    if kind == "ring":
        return True, scene_ops.delete_ring(item, record=False)

    state = scene_item_state_for(canvas, item)
    remove_scene_item(canvas, item)
    return True, DeleteSceneItemsCommand(item_states=[state], items=[item])


def build_delete_tool_history_command(
    commands: Sequence[HistoryCommand],
    *,
    before_smiles_input: str | None,
    after_smiles_input: str | None,
) -> HistoryCommand | None:
    if not commands:
        return None
    return CompositeCommand(
        [
            SetSmilesInputCommand(
                before_value=before_smiles_input,
                after_value=after_smiles_input,
            ),
            *commands,
        ]
    )


__all__ = [
    "DELETE_SCENE_ITEM_KINDS",
    "build_delete_tool_history_command",
    "erase_delete_tool_item",
]
