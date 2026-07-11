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
    atom_coords_3d_getter: Callable[[int], tuple[float, float, float] | None] | None = None,
) -> list[HistoryCommand]:
    bond_snapshots: list[tuple[int, int, int, dict]] = []
    for bond_id in plan.bond_ids_to_remove:
        if not (0 <= bond_id < len(bonds)):
            continue
        bond = bonds[bond_id]
        if bond is None:
            continue
        bond_snapshots.append(
            (bond_id, bond.a, bond.b, bond_state_getter(bond))
        )

    atom_states: dict[int, dict] = {}
    atom_coords_3d: dict[int, tuple[float, float, float]] = {}
    before_next_atom_id = 0
    if plan.atom_ids:
        before_next_atom_id = next_atom_id_getter()
        atom_states = {atom_id: atom_state_getter(atom_id) for atom_id in plan.atom_ids}
        if atom_coords_3d_getter is not None:
            for atom_id in plan.atom_ids:
                coords = atom_coords_3d_getter(atom_id)
                if coords is not None:
                    atom_coords_3d[atom_id] = coords

    scene_states = [scene_item_state_getter(item) for item in plan.scene_items]
    after_smiles_input = current_smiles_input_getter()
    commands: list[HistoryCommand] = []
    for bond_id, atom_a, atom_b, bond_state in bond_snapshots:
        bond_command = DeleteBondCommand(
            bond_id=bond_id,
            bond_state=bond_state,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )
        remove_bond_by_id(bond_id)
        redraw_connected_bonds(atom_a)
        redraw_connected_bonds(atom_b)
        bond_command.after_smiles_input = current_smiles_input_getter()
        commands.append(bond_command)

    if plan.atom_ids:
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
                atom_coords_3d=atom_coords_3d or None,
            )
        )

    if plan.scene_items:
        for item in plan.scene_items:
            remove_scene_item(item)
        commands.append(
            DeleteSceneItemsCommand(
                item_states=scene_states,
                items=plan.scene_items,
            )
        )

        if plan.clear_handles:
            clear_handles()

    return commands


__all__ = ["apply_delete_selection_plan"]
