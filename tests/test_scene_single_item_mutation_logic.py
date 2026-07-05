import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.history import CompositeCommand, DeleteAtomsCommand, DeleteBondCommand
from core.model import Atom, Bond, MoleculeModel
from ui.history_commands import DeleteSceneItemsCommand
from ui.scene_single_item_mutation_logic import (
    apply_bond_style_with_history,
    cycle_bond_style_with_history,
    delete_atom_with_history,
    delete_bond_with_history,
    delete_ring_with_history,
    flip_bond_direction_with_history,
)


class SceneSingleItemMutationLogicTest(unittest.TestCase):
    def test_delete_atom_with_history_builds_composite_command_in_reverse_bond_order(self) -> None:
        model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
                3: Atom("N", -10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1), Bond(3, 1, 2), None],
            next_atom_id=7,
        )
        smiles_state = {"value": "CO"}
        marks_by_atom = {1: [{"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0}]}
        removed_bonds: list[int] = []
        redraw_calls: list[int] = []
        removed_atoms: list[tuple[int, bool]] = []

        def clear_smiles_input() -> None:
            smiles_state["value"] = None

        def remove_bond_by_id(bond_id: int) -> None:
            removed_bonds.append(bond_id)
            model.bonds[bond_id] = None

        def remove_atom_only(atom_id: int, remove_marks: bool = True) -> None:
            removed_atoms.append((atom_id, remove_marks))
            model.atoms.pop(atom_id, None)

        command = delete_atom_with_history(
            1,
            bonds=model.bonds,
            marks_by_atom=marks_by_atom,
            before_smiles_input="CO",
            current_smiles_input_getter=lambda: smiles_state["value"],
            clear_smiles_input=clear_smiles_input,
            mark_state_getter=lambda mark: dict(mark),
            bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order},
            remove_bond_by_id=remove_bond_by_id,
            redraw_connected_bonds=redraw_calls.append,
            atom_state_getter=lambda atom_id: {
                "element": model.atoms[atom_id].element,
                "x": model.atoms[atom_id].x,
                "y": model.atoms[atom_id].y,
            },
            next_atom_id_getter=lambda: model.next_atom_id,
            remove_atom_only=remove_atom_only,
            atom_coords_3d_getter=lambda atom_id: {1: (0.0, 0.0, 2.0)}.get(atom_id),
        )

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual([type(child) for child in command.commands], [DeleteBondCommand, DeleteBondCommand, DeleteAtomsCommand])
        self.assertEqual([child.bond_id for child in command.commands[:2]], [1, 0])
        self.assertEqual(removed_bonds, [1, 0])
        self.assertEqual(redraw_calls, [3, 1, 1, 2])
        self.assertEqual(removed_atoms, [(1, True)])
        atom_delete = command.commands[-1]
        assert isinstance(atom_delete, DeleteAtomsCommand)
        self.assertEqual(atom_delete.mark_states, [{"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0}])
        self.assertEqual(atom_delete.before_next_atom_id, 4)
        self.assertEqual(atom_delete.after_next_atom_id, 4)
        self.assertEqual(atom_delete.atom_coords_3d, {1: (0.0, 0.0, 2.0)})
        self.assertIsNone(atom_delete.after_smiles_input)

    def test_delete_bond_with_history_validates_and_builds_command(self) -> None:
        model = MoleculeModel(bonds=[Bond(1, 2, 2), None])
        smiles_state = {"value": "C=C"}
        removed: list[int] = []
        redraw_calls: list[int] = []

        def clear_smiles_input() -> None:
            smiles_state["value"] = None

        def remove_bond_by_id(bond_id: int) -> None:
            removed.append(bond_id)
            model.bonds[bond_id] = None

        self.assertIsNone(
            delete_bond_with_history(
                9,
                bonds=model.bonds,
                before_smiles_input="C=C",
                current_smiles_input_getter=lambda: smiles_state["value"],
                clear_smiles_input=clear_smiles_input,
                bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order},
                remove_bond_by_id=remove_bond_by_id,
                redraw_connected_bonds=redraw_calls.append,
            )
        )
        self.assertIsNone(
            delete_bond_with_history(
                1,
                bonds=model.bonds,
                before_smiles_input="C=C",
                current_smiles_input_getter=lambda: smiles_state["value"],
                clear_smiles_input=clear_smiles_input,
                bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order},
                remove_bond_by_id=remove_bond_by_id,
                redraw_connected_bonds=redraw_calls.append,
            )
        )

        command = delete_bond_with_history(
            0,
            bonds=model.bonds,
            before_smiles_input="C=C",
            current_smiles_input_getter=lambda: smiles_state["value"],
            clear_smiles_input=clear_smiles_input,
            bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "order": bond.order},
            remove_bond_by_id=remove_bond_by_id,
            redraw_connected_bonds=redraw_calls.append,
        )

        self.assertIsInstance(command, DeleteBondCommand)
        assert command is not None
        self.assertEqual(command.bond_id, 0)
        self.assertEqual(command.before_smiles_input, "C=C")
        self.assertIsNone(command.after_smiles_input)
        self.assertEqual(removed, [0])
        self.assertEqual(redraw_calls, [1, 2])

    def test_delete_ring_with_history_builds_delete_scene_items_command(self) -> None:
        ring = object()
        removed_items: list[object] = []

        command = delete_ring_with_history(
            ring,
            ring_state_getter=lambda item: {"kind": "ring", "points": [(0.0, 0.0)]},
            remove_scene_item=removed_items.append,
        )

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(command.item_states, [{"kind": "ring", "points": [(0.0, 0.0)]}])
        self.assertEqual(command.items, [ring])
        self.assertEqual(removed_items, [ring])

    def test_flip_bond_direction_with_history_swaps_atoms_and_records_update(self) -> None:
        bonds = [Bond(1, 2, 1, style="wedge"), Bond(3, 4, 1, style="single"), None]
        rebuild_calls: list[tuple[int, bool]] = []
        record_calls: list[tuple[int, dict, dict, object, object]] = []

        self.assertFalse(
            flip_bond_direction_with_history(
                9,
                bonds=bonds,
                before_smiles_input="C=C",
                current_smiles_input_getter=lambda: "C=C",
                bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style},
                rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                record_bond_update=lambda *args: record_calls.append(args),
            )
        )
        self.assertFalse(
            flip_bond_direction_with_history(
                1,
                bonds=bonds,
                before_smiles_input="C=C",
                current_smiles_input_getter=lambda: "C=C",
                bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style},
                rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                record_bond_update=lambda *args: record_calls.append(args),
            )
        )

        self.assertTrue(
            flip_bond_direction_with_history(
                0,
                bonds=bonds,
                before_smiles_input="C=C",
                current_smiles_input_getter=lambda: "C=C",
                bond_state_getter=lambda bond: {"a": bond.a, "b": bond.b, "style": bond.style},
                rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                record_bond_update=lambda *args: record_calls.append(args),
            )
        )

        self.assertEqual((bonds[0].a, bonds[0].b), (2, 1))
        self.assertEqual(rebuild_calls, [(0, True)])
        self.assertEqual(
            record_calls,
            [(0, {"a": 1, "b": 2, "style": "wedge"}, {"a": 2, "b": 1, "style": "wedge"}, "C=C", "C=C")],
        )

    def test_apply_and_cycle_bond_style_with_history_use_expected_rebuild_policy(self) -> None:
        bonds = [Bond(1, 2, 1, style="single"), Bond(3, 4, 1, style="single"), None]
        rebuild_calls: list[tuple[int, bool]] = []
        record_calls: list[tuple[int, dict, dict, object, object]] = []

        self.assertFalse(
            apply_bond_style_with_history(
                9,
                bonds=bonds,
                style="double",
                order=2,
                before_smiles_input="CN",
                current_smiles_input_getter=lambda: "CN",
                bond_state_getter=lambda bond: {"style": bond.style, "order": bond.order},
                rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                record_bond_update=lambda *args: record_calls.append(args),
            )
        )
        self.assertTrue(
            apply_bond_style_with_history(
                0,
                bonds=bonds,
                style="double",
                order=2,
                before_smiles_input="CN",
                current_smiles_input_getter=lambda: "CN",
                bond_state_getter=lambda bond: {"style": bond.style, "order": bond.order},
                rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                record_bond_update=lambda *args: record_calls.append(args),
            )
        )
        self.assertEqual((bonds[0].style, bonds[0].order), ("double", 2))

        with mock.patch("ui.scene_single_item_mutation_logic.cycle_plain_bond_style", return_value=("aromatic", 3)) as cycle_style:
            self.assertFalse(
                cycle_bond_style_with_history(
                    2,
                    bonds=bonds,
                    before_smiles_input="CN",
                    current_smiles_input_getter=lambda: "CN",
                    bond_state_getter=lambda bond: {"style": bond.style, "order": bond.order},
                    rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                    record_bond_update=lambda *args: record_calls.append(args),
                )
            )
            self.assertTrue(
                cycle_bond_style_with_history(
                    1,
                    bonds=bonds,
                    before_smiles_input="CN",
                    current_smiles_input_getter=lambda: "CN",
                    bond_state_getter=lambda bond: {"style": bond.style, "order": bond.order},
                    rebuild_bond_graphics=lambda bond_id, redraw_connected: rebuild_calls.append((bond_id, redraw_connected)),
                    record_bond_update=lambda *args: record_calls.append(args),
                )
            )

        cycle_style.assert_called_once_with("single", 1, allow_double_variants=False)
        self.assertEqual((bonds[1].style, bonds[1].order), ("aromatic", 3))
        self.assertEqual(rebuild_calls, [(0, True), (1, False)])
        self.assertEqual(
            record_calls,
            [
                (0, {"style": "single", "order": 1}, {"style": "double", "order": 2}, "CN", "CN"),
                (1, {"style": "single", "order": 1}, {"style": "aromatic", "order": 3}, "CN", "CN"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
