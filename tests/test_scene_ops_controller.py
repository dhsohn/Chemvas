import os
import re
import unittest
from types import SimpleNamespace

from tests.ring_support import make_ring, register_ring_double
from tests.scene_operation_support import (
    _FakeCanvas,
    _make_model_ring_item,
    _make_note_item,
    _make_rect_item,
    _set_selectable,
    scene_clipboard_controller_for,
    scene_delete_controller_for,
    scene_transform_controller_for,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont, QImage
from PyQt6.QtWidgets import (
    QApplication,
)

from chemvas.core.history import CompositeCommand
from chemvas.core.model_commands import (
    DeleteAtomsCommand,
    DeleteBondCommand,
)
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.ui.canvas.graphics_items import AtomLabelItem
from chemvas.ui.history.history_commands import DeleteSceneItemsCommand
from chemvas.ui.scene.scene_clipboard_controller import (
    CLIPBOARD_PDF_MIME,
    CLIPBOARD_SVG_MIME,
)
from chemvas.ui.scene.scene_clipboard_transaction_logic import build_clipboard_copy_plan


class SceneOpsControllerTest(unittest.TestCase):
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

    def test_delete_selected_items_returns_false_without_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_delete_controller_for(canvas)

        self.assertFalse(controller.delete_selected_items())
        self.assertEqual(canvas.pushed_commands, [])

    def test_delete_selected_items_uses_single_bond_fast_path(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.atoms = {
            1: Atom("C", 0.0, 0.0),
            2: Atom("O", 30.0, 0.0),
        }
        canvas.model.bonds = [Bond(1, 2, 1)]
        bond_item = _make_rect_item("bond", data1=0)
        canvas.add_item(bond_item, selected=True)

        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(canvas.delete_bond_calls, [])
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], DeleteBondCommand)
        self.assertEqual(
            [
                set(child.atom_states)
                for child in command.commands[1:]
                if isinstance(child, DeleteAtomsCommand)
            ],
            [{1}],
        )
        self.assertEqual(canvas.remove_bond_calls, [0])
        # The oxygen keeps its element label and survives orphaning.
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])
        self.assertIn(2, canvas.model.atoms)
        self.assertEqual(sorted(canvas.redraw_connected_bonds_calls), [1, 2])
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_delete_selected_items_builds_composite_commands_for_mixed_selection(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 2)],
            next_atom_id=3,
        )
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        ring_item = make_ring(canvas=canvas)
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
            state={
                "kind": "ts_bracket",
                "left": 1.0,
                "top": 2.0,
                "right": 3.0,
                "bottom": 4.0,
            },
        )
        orbital_item = _make_rect_item(
            "orbital",
            state={"kind": "orbital", "center": (12.0, 9.0), "rotation": 15.0},
        )
        other_item = _make_rect_item("weird", state={"kind": "weird", "value": 1})
        handle_item = _make_rect_item("handle", state={"kind": "handle"})

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
        ):
            canvas.add_item(item, selected=True)
        canvas.add_item(sibling_mark, selected=False)
        canvas.mark_registry.by_atom[1] = [linked_mark, sibling_mark]

        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.clear_handles_calls, 1)
        self.assertIsNone(canvas.runtime_state.smiles_input_state.last_smiles_input)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(sorted(canvas.redraw_connected_bonds_calls), [1, 2])
        # The oxygen endpoint keeps its element label and survives orphaning.
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])

        delete_bond_commands = [
            child for child in command.commands if isinstance(child, DeleteBondCommand)
        ]
        self.assertEqual(len(delete_bond_commands), 1)
        self.assertEqual(delete_bond_commands[0].bond_id, 0)
        self.assertEqual(delete_bond_commands[0].bond_state["order"], 2)

        delete_atom_commands = [
            child for child in command.commands if isinstance(child, DeleteAtomsCommand)
        ]
        self.assertEqual(len(delete_atom_commands), 1)
        atom_delete = delete_atom_commands[0]
        self.assertEqual(set(atom_delete.atom_states), {1})
        self.assertEqual(atom_delete.mark_states, [])
        self.assertFalse(atom_delete.remove_marks)

        delete_scene_item_commands = [
            child
            for child in command.commands
            if isinstance(child, DeleteSceneItemsCommand)
        ]
        self.assertEqual(len(delete_scene_item_commands), 1)
        scene_delete = delete_scene_item_commands[0]
        deleted_kinds = [state["kind"] for state in scene_delete.item_states]
        self.assertEqual(
            deleted_kinds,
            [
                "ring",
                "note",
                "mark",
                "mark",
                "mark",
                "arrow",
                "ts_bracket",
                "orbital",
                "weird",
            ],
        )
        self.assertEqual(scene_delete.item_ids.count(linked_mark.data(3)), 1)
        self.assertEqual(scene_delete.item_ids.count(sibling_mark.data(3)), 1)
        self.assertIn(free_mark.data(3), scene_delete.item_ids)
        self.assertNotIn(handle_item.data(3), scene_delete.item_ids)
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_delete_bond_removes_only_orphaned_endpoint_atoms(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
                3: Atom("C", 40.0, 0.0),
            },
            bonds=[Bond(1, 2, 1), Bond(2, 3, 1)],
            next_atom_id=4,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], DeleteBondCommand)
        self.assertEqual(
            [
                set(child.atom_states)
                for child in command.commands[1:]
                if isinstance(child, DeleteAtomsCommand)
            ],
            [{1}],
        )
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])
        self.assertEqual(set(canvas.model.atoms), {2, 3})

    def test_delete_bond_removes_both_orphaned_endpoint_atoms(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
            next_atom_id=3,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], DeleteBondCommand)
        self.assertEqual(canvas.remove_atom_calls, [(1, False), (2, False)])
        self.assertEqual(canvas.model.atoms, {})
        self.assertIsNone(canvas.model.bonds[0])

    def test_delete_bond_keeps_labeled_endpoint_atom(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
            next_atom_id=3,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])
        self.assertEqual(set(canvas.model.atoms), {2})

    def test_delete_bond_keeps_marked_endpoint_atom(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
            next_atom_id=3,
        )
        mark_item = _make_rect_item(
            "mark",
            data1={"atom_id": 2},
            state={"kind": "mark", "atom_id": 2, "x": 24.0, "y": -4.0},
        )
        canvas.mark_registry.by_atom[2] = [mark_item]
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_bond(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])
        self.assertEqual(set(canvas.model.atoms), {2})

    def test_delete_atom_removes_invisible_orphaned_neighbor(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
            next_atom_id=3,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_atom(1, record=False)

        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(canvas.remove_bond_calls, [0])
        self.assertEqual(canvas.remove_atom_calls, [(1, False), (2, False)])
        self.assertEqual(canvas.model.atoms, {})

    def test_delete_atom_keeps_labeled_orphaned_neighbor(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
            next_atom_id=3,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_atom(1, record=False)

        self.assertIsNotNone(command)
        self.assertEqual(canvas.remove_atom_calls, [(1, False)])
        self.assertEqual(set(canvas.model.atoms), {2})

    def test_delete_atom_keeps_neighbor_that_still_has_bonds(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 20.0, 0.0),
                3: Atom("C", 40.0, 0.0),
                4: Atom("C", 60.0, 0.0),
            },
            bonds=[Bond(1, 2, 1), Bond(2, 3, 1), Bond(3, 4, 1)],
            next_atom_id=5,
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_atom(2, record=False)

        self.assertIsNotNone(command)
        # Atom 1 loses its only bond and vanishes; atom 3 keeps the bond to 4.
        self.assertEqual(canvas.remove_atom_calls, [(2, False), (1, False)])
        self.assertEqual(set(canvas.model.atoms), {3, 4})

    def test_delete_selected_items_pushes_single_scene_item_command(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Solo", 12.0, 14.0)
        canvas.add_item(note_item, selected=True)
        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [note_item])
        self.assertEqual(canvas.clear_handles_calls, 0)
        self.assertEqual(canvas.suspend_selection_outline_calls, [True, False])
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_delete_selected_items_includes_note_selection_registry(self) -> None:
        canvas = _FakeCanvas()
        note_item = _make_note_item("Registry", 12.0, 14.0)
        canvas.add_item(note_item, selected=False)
        canvas.selected_notes = [note_item]
        controller = scene_delete_controller_for(canvas)

        self.assertTrue(controller.delete_selected_items())
        self.assertEqual(len(canvas.pushed_commands), 1)
        self.assertIsInstance(canvas.pushed_commands[0], DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [note_item])

    def test_delete_ring_prefers_scene_item_controller_when_available(self) -> None:
        canvas = _FakeCanvas()
        ring_item = make_ring(canvas=canvas)
        controller_removed_items: list[object] = []
        canvas.services.scene_item_controller = SimpleNamespace(
            remove_scene_item=controller_removed_items.append
        )
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_ring(ring_item, record=False)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(controller_removed_items, [ring_item])
        self.assertEqual(canvas.removed_scene_items, [])

    def test_delete_ring_records_command_when_enabled(self) -> None:
        canvas = _FakeCanvas()
        ring_item = make_ring(canvas=canvas)
        controller = scene_delete_controller_for(canvas)

        command = controller.delete_ring(ring_item, record=True)

        self.assertIsInstance(command, DeleteSceneItemsCommand)
        self.assertEqual(canvas.removed_scene_items, [ring_item])
        self.assertEqual(canvas.pushed_commands, [command])

    def test_delete_bond_removes_only_broken_ring_fill_and_restores_exact_state(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        operations = canvas.services.history_service.operations
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
                3: Atom("C", 40.0, 0.0),
                4: Atom("C", 60.0, 0.0),
                5: Atom("C", 50.0, 16.0),
            },
            bonds=[
                Bond(0, 1),
                Bond(1, 2),
                Bond(2, 0),
                Bond(3, 4),
                Bond(4, 5),
                Bond(5, 3),
            ],
            next_atom_id=6,
        )

        broken_ring = _make_model_ring_item(
            canvas, [0, 1, 2], color="#a1b2c3", alpha=0.37
        )
        valid_ring = _make_model_ring_item(
            canvas, [3, 4, 5], color="#d4e5f6", alpha=0.23
        )
        for item in (broken_ring, valid_ring):
            register_ring_double(canvas, item)
            canvas.add_item(item)
        original_alpha = broken_ring.brush().color().alphaF()

        command = scene_delete_controller_for(canvas).delete_bond(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertEqual(
            [type(child) for child in command.commands],
            [DeleteSceneItemsCommand, DeleteBondCommand],
        )
        ring_delete = command.commands[0]
        assert isinstance(ring_delete, DeleteSceneItemsCommand)
        self.assertEqual(ring_delete.item_states[0]["atom_ids"], [0, 1, 2])
        self.assertEqual(ring_delete.item_states[0]["color"], "#a1b2c3")
        self.assertEqual(ring_delete.item_states[0]["alpha"], 0.37)
        self.assertNotIn(broken_ring, canvas.ring_items)
        self.assertIsNone(broken_ring.scene())
        self.assertIn(valid_ring, canvas.ring_items)
        self.assertIs(valid_ring.scene(), canvas.scene())

        command.undo(operations)

        self.assertIsNotNone(canvas.model.bonds[0])
        self.assertIn(broken_ring, canvas.ring_items)
        self.assertIs(broken_ring.scene(), canvas.scene())
        self.assertEqual(broken_ring.data(2), [0, 1, 2])
        self.assertEqual(broken_ring.brush().color().name(), "#a1b2c3")
        self.assertAlmostEqual(broken_ring.brush().color().alphaF(), original_alpha)
        self.assertIn(valid_ring, canvas.ring_items)

        command.redo(operations)

        self.assertIsNone(canvas.model.bonds[0])
        self.assertNotIn(broken_ring, canvas.ring_items)
        self.assertIsNone(broken_ring.scene())
        self.assertIn(valid_ring, canvas.ring_items)

    def test_delete_atom_removes_and_restores_its_ring_fill_with_the_atom_transaction(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        operations = canvas.services.history_service.operations
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
            },
            bonds=[Bond(0, 1), Bond(1, 2), Bond(2, 0)],
            next_atom_id=3,
        )
        ring_item = _make_model_ring_item(
            canvas, [0, 1, 2], color="#6a5acd", alpha=0.41
        )
        register_ring_double(canvas, ring_item)
        canvas.add_item(ring_item)

        command = scene_delete_controller_for(canvas).delete_atom(0, record=False)

        self.assertIsInstance(command, CompositeCommand)
        assert isinstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[0], DeleteSceneItemsCommand)
        self.assertNotIn(0, canvas.model.atoms)
        self.assertNotIn(ring_item, canvas.ring_items)
        self.assertIsNone(ring_item.scene())

        command.undo(operations)

        self.assertIn(0, canvas.model.atoms)
        self.assertTrue(
            all(canvas.model.bonds[bond_id] is not None for bond_id in (0, 1, 2))
        )
        self.assertIn(ring_item, canvas.ring_items)
        self.assertIs(ring_item.scene(), canvas.scene())
        self.assertEqual(ring_item.data(2), [0, 1, 2])

        command.redo(operations)

        self.assertNotIn(0, canvas.model.atoms)
        self.assertNotIn(ring_item, canvas.ring_items)
        self.assertIsNone(ring_item.scene())

    def test_broken_ring_cleanup_rolls_back_all_rings_and_bond_when_second_remove_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
            },
            bonds=[Bond(0, 1), Bond(1, 2), Bond(2, 0)],
            next_atom_id=3,
        )
        first_ring = _make_model_ring_item(
            canvas, [0, 1, 2], color="#aa3300", alpha=0.21
        )
        second_ring = _make_model_ring_item(
            canvas, [0, 1, 2], color="#0033aa", alpha=0.43
        )
        for item in (first_ring, second_ring):
            register_ring_double(canvas, item)
            canvas.add_item(item)
        controller = scene_delete_controller_for(canvas)
        remove_calls = 0
        original_remove = controller._remove_scene_item

        def remove_then_fail(item) -> None:
            nonlocal remove_calls
            original_remove(item)
            remove_calls += 1
            if remove_calls == 2:
                raise RuntimeError("second ring remove failed")

        controller._remove_scene_item = remove_then_fail

        with self.assertRaisesRegex(RuntimeError, "second ring remove failed"):
            controller.delete_bond(0, record=False)

        self.assertIsNotNone(canvas.model.bonds[0])
        self.assertEqual(canvas.ring_items, [first_ring, second_ring])
        self.assertIs(first_ring.scene(), canvas.scene())
        self.assertIs(second_ring.scene(), canvas.scene())
        self.assertEqual(first_ring.data(2), [0, 1, 2])
        self.assertEqual(second_ring.data(2), [0, 1, 2])

    def test_multi_selection_deletion_auto_removes_broken_ring_and_preserves_valid_ring(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        operations = canvas.history_service.operations
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 20.0, 0.0),
                2: Atom("C", 10.0, 16.0),
                3: Atom("C", 40.0, 0.0),
                4: Atom("C", 60.0, 0.0),
                5: Atom("C", 50.0, 16.0),
            },
            bonds=[
                Bond(0, 1),
                Bond(1, 2),
                Bond(2, 0),
                Bond(3, 4),
                Bond(4, 5),
                Bond(5, 3),
            ],
            next_atom_id=6,
        )
        broken_ring = _make_model_ring_item(
            canvas, [0, 1, 2], color="#ff8800", alpha=0.31
        )
        valid_ring = _make_model_ring_item(
            canvas, [3, 4, 5], color="#0088ff", alpha=0.27
        )
        for item in (broken_ring, valid_ring):
            register_ring_double(canvas, item)
            canvas.add_item(item)
        atom_item = _make_rect_item("atom", data1=0)
        note_item = _make_note_item("delete together", 80.0, 30.0)
        canvas.add_item(atom_item, selected=True)
        canvas.add_item(note_item, selected=True)

        self.assertTrue(scene_delete_controller_for(canvas).delete_selected_items())

        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertNotIn(broken_ring, canvas.ring_items)
        self.assertIn(valid_ring, canvas.ring_items)
        self.assertIsNone(broken_ring.scene())
        self.assertIs(valid_ring.scene(), canvas.scene())
        self.assertIsNone(note_item.scene())

        command.undo(operations)

        self.assertIn(0, canvas.model.atoms)
        self.assertIn(broken_ring, canvas.ring_items)
        self.assertIn(valid_ring, canvas.ring_items)
        self.assertIs(broken_ring.scene(), canvas.scene())
        self.assertIs(note_item.scene(), canvas.scene())

        command.redo(operations)

        self.assertNotIn(0, canvas.model.atoms)
        self.assertNotIn(broken_ring, canvas.ring_items)
        self.assertIn(valid_ring, canvas.ring_items)
        self.assertIsNone(broken_ring.scene())
        self.assertIsNone(note_item.scene())
        self.assertIs(valid_ring.scene(), canvas.scene())

    def test_clipboard_selection_payload_rejects_wrong_type_and_version(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        clipboard = QApplication.clipboard()

        for raw_payload in (
            b'{"format":"not-chemvas-selection","version":1}',
            b'{"format":"chemvas-selection","version":999}',
        ):
            mime_data = canvas.new_mime_data(raw_payload)
            clipboard.setMimeData(mime_data)
            with self.assertRaisesRegex(ValueError, "format|version"):
                controller.clipboard_selection_payload()

    def test_clipboard_selection_payload_rejects_image_only_clipboard(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        clipboard = QApplication.clipboard()
        mime_data = QImage(4, 4, QImage.Format.Format_ARGB32)
        image_mime = canvas.new_image_mime_data(mime_data)
        clipboard.setMimeData(image_mime)

        self.assertEqual(controller.clipboard_selection_payload(), (None, None))

    def test_selection_payload_for_clipboard_includes_linked_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0, color="#111111", explicit_label=True),
                2: Atom("O", 20.0, 0.0, color="#222222"),
            },
            bonds=[Bond(1, 2, 2, style="double", color="#333333")],
        )
        atom_item = _make_rect_item("atom", data1=1, state={"kind": "atom"})
        bond_item = _make_rect_item("bond", data1=0, state={"kind": "bond"})
        note_item = _make_note_item("payload", 30.0, 40.0)
        free_mark = _make_rect_item(
            "mark",
            data1={"atom_id": None},
            state={"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0},
        )
        free_mark.setPos(50.0, 60.0)
        linked_mark = _make_rect_item(
            "mark",
            data1={"atom_id": 1, "dx": 2.0, "dy": 3.0},
            state={"kind": "mark", "atom_id": 1, "x": 2.0, "y": 3.0},
        )
        linked_mark.setPos(2.0, 3.0)
        ring_item = make_ring(canvas=canvas)
        ring_item.setData(2, [1, 2])
        register_ring_double(canvas, ring_item)
        canvas.mark_registry.by_atom[1] = [linked_mark]
        for item in (atom_item, bond_item, note_item, free_mark, linked_mark):
            canvas.add_item(item, selected=True)
        canvas.add_item(ring_item, selected=False)
        controller = scene_clipboard_controller_for(canvas)

        payload = controller.selection_payload_for_clipboard()

        assert payload is not None
        self.assertEqual(payload["format"], "chemvas-selection")
        self.assertEqual(payload["version"], 3)
        self.assertEqual([atom["id"] for atom in payload["atoms"]], [1, 2])
        self.assertEqual(
            payload["bonds"],
            [{"a": 1, "b": 2, "order": 2, "style": "double", "color": "#333333"}],
        )
        self.assertEqual(
            payload["rings"],
            [],
        )
        self.assertEqual(
            payload["marks"],
            [
                {
                    "kind": "mark",
                    "mark_kind": "plus",
                    "text": None,
                    "atom_id": 1,
                    "dx": 2.0,
                    "dy": 3.0,
                    "x": 2.0,
                    "y": 3.0,
                },
                {
                    "kind": "mark",
                    "mark_kind": "plus",
                    "text": None,
                    "atom_id": None,
                    "dx": None,
                    "dy": None,
                    "x": 50.0,
                    "y": 60.0,
                },
            ],
        )
        self.assertEqual(len(payload["scene_items"]), 1)
        note_state = payload["scene_items"][0]
        self.assertEqual(
            {key: note_state[key] for key in ("kind", "text", "x", "y")},
            {"kind": "note", "text": "payload", "x": 30.0, "y": 40.0},
        )

    def test_selection_payload_for_clipboard_returns_none_for_empty_selection(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        self.assertIsNone(controller.selection_payload_for_clipboard())

    def test_clipboard_copy_plan_uses_union_of_valid_rects(self) -> None:
        first = _make_rect_item("note", rect=QRectF(0.0, 0.0, 10.0, 10.0))
        invalid = _make_rect_item("note", rect=QRectF())
        second = _make_rect_item("note", rect=QRectF(20.0, 10.0, 5.0, 5.0))

        plan = build_clipboard_copy_plan(
            [first, invalid, second],
            payload=None,
            bond_line_width=0.5,
            device_pixel_ratio=1.0,
        )

        assert plan is not None
        self.assertEqual(plan.source, QRectF(-2.5, -2.5, 30.0, 20.0))

    def test_copy_selection_to_clipboard_handles_empty_and_successful_copy(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        self.assertFalse(controller.copy_selection_to_clipboard())

        note_item = _make_note_item("copy", 10.0, 12.0)
        canvas.add_item(note_item, selected=True)
        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNotNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_SVG_MIME))
        self.assertTrue(mime_data.hasFormat(CLIPBOARD_PDF_MIME))
        self.assertIn(b"<svg", bytes(mime_data.data(CLIPBOARD_SVG_MIME)))
        self.assertTrue(bytes(mime_data.data(CLIPBOARD_PDF_MIME)).startswith(b"%PDF-"))
        self.assertTrue(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))

    def test_vector_clipboard_uses_label_ink_bounds_not_hit_bounds(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        label = _set_selectable(AtomLabelItem("N", hit_radius=80.0))
        label.setFont(QFont("Arial", 12))
        label.setData(0, "note")
        label.setData(9, {"kind": "note", "text": "N", "x": 10.0, "y": 12.0})
        label.setPos(10.0, 12.0)
        canvas.add_item(label, selected=True)

        self.assertTrue(controller.copy_selection_to_clipboard())
        svg_data = bytes(QApplication.clipboard().mimeData().data(CLIPBOARD_SVG_MIME))
        match = re.search(rb'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg_data)

        self.assertIsNotNone(match)
        assert match is not None
        vector_width = float(match.group(1))
        self.assertLess(vector_width, label.sceneBoundingRect().width())

    def test_paste_selection_remaps_atom_ids_and_restores_selection(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        stale_item = _make_rect_item("stale")
        canvas.add_item(stale_item, selected=True)

        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {
                    "id": 10,
                    "element": "C",
                    "x": 5.0,
                    "y": 10.0,
                    "color": "#ff0000",
                    "explicit_label": True,
                },
                {"id": 11, "element": "O", "x": 25.0, "y": 30.0, "color": "#00ff00"},
            ],
            "bonds": [
                {"a": 10, "b": 11, "order": 2, "style": "double", "color": "#123456"},
            ],
            "rings": [],
            "marks": [
                {"kind": "mark", "atom_id": 10, "x": 8.0, "y": 12.0},
            ],
            "scene_items": [
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
            ],
        }
        controller.clipboard_selection_payload = lambda: (payload, "payload-json")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "payload-json")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
        self.assertEqual(set(canvas.model.atoms), {0, 1})
        self.assertEqual(canvas.model.atoms[0].color, "#ff0000")
        self.assertTrue(canvas.model.atoms[0].explicit_label)
        self.assertEqual(canvas.model.atoms[1].color, "#00ff00")
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual((canvas.model.bonds[0].a, canvas.model.bonds[0].b), (0, 1))
        self.assertEqual(
            canvas.restore_bond_calls,
            [
                (
                    0,
                    {
                        "a": 0,
                        "b": 1,
                        "order": 2,
                        "style": "double",
                        "color": "#123456",
                    },
                )
            ],
        )
        self.assertEqual(
            canvas.created_scene_item_states,
            [
                {"kind": "mark", "atom_id": 0, "x": 26.0, "y": 30.0},
                {"kind": "note", "text": "copied", "x": 68.0, "y": 78.0},
            ],
        )
        self.assertFalse(stale_item.isSelected())
        self.assertTrue(canvas._atom_item_for_id(0).isSelected())
        self.assertTrue(canvas._atom_item_for_id(1).isSelected())
        self.assertTrue(canvas.created_items[0].isSelected())
        self.assertTrue(canvas.created_items[1].isSelected())
        self.assertEqual(canvas.selected_notes, [canvas.created_items[1]])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertEqual(
            canvas.record_additions_calls,
            [
                (0, 0, None, canvas.created_items),
            ],
        )

    def test_paste_selection_from_clipboard_rejects_missing_or_empty_payload(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        controller.clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller.clipboard_selection_payload = lambda: (
            {
                "format": "chemvas-selection",
                "version": 2,
                "atoms": [],
                "bonds": [],
                "rings": [],
                "marks": [],
                "scene_items": [],
            },
            "payload-json",
        )
        self.assertFalse(controller.paste_selection_from_clipboard())

    def test_paste_selection_from_clipboard_accepts_scene_item_only_payload_and_resets_source(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "old-source"
        canvas.scene_clipboard_state.paste_count = 5
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [{"id": "bad"}],
            "bonds": [{"a": 1, "b": "bad"}],
            "rings": [],
            "marks": [],
            "scene_items": [{"kind": "note", "text": "solo", "x": 10.0, "y": 15.0}],
        }
        controller.clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertTrue(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "new-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
        self.assertEqual(
            canvas.created_scene_item_states,
            [{"kind": "note", "text": "solo", "x": 28.0, "y": 33.0}],
        )
        self.assertEqual(
            canvas.record_additions_calls, [(0, 0, None, canvas.created_items)]
        )

    def test_flip_selected_items_noop_paths(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_transform_controller_for(canvas)

        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])

    def test_flip_selected_items_skips_atom_component_without_center(self) -> None:
        canvas = _FakeCanvas()
        missing_atom_item = _make_rect_item("atom", data1=99)
        canvas.add_item(missing_atom_item, selected=True)
        controller = scene_transform_controller_for(canvas)

        controller.flip_selected_items(horizontal=True)

        self.assertEqual(canvas.pushed_commands, [])
        self.assertEqual(canvas.update_selection_outline_calls, 0)
