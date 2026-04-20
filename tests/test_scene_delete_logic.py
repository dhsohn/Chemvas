import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import CompositeCommand, DeleteAtomsCommand, DeleteBondCommand, DeleteSceneItemsCommand
    from core.model import Atom, Bond, MoleculeModel
    from ui.scene_delete_logic import build_delete_selection_plan, classify_delete_selection
    from tests.test_scene_ops_controller import (
        SceneOpsController,
        _FakeCanvas,
        _make_note_item,
        _make_rect_item,
        _make_ring_item,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller tests")
class SceneDeleteLogicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def tearDown(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def test_classify_delete_selection_groups_supported_items_and_ignores_ui_only_items(self) -> None:
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=2)
        ring_item = _make_ring_item()
        note_item = _make_note_item("Mechanism", 12.0, 18.0)
        mark_item = _make_rect_item("mark", data1={"atom_id": None}, state={"kind": "mark"})
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow"})
        ts_bracket_item = _make_rect_item("ts_bracket", state={"kind": "ts_bracket"})
        orbital_item = _make_rect_item("orbital", state={"kind": "orbital"})
        other_item = _make_rect_item("other", state={"kind": "other"})
        ignored_items = [
            _make_rect_item("handle"),
            _make_rect_item("note_box"),
            _make_rect_item("note_select"),
        ]

        buckets = classify_delete_selection(
            [
                atom_item,
                bond_item,
                ring_item,
                note_item,
                mark_item,
                arrow_item,
                ts_bracket_item,
                orbital_item,
                other_item,
                *ignored_items,
            ]
        )

        self.assertEqual(buckets.atom_ids, {1})
        self.assertEqual(buckets.bond_ids, {2})
        self.assertEqual(buckets.ring_items, [ring_item])
        self.assertEqual(buckets.note_items, [note_item])
        self.assertEqual(buckets.mark_items, [mark_item])
        self.assertEqual(buckets.arrow_items, [arrow_item])
        self.assertEqual(buckets.ts_bracket_items, [ts_bracket_item])
        self.assertEqual(buckets.orbital_items, [orbital_item])
        self.assertEqual(buckets.other_items, [other_item])

    def test_classify_delete_selection_skips_wrong_typed_core_items(self) -> None:
        buckets = classify_delete_selection(
            [
                _make_rect_item("atom", data1="bad"),
                _make_rect_item("bond", data1="bad"),
                _make_rect_item("ring"),
                _make_rect_item("note"),
            ]
        )

        self.assertEqual(buckets.atom_ids, set())
        self.assertEqual(buckets.bond_ids, set())
        self.assertEqual(buckets.ring_items, [])
        self.assertEqual(buckets.note_items, [])
        self.assertEqual(buckets.other_items, [])

    def test_build_delete_selection_plan_detects_single_bond_fast_path(self) -> None:
        bond_item = _make_rect_item("bond", data1=0)
        selection = classify_delete_selection(
            [
                bond_item,
                _make_rect_item("handle"),
                _make_rect_item("note_box"),
                _make_rect_item("note_select"),
            ]
        )

        plan = build_delete_selection_plan(
            selection,
            bonds=[Bond(1, 2, 1)],
            marks_by_atom={},
            mark_state_getter=lambda item: {"kind": item.data(0)},
        )

        self.assertEqual(plan.single_bond_id, 0)
        self.assertTrue(plan.has_work())
        self.assertEqual(plan.bond_ids_to_remove, [])
        self.assertEqual(plan.scene_items, [])

    def test_build_delete_selection_plan_single_bond_fast_path_skips_missing_bond(self) -> None:
        selection = classify_delete_selection([_make_rect_item("bond", data1=0)])

        plan = build_delete_selection_plan(
            selection,
            bonds=[None],
            marks_by_atom={},
            mark_state_getter=lambda item: {"kind": item.data(0)},
        )

        self.assertEqual(plan.single_bond_id, None)
        self.assertEqual(plan.bond_ids_to_remove, [0])
        self.assertTrue(plan.has_work())

    def test_build_delete_selection_plan_skips_none_and_unrelated_bonds(self) -> None:
        selection = classify_delete_selection([_make_rect_item("atom", data1=1)])

        plan = build_delete_selection_plan(
            selection,
            bonds=[None, Bond(2, 3, 1)],
            marks_by_atom={},
            mark_state_getter=lambda item: {"kind": item.data(0)},
        )

        self.assertEqual(plan.single_bond_id, None)
        self.assertEqual(plan.bond_ids_to_remove, [])
        self.assertEqual(plan.atom_ids, [1])
        self.assertTrue(plan.clear_smiles_input)

    def test_build_delete_selection_plan_filters_atom_bound_marks_and_requests_handle_clear(self) -> None:
        atom_item = _make_rect_item("atom", data1=1)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
        )
        sibling_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
        )
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 80.0, "y": 5.0},
        )
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow"})
        ts_bracket_item = _make_rect_item("ts_bracket", state={"kind": "ts_bracket"})
        orbital_item = _make_rect_item("orbital", state={"kind": "orbital"})
        other_item = _make_rect_item("other", state={"kind": "other"})

        selection = classify_delete_selection(
            [atom_item, linked_mark, free_mark, arrow_item, ts_bracket_item, orbital_item, other_item]
        )
        plan = build_delete_selection_plan(
            selection,
            bonds=[Bond(1, 2, 2)],
            marks_by_atom={1: [linked_mark, sibling_mark]},
            mark_state_getter=lambda item: dict(item.data(9) or {}),
        )

        self.assertEqual(plan.single_bond_id, None)
        self.assertEqual(plan.bond_ids_to_remove, [0])
        self.assertEqual(plan.atom_ids, [1])
        self.assertEqual(
            plan.mark_states_for_atoms,
            [
                {"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
                {"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
            ],
        )
        self.assertEqual(plan.scene_items, [free_mark, arrow_item, ts_bracket_item, orbital_item, other_item])
        self.assertTrue(plan.clear_handles)
        self.assertTrue(plan.clear_smiles_input)
        self.assertTrue(plan.has_work())

    def test_delete_selected_items_uses_single_bond_fast_path_with_only_ignored_ui_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("O", 30.0, 0.0),
        }
        canvas.model.bonds = [Bond(1, 2, 1)]
        bond_item = _make_rect_item("bond", data1=0)
        handle_item = _make_rect_item("handle")
        note_box_item = _make_rect_item("note_box")
        note_select_item = _make_rect_item("note_select")
        for item in (bond_item, handle_item, note_box_item, note_select_item):
            canvas.add_item(item, selected=True)

        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(canvas.remove_atom_calls, [])
        self.assertEqual(canvas.removed_scene_items, [])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteBondCommand)

    def test_delete_selected_items_classifies_scene_items_and_moves_atom_bound_marks_into_atom_delete_state(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 24.0, 0.0),
            },
            bonds=[Bond(1, 2, 2)],
            next_atom_id=3,
        )
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        ring_item = _make_ring_item()
        note_item = _make_note_item("Mechanism", 40.0, 10.0)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
        )
        sibling_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1},
            state={"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
        )
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 80.0, "y": 5.0},
        )
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (0.0, 0.0), "end": (10.0, 5.0)},
        )
        ts_bracket_item = _make_rect_item(
            "ts_bracket",
            state={"kind": "ts_bracket", "left": 1.0, "top": 2.0, "right": 3.0, "bottom": 4.0},
        )
        orbital_item = _make_rect_item(
            "orbital",
            state={"kind": "orbital", "center": (12.0, 9.0), "rotation": 15.0},
        )
        other_item = _make_rect_item("other", state={"kind": "other", "value": 1})
        handle_item = _make_rect_item("handle", state={"kind": "handle"})
        note_box_item = _make_rect_item("note_box", state={"kind": "note_box"})
        note_select_item = _make_rect_item("note_select", state={"kind": "note_select"})

        for item in (
            atom_item,
            bond_item,
            ring_item,
            note_item,
            linked_mark,
            free_mark,
            arrow_item,
            ts_bracket_item,
            orbital_item,
            other_item,
            handle_item,
            note_box_item,
            note_select_item,
        ):
            canvas.add_item(item, selected=True)
        canvas.add_item(sibling_mark, selected=False)
        canvas._marks_by_atom[1] = [linked_mark, sibling_mark]

        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(canvas.remove_atom_calls, [(1, True)])
        self.assertEqual(canvas.last_smiles_input, None)

        delete_bond_commands = [child for child in command.commands if isinstance(child, DeleteBondCommand)]
        self.assertEqual(len(delete_bond_commands), 1)
        self.assertEqual(delete_bond_commands[0].bond_id, 0)

        delete_atom_commands = [child for child in command.commands if isinstance(child, DeleteAtomsCommand)]
        self.assertEqual(len(delete_atom_commands), 1)
        atom_delete = delete_atom_commands[0]
        self.assertEqual(set(atom_delete.atom_states), {1})
        self.assertEqual(
            atom_delete.mark_states,
            [
                {"kind": "mark", "atom_id": 1, "x": 4.0, "y": -5.0},
                {"kind": "mark", "atom_id": 1, "x": -2.0, "y": 7.0},
            ],
        )

        delete_scene_item_commands = [child for child in command.commands if isinstance(child, DeleteSceneItemsCommand)]
        self.assertEqual(len(delete_scene_item_commands), 1)
        scene_delete = delete_scene_item_commands[0]
        self.assertEqual(
            [state["kind"] for state in scene_delete.item_states],
            ["ring", "note", "mark", "arrow", "ts_bracket", "orbital", "other"],
        )
        self.assertNotIn(linked_mark, scene_delete.items)
        self.assertIn(free_mark, scene_delete.items)
        self.assertNotIn(handle_item, scene_delete.items)
        self.assertNotIn(note_box_item, scene_delete.items)
        self.assertNotIn(note_select_item, scene_delete.items)

    def test_delete_selected_items_keeps_supported_and_ignored_items_separated_from_scene_delete_plan(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Solo", 12.0, 14.0)
        ring_item = _make_ring_item()
        handle_item = _make_rect_item("handle")
        note_box_item = _make_rect_item("note_box")
        note_select_item = _make_rect_item("note_select")
        other_item = _make_rect_item("other", state={"kind": "other", "tag": "x"})

        for item in (note_item, ring_item, handle_item, note_box_item, note_select_item, other_item):
            canvas.add_item(item, selected=True)

        controller = SceneOpsController(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.remove_atom_calls, [])
        self.assertEqual(canvas.remove_bond_calls, [])
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        scene_delete = canvas.pushed_commands[0]
        self.assertEqual([state["kind"] for state in scene_delete.item_states], ["ring", "note", "other"])
        self.assertIn(note_item, scene_delete.items)
        self.assertIn(ring_item, scene_delete.items)
        self.assertIn(other_item, scene_delete.items)
        self.assertNotIn(handle_item, scene_delete.items)
        self.assertNotIn(note_box_item, scene_delete.items)
        self.assertNotIn(note_select_item, scene_delete.items)


if __name__ == "__main__":
    unittest.main()
