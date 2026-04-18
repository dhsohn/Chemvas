import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    AddSceneItemsCommand,
    ChangeAtomLabelCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    DeleteSceneItemsCommand,
    MoveAtomsCommand,
    MoveItemsCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    SetSmilesInputCommand,
    UpdateAtomColorCommand,
    UpdateBondCommand,
    UpdateBondLengthCommand,
    UpdateSceneItemCommand,
)


class _RecorderCommand:
    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self.log = log

    def undo(self, canvas) -> None:
        self.log.append(f"undo:{self.name}")

    def redo(self, canvas) -> None:
        self.log.append(f"redo:{self.name}")


class _FakeItem:
    def __init__(self, scene_obj, raises: bool = False) -> None:
        self._scene_obj = scene_obj
        self._raises = raises

    def scene(self):
        if self._raises:
            raise RuntimeError("item deleted")
        return self._scene_obj


class _FakeRenderer:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def set_bond_length(self, length: float) -> None:
        self.canvas.calls.append(("set_bond_length", length))


class _FakeCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.last_smiles_input = None
        self.model = SimpleNamespace(next_atom_id=0)
        self._scene_obj = object()
        self.renderer = _FakeRenderer(self)
        self._projection_center_3d = "before-center"
        self._projection_anchor_2d = "before-anchor"

    def scene(self):
        return self._scene_obj

    def move_atoms(self, atom_ids, dx, dy, bond_ids=None, redraw_bond_ids=None, update_selection=True) -> None:
        self.calls.append(("move_atoms", set(atom_ids), dx, dy, bond_ids, redraw_bond_ids, update_selection))

    def move_item(self, item, dx, dy, update_selection=False) -> None:
        self.calls.append(("move_item", item, dx, dy, update_selection))

    def _update_selection_outline(self) -> None:
        self.calls.append(("_update_selection_outline",))

    def set_atom_positions(self, positions, update_selection=True) -> None:
        self.calls.append(("set_atom_positions", dict(positions), update_selection))

    def set_ring_polygons(self, ring_items, polygons) -> None:
        self.calls.append(("set_ring_polygons", list(ring_items), list(polygons)))

    def _rebuild_graphics(self) -> None:
        self.calls.append(("_rebuild_graphics",))

    def _mark_spatial_index_dirty(self) -> None:
        self.calls.append(("_mark_spatial_index_dirty",))

    def _remove_atom_only(self, atom_id, remove_marks=True) -> None:
        self.calls.append(("_remove_atom_only", atom_id, remove_marks))

    def _restore_atom_from_state(self, atom_id, state) -> None:
        self.calls.append(("_restore_atom_from_state", atom_id, dict(state)))

    def apply_atom_color(self, atom_id, color) -> None:
        self.calls.append(("apply_atom_color", atom_id, color))

    def apply_scene_item_state(self, item, state) -> None:
        self.calls.append(("apply_scene_item_state", item, dict(state)))

    def create_scene_item_from_state(self, state):
        item = {"created_from": dict(state)}
        self.calls.append(("create_scene_item_from_state", dict(state)))
        return item

    def restore_scene_item(self, item) -> None:
        self.calls.append(("restore_scene_item", item))

    def remove_scene_item(self, item) -> None:
        self.calls.append(("remove_scene_item", item))

    def add_or_update_atom_label(
        self,
        atom_id,
        element,
        clear_smiles=False,
        record=False,
        allow_merge=False,
        show_carbon=False,
    ) -> None:
        self.calls.append(
            (
                "add_or_update_atom_label",
                atom_id,
                element,
                clear_smiles,
                record,
                allow_merge,
                show_carbon,
            )
        )

    def _remove_bond_by_id(self, bond_id) -> None:
        self.calls.append(("_remove_bond_by_id", bond_id))

    def _trim_bonds_to_length(self, previous_bond_count) -> None:
        self.calls.append(("_trim_bonds_to_length", previous_bond_count))

    def _restore_bond_from_state(self, bond_id, bond_state) -> None:
        self.calls.append(("_restore_bond_from_state", bond_id, dict(bond_state)))

    def _restore_mark_from_state(self, mark_state) -> None:
        self.calls.append(("_restore_mark_from_state", dict(mark_state)))


