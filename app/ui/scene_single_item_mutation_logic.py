from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence

from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
)
from core.model import Bond

from ui.bond_style_logic import cycle_plain_bond_style
from ui.history_commands import DeleteSceneItemsCommand


def delete_atom_with_history(
    atom_id: int,
    *,
    bonds: Sequence[Bond | None],
    marks_by_atom: Mapping[int, Sequence[object]],
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    clear_smiles_input: Callable[[], None],
    mark_state_getter: Callable[[object], dict],
    bond_state_getter: Callable[[object], dict],
    remove_bond_by_id: Callable[[int], None],
    redraw_connected_bonds: Callable[[int], None],
    atom_state_getter: Callable[[int], dict],
    next_atom_id_getter: Callable[[], int],
    remove_atom_only: Callable[[int], None],
    atom_coords_3d_getter: Callable[[int], tuple[float, float, float] | None] | None = None,
    bond_ids: Iterable[int] | None = None,
) -> HistoryCommand:
    candidate_bond_ids = range(len(bonds)) if bond_ids is None else sorted(set(bond_ids))
    bond_snapshots = [
        (bond_id, bond.a, bond.b, bond_state_getter(bond))
        for bond_id in candidate_bond_ids
        if 0 <= bond_id < len(bonds)
        for bond in (bonds[bond_id],)
        if bond is not None and (bond.a == atom_id or bond.b == atom_id)
    ]
    mark_states = [mark_state_getter(mark) for mark in marks_by_atom.get(atom_id, [])]
    atom_state = atom_state_getter(atom_id)
    coords_3d = atom_coords_3d_getter(atom_id) if atom_coords_3d_getter is not None else None
    before_next_atom_id = next_atom_id_getter()

    clear_smiles_input()
    after_smiles_input = current_smiles_input_getter()
    commands: list[HistoryCommand] = []
    for bond_id, atom_a, atom_b, bond_state in sorted(
        bond_snapshots,
        key=lambda snapshot: snapshot[0],
        reverse=True,
    ):
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

    atom_command = DeleteAtomsCommand(
        atom_states={atom_id: atom_state},
        mark_states=mark_states,
        before_next_atom_id=before_next_atom_id,
        after_next_atom_id=before_next_atom_id,
        before_smiles_input=before_smiles_input,
        after_smiles_input=after_smiles_input,
        atom_coords_3d={atom_id: coords_3d} if coords_3d is not None else None,
    )
    remove_atom_only(atom_id)
    atom_command.after_next_atom_id = next_atom_id_getter()
    atom_command.after_smiles_input = current_smiles_input_getter()
    commands.append(atom_command)
    return commands[0] if len(commands) == 1 else CompositeCommand(commands)


def delete_bond_with_history(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    clear_smiles_input: Callable[[], None],
    bond_state_getter: Callable[[object], dict],
    remove_bond_by_id: Callable[[int], None],
    redraw_connected_bonds: Callable[[int], None],
) -> DeleteBondCommand | None:
    if not isinstance(bond_id, int) or not (0 <= bond_id < len(bonds)):
        return None
    bond = bonds[bond_id]
    if bond is None:
        return None
    bond_state = bond_state_getter(bond)
    atom_a = bond.a
    atom_b = bond.b
    clear_smiles_input()
    command = DeleteBondCommand(
        bond_id=bond_id,
        bond_state=bond_state,
        before_smiles_input=before_smiles_input,
        after_smiles_input=current_smiles_input_getter(),
    )
    remove_bond_by_id(bond_id)
    redraw_connected_bonds(atom_a)
    redraw_connected_bonds(atom_b)
    command.after_smiles_input = current_smiles_input_getter()
    return command


def delete_ring_with_history(
    item,
    *,
    ring_state_getter: Callable[[object], dict],
    remove_scene_item: Callable[[object], None],
) -> DeleteSceneItemsCommand:
    state = ring_state_getter(item)
    command = DeleteSceneItemsCommand(item_states=[state], items=[item])
    remove_scene_item(item)
    return command


