from __future__ import annotations

from collections.abc import Sequence

from core.history import CompositeCommand, DeleteSceneItemsCommand, HistoryCommand, SetSmilesInputCommand
from ui.scene_item_access import remove_scene_item


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
def erase_delete_tool_item(canvas, item):
    kind = item.data(0)
    if kind == "atom":
        atom_id = item.data(1)
        if not isinstance(atom_id, int):
            return False, None
        return True, canvas.delete_atom(atom_id, record=False)

    if kind == "bond":
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return False, None
        return True, canvas.delete_bond(bond_id, record=False)

    if kind == "ring":
        return True, canvas.delete_ring(item, record=False)

    state = canvas.scene_item_state(item)
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
