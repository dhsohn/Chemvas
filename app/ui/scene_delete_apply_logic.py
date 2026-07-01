from __future__ import annotations

from collections.abc import Callable, Sequence

from core.history import DeleteAtomsCommand, DeleteBondCommand, HistoryCommand
from core.model import Bond

from ui.history_commands import DeleteSceneItemsCommand
from ui.scene_delete_logic import DeleteSelectionPlan


def apply_delete_selection_plan(
    plan: DeleteSelectionPlan,
    *,
    bonds: Sequence[Bond | None],
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    bond_state_getter: Callable[[object], dict],
    remove_bond_by_id: Callable[[int], None],
    redraw_connected_bonds: Callable[[int], None],
    atom_state_getter: Callable[[int], dict],
    next_atom_id_getter: Callable[[], int],
    remove_atom_only: Callable[[int], None],
    scene_item_state_getter: Callable[[object], dict],
    remove_scene_item: Callable[[object], None],
    clear_handles: Callable[[], None],
) -> list[HistoryCommand]:
    commands: list[HistoryCommand] = []

    for bond_id in plan.bond_ids_to_remove:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        bond_state = bond_state_getter(bond)
        remove_bond_by_id(bond_id)
        redraw_connected_bonds(bond.a)
        redraw_connected_bonds(bond.b)
        commands.append(
            DeleteBondCommand(
                bond_id=bond_id,
                bond_state=bond_state,
                before_smiles_input=before_smiles_input,
                after_smiles_input=current_smiles_input_getter(),
            )
        )

    if plan.atom_ids:
        atom_states = {atom_id: atom_state_getter(atom_id) for atom_id in plan.atom_ids}
        before_next_atom_id = next_atom_id_getter()
        for atom_id in plan.atom_ids:
            remove_atom_only(atom_id)
        commands.append(
            DeleteAtomsCommand(
                atom_states=atom_states,
                mark_states=plan.mark_states_for_atoms,
                before_next_atom_id=before_next_atom_id,
                after_next_atom_id=next_atom_id_getter(),
                before_smiles_input=before_smiles_input,
                after_smiles_input=current_smiles_input_getter(),
            )
        )

    if plan.scene_items:
        if plan.clear_handles:
            clear_handles()
        scene_states = [scene_item_state_getter(item) for item in plan.scene_items]
        for item in plan.scene_items:
            remove_scene_item(item)
        commands.append(DeleteSceneItemsCommand(item_states=scene_states, items=plan.scene_items))

    return commands


__all__ = ["apply_delete_selection_plan"]