def flip_bond_direction_with_history(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    bond_state_getter: Callable[[object], dict],
    rebuild_bond_graphics: Callable[..., None],
    record_bond_update: Callable[[int, dict, dict, object, object], None],
) -> bool:
    bond = _valid_bond(bond_id, bonds)
    if bond is None or bond.style not in {"wedge", "hash"}:
        return False

    def mutate(target) -> None:
        target.a, target.b = target.b, target.a

    return _mutate_bond_and_record(
        bond_id,
        bond=bond,
        before_smiles_input=before_smiles_input,
        current_smiles_input_getter=current_smiles_input_getter,
        bond_state_getter=bond_state_getter,
        rebuild_bond_graphics=rebuild_bond_graphics,
        record_bond_update=record_bond_update,
        redraw_connected=True,
        mutate=mutate,
    )


def apply_bond_style_with_history(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    style: str,
    order: int,
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    bond_state_getter: Callable[[object], dict],
    rebuild_bond_graphics: Callable[..., None],
    record_bond_update: Callable[[int, dict, dict, object, object], None],
) -> bool:
    bond = _valid_bond(bond_id, bonds)
    if bond is None:
        return False

    def mutate(target) -> None:
        target.style = style
        target.order = order

    return _mutate_bond_and_record(
        bond_id,
        bond=bond,
        before_smiles_input=before_smiles_input,
        current_smiles_input_getter=current_smiles_input_getter,
        bond_state_getter=bond_state_getter,
        rebuild_bond_graphics=rebuild_bond_graphics,
        record_bond_update=record_bond_update,
        redraw_connected=True,
        mutate=mutate,
    )


def cycle_bond_style_with_history(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    bond_state_getter: Callable[[object], dict],
    rebuild_bond_graphics: Callable[..., None],
    record_bond_update: Callable[[int, dict, dict, object, object], None],
) -> bool:
    bond = _valid_bond(bond_id, bonds)
    if bond is None:
        return False

    def mutate(target) -> None:
        next_style, next_order = cycle_plain_bond_style(
            target.style,
            target.order,
            allow_double_variants=False,
        )
        target.style = next_style
        target.order = next_order

    return _mutate_bond_and_record(
        bond_id,
        bond=bond,
        before_smiles_input=before_smiles_input,
        current_smiles_input_getter=current_smiles_input_getter,
        bond_state_getter=bond_state_getter,
        rebuild_bond_graphics=rebuild_bond_graphics,
        record_bond_update=record_bond_update,
        redraw_connected=False,
        mutate=mutate,
    )


def _valid_bond(bond_id: int, bonds: Sequence[Bond | None]):
    if not (0 <= bond_id < len(bonds)):
        return None
    return bonds[bond_id]


def _mutate_bond_and_record(
    bond_id: int,
    *,
    bond,
    before_smiles_input,
    current_smiles_input_getter: Callable[[], str | None],
    bond_state_getter: Callable[[object], dict],
    rebuild_bond_graphics: Callable[..., None],
    record_bond_update: Callable[[int, dict, dict, object, object], None],
    redraw_connected: bool,
    mutate: Callable[[object], None],
) -> bool:
    before_state = bond_state_getter(bond)
    mutate(bond)
    rebuild_bond_graphics(bond_id, redraw_connected=redraw_connected)
    after_state = bond_state_getter(bond)
    record_bond_update(
        bond_id,
        before_state,
        after_state,
        before_smiles_input,
        current_smiles_input_getter(),
    )
    return True


__all__ = [
    "apply_bond_style_with_history",
    "cycle_bond_style_with_history",
    "delete_atom_with_history",
    "delete_bond_with_history",
    "delete_ring_with_history",
    "flip_bond_direction_with_history",
]