class _FakeSceneItemController:
    def __init__(self, canvas: _FakeCanvas) -> None:
        self.canvas = canvas

    def apply_scene_item_state(self, item, state) -> None:
        self.canvas.calls.append(("controller_apply_scene_item_state", item, dict(state)))

    def create_scene_item_from_state(self, state):
        item = {"controller_created_from": dict(state)}
        self.canvas.calls.append(("controller_create_scene_item_from_state", dict(state)))
        return item

    def restore_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_restore_scene_item", item))

    def remove_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_remove_scene_item", item))

    def _restore_mark_from_state(self, mark_state) -> None:
        self.canvas.calls.append(("controller_restore_mark_from_state", dict(mark_state)))


class HistoryCommandTest(unittest.TestCase):
    def test_composite_command_undo_redo_order(self) -> None:
        log: list[str] = []
        command = CompositeCommand(
            [_RecorderCommand("first", log), _RecorderCommand("second", log), _RecorderCommand("third", log)]
        )

        command.undo(None)
        command.redo(None)

        self.assertEqual(
            log,
            [
                "undo:third",
                "undo:second",
                "undo:first",
                "redo:first",
                "redo:second",
                "redo:third",
            ],
        )

    def test_move_commands_delegate_to_canvas(self) -> None:
        canvas = _FakeCanvas()
        move_atoms = MoveAtomsCommand({1, 2}, 3.5, -4.0, bond_ids={7}, redraw_bond_ids={8})
        scene_item = _FakeItem(canvas.scene())
        off_scene_item = _FakeItem(object())
        dead_item = _FakeItem(canvas.scene(), raises=True)
        move_items = MoveItemsCommand([scene_item, off_scene_item, dead_item], 2.0, 5.0)

        move_atoms.undo(canvas)
        move_atoms.redo(canvas)
        move_items.undo(canvas)
        move_items.redo(canvas)

        self.assertIn(("move_atoms", {1, 2}, -3.5, 4.0, {7}, {8}, True), canvas.calls)
        self.assertIn(("move_atoms", {1, 2}, 3.5, -4.0, {7}, {8}, True), canvas.calls)
        self.assertEqual(canvas.calls.count(("move_item", scene_item, -2.0, -5.0, False)), 1)
        self.assertEqual(canvas.calls.count(("move_item", scene_item, 2.0, 5.0, False)), 1)
        self.assertEqual(canvas.calls.count(("_update_selection_outline",)), 2)

    def test_position_and_polygon_commands_delegate(self) -> None:
        canvas = _FakeCanvas()
        atom_command = SetAtomPositionsCommand({1: (0.0, 0.0)}, {1: (2.0, 3.0)}, update_selection=False)
        ring_command = SetRingPolygonsCommand(["ring"], [[(0.0, 0.0)]], [[(1.0, 1.0)]])

        atom_command.undo(canvas)
        atom_command.redo(canvas)
        ring_command.undo(canvas)
        ring_command.redo(canvas)

        self.assertIn(("set_atom_positions", {1: (0.0, 0.0)}, False), canvas.calls)
        self.assertIn(("set_atom_positions", {1: (2.0, 3.0)}, False), canvas.calls)
        self.assertIn(("set_ring_polygons", ["ring"], [[(0.0, 0.0)]]), canvas.calls)
        self.assertIn(("set_ring_polygons", ["ring"], [[(1.0, 1.0)]]), canvas.calls)

    def test_set_atom_positions_command_restores_projection_state(self) -> None:
        canvas = _FakeCanvas()
        command = SetAtomPositionsCommand(
            {1: (0.0, 0.0)},
            {1: (2.0, 3.0)},
            before_coords_3d={1: (0.0, 0.0, 0.0)},
            after_coords_3d={1: (2.0, 3.0, 4.0)},
            restore_projection_state=True,
            before_projection_center_3d=None,
            after_projection_center_3d=(5.0, 6.0, 7.0),
            before_projection_anchor_2d=None,
            after_projection_anchor_2d=(8.0, 9.0),
        )

        command.redo(canvas)
        self.assertEqual(canvas._projection_center_3d, (5.0, 6.0, 7.0))
        self.assertEqual(canvas._projection_anchor_2d, (8.0, 9.0))

        command.undo(canvas)
        self.assertIsNone(canvas._projection_center_3d)
        self.assertIsNone(canvas._projection_anchor_2d)

    def test_update_commands_apply_length_color_scene_state_and_smiles(self) -> None:
        canvas = _FakeCanvas()
        length_command = UpdateBondLengthCommand(18.0, 24.0)
        smiles_command = SetSmilesInputCommand("before", "after")
        color_command = UpdateAtomColorCommand(4, "#000000", "#ff0000")
        scene_state_command = UpdateSceneItemCommand("item", {"x": 1}, {"x": 2})

        length_command.undo(canvas)
        length_command.redo(canvas)
        smiles_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before")
        smiles_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after")
        color_command.undo(canvas)
        color_command.redo(canvas)
        scene_state_command.undo(canvas)
        scene_state_command.redo(canvas)

        self.assertEqual(canvas.calls.count(("_rebuild_graphics",)), 2)
        self.assertEqual(canvas.calls.count(("_mark_spatial_index_dirty",)), 2)
        self.assertIn(("apply_atom_color", 4, "#000000"), canvas.calls)
        self.assertIn(("apply_atom_color", 4, "#ff0000"), canvas.calls)
        self.assertIn(("apply_scene_item_state", "item", {"x": 1}), canvas.calls)
        self.assertIn(("apply_scene_item_state", "item", {"x": 2}), canvas.calls)

    def test_atom_commands_restore_and_remove_atoms_and_marks(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.next_atom_id = 10
        add_command = AddAtomsCommand(
            atom_states={3: {"element": "C"}},
            before_next_atom_id=3,
            after_next_atom_id=4,
            before_smiles_input="old",
            after_smiles_input="new",
        )
        delete_command = DeleteAtomsCommand(
            atom_states={3: {"element": "O"}},
            mark_states=[{"kind": "plus"}],
            before_next_atom_id=4,
            after_next_atom_id=3,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        add_command.undo(canvas)
        add_command.redo(canvas)
        delete_command.undo(canvas)
        delete_command.redo(canvas)

        self.assertIn(("_remove_atom_only", 3, True), canvas.calls)
        self.assertIn(("_restore_atom_from_state", 3, {"element": "C"}), canvas.calls)
        self.assertIn(("_restore_atom_from_state", 3, {"element": "O"}), canvas.calls)
        self.assertIn(("_restore_mark_from_state", {"kind": "plus"}), canvas.calls)
        self.assertEqual(canvas.model.next_atom_id, 3)
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_delete_atoms_command_can_skip_mark_restoration_and_mark_removal(self) -> None:
        canvas = _FakeCanvas()
        command = DeleteAtomsCommand(
            atom_states={8: {"element": "N"}},
            mark_states=[{"kind": "minus"}],
            before_next_atom_id=9,
            after_next_atom_id=8,
            before_smiles_input="before",
            after_smiles_input="after",
            remove_marks=False,
        )

        command.undo(canvas)
        command.redo(canvas)

        self.assertIn(("_restore_atom_from_state", 8, {"element": "N"}), canvas.calls)
        self.assertIn(("_remove_atom_only", 8, False), canvas.calls)
        self.assertNotIn(("_restore_mark_from_state", {"kind": "minus"}), canvas.calls)
        self.assertEqual(canvas.model.next_atom_id, 8)
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_scene_item_commands_create_remove_and_restore_items(self) -> None:
        canvas = _FakeCanvas()
        add_command = AddSceneItemsCommand(item_states=[{"kind": "note"}])
        delete_command = DeleteSceneItemsCommand(item_states=[{"kind": "arrow"}])

        add_command.redo(canvas)
        add_item = add_command.items[0]
        add_command.undo(canvas)
        add_command.redo(canvas)

        delete_command.undo(canvas)
        delete_item = delete_command.items[0]
        delete_command.redo(canvas)
        delete_command.undo(canvas)

        self.assertIn(("create_scene_item_from_state", {"kind": "note"}), canvas.calls)
        self.assertIn(("remove_scene_item", add_item), canvas.calls)
        self.assertIn(("restore_scene_item", add_item), canvas.calls)
        self.assertIn(("create_scene_item_from_state", {"kind": "arrow"}), canvas.calls)
        self.assertIn(("remove_scene_item", delete_item), canvas.calls)
        self.assertIn(("restore_scene_item", delete_item), canvas.calls)

    def test_scene_item_commands_prefer_scene_item_controller_when_available(self) -> None:
        canvas = _FakeCanvas()
        canvas._scene_item_controller = _FakeSceneItemController(canvas)
        add_command = AddSceneItemsCommand(item_states=[{"kind": "note"}])
        delete_command = DeleteSceneItemsCommand(item_states=[{"kind": "arrow"}])
        update_command = UpdateSceneItemCommand("item", {"x": 1}, {"x": 2})
        delete_atoms_command = DeleteAtomsCommand(
            atom_states={},
            mark_states=[{"kind": "plus"}],
            before_next_atom_id=1,
            after_next_atom_id=1,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        add_command.redo(canvas)
        add_item = add_command.items[0]
        add_command.undo(canvas)
        add_command.redo(canvas)

        delete_command.undo(canvas)
        delete_item = delete_command.items[0]
        delete_command.redo(canvas)
        delete_command.undo(canvas)

        update_command.undo(canvas)
        update_command.redo(canvas)
        delete_atoms_command.undo(canvas)

        self.assertIn(("controller_create_scene_item_from_state", {"kind": "note"}), canvas.calls)
        self.assertIn(("controller_remove_scene_item", add_item), canvas.calls)
        self.assertIn(("controller_restore_scene_item", add_item), canvas.calls)
        self.assertIn(("controller_create_scene_item_from_state", {"kind": "arrow"}), canvas.calls)
        self.assertIn(("controller_remove_scene_item", delete_item), canvas.calls)
        self.assertIn(("controller_restore_scene_item", delete_item), canvas.calls)
        self.assertIn(("controller_apply_scene_item_state", "item", {"x": 1}), canvas.calls)
        self.assertIn(("controller_apply_scene_item_state", "item", {"x": 2}), canvas.calls)
        self.assertIn(("controller_restore_mark_from_state", {"kind": "plus"}), canvas.calls)
        self.assertNotIn(("create_scene_item_from_state", {"kind": "note"}), canvas.calls)
        self.assertNotIn(("apply_scene_item_state", "item", {"x": 1}), canvas.calls)
        self.assertNotIn(("_restore_mark_from_state", {"kind": "plus"}), canvas.calls)

    def test_change_atom_label_command_replays_label_state_without_recording(self) -> None:
        canvas = _FakeCanvas()
        command = ChangeAtomLabelCommand(
            atom_id=5,
            before_element="C",
            after_element="N",
            before_explicit_label=False,
            after_explicit_label=True,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before")
        command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after")

        self.assertEqual(
            canvas.calls[0],
            ("add_or_update_atom_label", 5, "C", False, False, False, False),
        )
        self.assertEqual(
            canvas.calls[1],
            ("add_or_update_atom_label", 5, "N", False, False, False, True),
        )

    def test_change_atom_label_command_prefers_atom_label_service_when_available(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas._atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )
        command = ChangeAtomLabelCommand(
            atom_id=7,
            before_element="C",
            after_element="Cl",
            before_explicit_label=False,
            after_explicit_label=False,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        command.redo(canvas)

        self.assertEqual(
            service_calls,
            [
                (
                    7,
                    "Cl",
                    {
                        "clear_smiles": False,
                        "record": False,
                        "allow_merge": False,
                        "show_carbon": False,
                    },
                )
            ],
        )
        self.assertEqual(canvas.calls, [])
        self.assertEqual(canvas.last_smiles_input, "after")

    def test_bond_commands_remove_trim_and_restore(self) -> None:
        canvas = _FakeCanvas()
        add_command = AddBondCommand(
            bond_id=2,
            bond_state={"order": 1},
            previous_bond_count=5,
            before_smiles_input="before-add",
            after_smiles_input="after-add",
        )
        delete_command = DeleteBondCommand(
            bond_id=3,
            bond_state={"order": 2},
            before_smiles_input="before-delete",
            after_smiles_input="after-delete",
        )
        update_command = UpdateBondCommand(
            bond_id=4,
            before_state={"order": 1},
            after_state={"order": 3},
            before_smiles_input="before-update",
            after_smiles_input="after-update",
        )

        add_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-add")
        add_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-add")

        delete_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-delete")
        delete_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-delete")

        update_command.undo(canvas)
        self.assertEqual(canvas.last_smiles_input, "before-update")
        update_command.redo(canvas)
        self.assertEqual(canvas.last_smiles_input, "after-update")

        self.assertIn(("_remove_bond_by_id", 2), canvas.calls)
        self.assertIn(("_trim_bonds_to_length", 5), canvas.calls)
        self.assertIn(("_restore_bond_from_state", 2, {"order": 1}), canvas.calls)
        self.assertIn(("_restore_bond_from_state", 3, {"order": 2}), canvas.calls)
        self.assertIn(("_restore_bond_from_state", 4, {"order": 1}), canvas.calls)
        self.assertIn(("_restore_bond_from_state", 4, {"order": 3}), canvas.calls)


if __name__ == "__main__":
    unittest.main()
