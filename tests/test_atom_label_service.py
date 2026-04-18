import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QBrush, QColor, QFont
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.history import (
        ChangeAtomLabelCommand,
        CompositeCommand,
        DeleteAtomsCommand,
        DeleteBondCommand,
        UpdateBondCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.atom_label_service import AtomLabelService
    from ui.graphics_items import AtomLabelItem


class _FakeScene:
    def __init__(self) -> None:
        self.added_items = []
        self.removed_items = []

    def addItem(self, item) -> None:
        self.added_items.append(item)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class _FakeGraphicsItem:
    def __init__(self, selected: bool = False) -> None:
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(
                bond_length_px=20.0,
                atom_color="#223344",
                atom_label_offset_px=2.0,
                bond_line_width=1.0,
            ),
            atom_font=Mock(return_value=QFont()),
        )
        self.atom_items = {}
        self.atom_dots = {}
        self.bond_items = {}
        self.last_smiles_input = None
        self.hover_atom_id = None
        self._history_enabled = True

        self.scene_obj = _FakeScene()
        self.redraw_calls = []
        self.rebuild_bond_adjacency_calls = 0
        self.pushed_commands = []
        self._refresh_hover_from_cursor = Mock()

    def scene(self) -> _FakeScene:
        return self.scene_obj

    def _atom_state_dict(self, atom_id: int) -> dict:
        return {"atom_id": atom_id}

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _rebuild_bond_adjacency(self) -> None:
        self.rebuild_bond_adjacency_calls += 1

    def _redraw_connected_bonds(self, atom_id: int) -> None:
        self.redraw_calls.append(atom_id)

    def _atom_pick_radius(self) -> float:
        return 4.0

    def _uses_compact_label_hit_shape(self, text: str) -> bool:
        return len(text.strip()) <= 2

    def _implicit_carbon_dot_brush(self) -> QBrush:
        return QBrush(QColor("#223344"))

    def _make_selectable(self, item) -> None:
        if not hasattr(item, "setFlag"):
            return
        try:
            item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
        except AttributeError:
            return

    def _push_command(self, command) -> None:
        self.pushed_commands.append(command)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for atom label service tests")
class AtomLabelServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_merge_overlapping_atoms_is_noop_without_nearby_atoms(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 10.0, 0.0),
            }
        )
        service = AtomLabelService(canvas)

        merge_ids, merge_info = service.merge_overlapping_atoms(1)

        self.assertEqual(merge_ids, [])
        self.assertEqual(merge_info, {})
        self.assertEqual(canvas.rebuild_bond_adjacency_calls, 0)
        self.assertEqual(canvas.scene_obj.removed_items, [])

    def test_merge_overlapping_atoms_returns_early_for_missing_atom(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 0.0, 0.0)})
        service = AtomLabelService(canvas)

        merge_ids, merge_info = service.merge_overlapping_atoms(99)

        self.assertEqual(merge_ids, [])
        self.assertEqual(merge_info, {})
        self.assertEqual(canvas.rebuild_bond_adjacency_calls, 0)
        self.assertEqual(canvas.scene_obj.removed_items, [])

    def test_merge_overlapping_atoms_deletes_self_loops_and_weaker_duplicates(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 0.4, 0.3),
                3: Atom("N", 6.0, 0.0),
            },
            bonds=[
                Bond(1, 2, 1),
                Bond(1, 3, 1),
                Bond(2, 3, 2),
            ],
        )
        merged_label = _FakeGraphicsItem()
        merged_dot = _FakeGraphicsItem()
        deleted_self_loop_item = _FakeGraphicsItem()
        deleted_duplicate_item = _FakeGraphicsItem()
        canvas.atom_items[2] = merged_label
        canvas.atom_dots[2] = merged_dot
        canvas.bond_items = {
            0: [deleted_self_loop_item],
            1: [deleted_duplicate_item],
            2: [_FakeGraphicsItem()],
        }
        service = AtomLabelService(canvas)

        merge_ids, merge_info = service.merge_overlapping_atoms(1)

        self.assertEqual(merge_ids, [2])
        self.assertEqual(merge_info["atom_states"], {2: {"atom_id": 2}})
        self.assertEqual(set(merge_info["bond_before_states"]), {0, 1, 2})
        self.assertCountEqual(merge_info["deleted_bond_ids"], [0, 1])
        self.assertNotIn(2, canvas.model.atoms)
        self.assertIsNone(canvas.model.bonds[0])
        self.assertIsNone(canvas.model.bonds[1])
        self.assertEqual(canvas.model.bonds[2], Bond(1, 3, 2))
        self.assertEqual(canvas.rebuild_bond_adjacency_calls, 1)
        self.assertCountEqual(
            canvas.scene_obj.removed_items,
            [merged_label, merged_dot, deleted_self_loop_item, deleted_duplicate_item],
        )

    def test_merge_overlapping_atoms_keeps_special_style_on_same_order_duplicate(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 0.3, 0.2),
                3: Atom("O", 5.0, 0.0),
            },
            bonds=[
                Bond(1, 3, 1, style="single"),
                Bond(2, 3, 1, style="wedge"),
            ],
        )
        removed_standard_bond_item = _FakeGraphicsItem()
        kept_special_bond_item = _FakeGraphicsItem()
        canvas.bond_items = {
            0: [removed_standard_bond_item],
            1: [kept_special_bond_item],
        }
        service = AtomLabelService(canvas)

        merge_ids, merge_info = service.merge_overlapping_atoms(1)

        self.assertEqual(merge_ids, [2])
        self.assertEqual(canvas.model.bonds[0], None)
        self.assertEqual(canvas.model.bonds[1], Bond(1, 3, 1, style="wedge"))
        self.assertEqual(merge_info["deleted_bond_ids"], [0])
        self.assertEqual(merge_info["bond_before_states"][0]["style"], "single")
        self.assertEqual(merge_info["bond_before_states"][1]["style"], "wedge")
        self.assertIn(removed_standard_bond_item, canvas.scene_obj.removed_items)
        self.assertNotIn(kept_special_bond_item, canvas.scene_obj.removed_items)

    def test_merge_overlapping_atoms_skips_none_bonds_and_discards_later_weaker_duplicate(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 0.2, 0.3),
                3: Atom("O", 5.0, 0.0),
            },
            bonds=[
                None,
                Bond(1, 3, 1, style="wedge"),
                Bond(2, 3, 1, style="single"),
            ],
        )
        kept_special_bond_item = _FakeGraphicsItem()
        removed_weaker_bond_item = _FakeGraphicsItem()
        canvas.bond_items = {
            1: [kept_special_bond_item],
            2: [removed_weaker_bond_item],
        }
        service = AtomLabelService(canvas)

        merge_ids, merge_info = service.merge_overlapping_atoms(1)

        self.assertEqual(merge_ids, [2])
        self.assertIsNone(canvas.model.bonds[0])
        self.assertEqual(canvas.model.bonds[1], Bond(1, 3, 1, style="wedge"))
        self.assertIsNone(canvas.model.bonds[2])
        self.assertEqual(merge_info["deleted_bond_ids"], [2])
        self.assertEqual(merge_info["bond_before_states"][2]["style"], "single")
        self.assertIn(removed_weaker_bond_item, canvas.scene_obj.removed_items)
        self.assertNotIn(kept_special_bond_item, canvas.scene_obj.removed_items)

    def test_atom_item_for_id_prefers_label_then_dot(self) -> None:
        canvas = _FakeCanvas()
        label_item = AtomLabelItem(hit_padding=0.5, hit_radius=None)
        dot_item = _FakeGraphicsItem()
        canvas.atom_items[1] = label_item
        canvas.atom_dots[1] = dot_item
        service = AtomLabelService(canvas)

        self.assertIs(service.atom_item_for_id(1), label_item)
        canvas.atom_items.pop(1)
        self.assertIs(service.atom_item_for_id(1), dot_item)
        self.assertIsNone(service.atom_item_for_id(99))

    def test_carbon_dot_helpers_position_label_and_restore_item_interaction(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 4.0, 6.0)})
        service = AtomLabelService(canvas)

        service.ensure_carbon_dot(1)
        dot_item = canvas.atom_dots[1]
        self.assertEqual(dot_item.data(0), "atom")
        self.assertEqual(dot_item.data(1), 1)
        self.assertIn(dot_item, canvas.scene_obj.added_items)

        label_item = AtomLabelItem(hit_padding=0.5, hit_radius=None)
        label_item.setPlainText("NH")
        service.position_label(label_item, 10.0, 12.0)
        self.assertAlmostEqual(
            label_item.pos().x() + label_item.boundingRect().center().x() - canvas.renderer.style.atom_label_offset_px,
            10.0,
        )
        self.assertAlmostEqual(
            label_item.pos().y() + label_item.boundingRect().center().y() + canvas.renderer.style.atom_label_offset_px,
            12.0,
        )

        replacement_item = _FakeGraphicsItem()
        canvas.atom_items[1] = replacement_item
        service.restore_atom_item_interaction(1, _FakeGraphicsItem(selected=True), was_selected=True, refresh_hover=True)
        self.assertTrue(replacement_item.isSelected())
        canvas._refresh_hover_from_cursor.assert_called_once_with()

        service.remove_carbon_dot(1)
        self.assertNotIn(1, canvas.atom_dots)
        self.assertIn(dot_item, canvas.scene_obj.removed_items)

    def test_record_label_change_builds_composite_single_and_noop_commands(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={5: Atom("N", 1.0, 2.0, explicit_label=True)},
            bonds=[
                Bond(5, 6, 2, style="double", color="#112233"),
                None,
            ],
        )
        canvas.model.next_atom_id = 8
        canvas.last_smiles_input = "after"
        service = AtomLabelService(canvas)

        service.record_label_change(
            atom_id=5,
            before_element="C",
            before_explicit_label=False,
            before_smiles_input="before",
            merge_ids=[7],
            merge_info={
                "bond_before_states": {
                    0: {"a": 5, "b": 6, "order": 1, "style": "single", "color": "#000000"},
                    1: {"a": 7, "b": 8, "order": 1, "style": "single", "color": "#abcdef"},
                },
                "deleted_bond_ids": [1],
                "atom_states": {7: {"element": "C"}},
            },
        )

        self.assertEqual(len(canvas.pushed_commands), 1)
        composite = canvas.pushed_commands.pop()
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(
            [type(command) for command in composite.commands],
            [ChangeAtomLabelCommand, UpdateBondCommand, DeleteBondCommand, DeleteAtomsCommand],
        )
        self.assertFalse(composite.commands[-1].remove_marks)

        service.record_label_change(
            atom_id=5,
            before_element="C",
            before_explicit_label=True,
            before_smiles_input="before",
            merge_ids=[],
            merge_info={},
        )
        self.assertIsInstance(canvas.pushed_commands.pop(), ChangeAtomLabelCommand)

        service.record_label_change(
            atom_id=5,
            before_element="N",
            before_explicit_label=True,
            before_smiles_input="after",
            merge_ids=[],
            merge_info={},
        )
        self.assertEqual(canvas.pushed_commands, [])

        canvas._history_enabled = False
        service.record_label_change(
            atom_id=5,
            before_element="C",
            before_explicit_label=False,
            before_smiles_input="before",
            merge_ids=[7],
            merge_info={"atom_states": {7: {"element": "C"}}},
        )
        self.assertEqual(canvas.pushed_commands, [])

    def test_add_or_update_atom_label_removes_label_to_carbon_dot_and_records_change(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0, explicit_label=True)})
        canvas.last_smiles_input = "keep-me"
        existing_label = _FakeGraphicsItem(selected=True)
        canvas.atom_items[1] = existing_label
        service = AtomLabelService(canvas)

        service.add_or_update_atom_label(1, "")

        self.assertEqual(canvas.model.atoms[1].element, "C")
        self.assertFalse(canvas.model.atoms[1].explicit_label)
        self.assertNotIn(1, canvas.atom_items)
        self.assertIn(1, canvas.atom_dots)
        self.assertEqual(canvas.redraw_calls, [1])
        self.assertIn(existing_label, canvas.scene_obj.removed_items)
        self.assertEqual(len(canvas.pushed_commands), 1)
        command = canvas.pushed_commands[0]
        self.assertIsInstance(command, ChangeAtomLabelCommand)
        self.assertEqual(command.atom_id, 1)
        self.assertFalse(command.after_explicit_label)

    def test_add_or_update_atom_label_creates_explicit_carbon_label_and_removes_dot(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0)})
        existing_dot = _FakeGraphicsItem()
        canvas.atom_dots[1] = existing_dot
        service = AtomLabelService(canvas)

        service.add_or_update_atom_label(1, "C", show_carbon=True, allow_merge=False, record=False)

        self.assertEqual(canvas.model.atoms[1].element, "C")
        self.assertTrue(canvas.model.atoms[1].explicit_label)
        self.assertNotIn(1, canvas.atom_dots)
        self.assertIn(existing_dot, canvas.scene_obj.removed_items)
        self.assertIn(1, canvas.atom_items)
        self.assertIsInstance(canvas.atom_items[1], AtomLabelItem)
        self.assertEqual(canvas.atom_items[1].toPlainText(), "C")
        self.assertEqual(canvas.pushed_commands, [])

    def test_add_or_update_atom_label_replaces_non_label_atom_item(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("N", 1.0, 2.0)})
        existing_item = _FakeGraphicsItem(selected=True)
        canvas.atom_items[1] = existing_item
        service = AtomLabelService(canvas)

        service.add_or_update_atom_label(1, "Cl", allow_merge=False, record=False)

        self.assertIsInstance(canvas.atom_items[1], AtomLabelItem)
        self.assertEqual(canvas.atom_items[1].toPlainText(), "Cl")
        self.assertIn(existing_item, canvas.scene_obj.removed_items)
        self.assertTrue(canvas.atom_items[1].isSelected())

    def test_add_or_update_atom_label_reuses_existing_atom_label_item(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("N", 1.0, 2.0)})
        canvas.last_smiles_input = "preserve"
        existing_item = AtomLabelItem(hit_padding=0.5, hit_radius=None)
        canvas.atom_items[1] = existing_item
        service = AtomLabelService(canvas)

        service.add_or_update_atom_label(1, "NH", clear_smiles=False, allow_merge=False, record=False)

        self.assertIs(canvas.atom_items[1], existing_item)
        self.assertEqual(existing_item.toPlainText(), "NH")
        self.assertEqual(existing_item.data(0), "atom")
        self.assertEqual(existing_item.data(1), 1)
        self.assertEqual(canvas.last_smiles_input, "preserve")
        self.assertEqual(canvas.scene_obj.removed_items, [])

    def test_add_or_update_atom_label_removes_non_carbon_label_without_dot_when_record_disabled(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("N", 1.0, 2.0, explicit_label=True)})
        existing_label = _FakeGraphicsItem()
        canvas.atom_items[1] = existing_label
        service = AtomLabelService(canvas)

        service.add_or_update_atom_label(1, "", record=False)

        self.assertNotIn(1, canvas.atom_items)
        self.assertNotIn(1, canvas.atom_dots)
        self.assertEqual(canvas.pushed_commands, [])
        self.assertIn(existing_label, canvas.scene_obj.removed_items)

    def test_add_or_update_atom_label_records_merge_context_for_history(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0)})
        canvas.last_smiles_input = "C=C"
        service = AtomLabelService(canvas)
        merge_info = {"bond_before_states": {3: {"a": 1, "b": 2}}, "deleted_bond_ids": [3]}
        service.merge_overlapping_atoms = Mock(return_value=([7], merge_info))

        service.add_or_update_atom_label(1, "N")

        self.assertEqual(canvas.model.atoms[1].element, "N")
        self.assertFalse(canvas.model.atoms[1].explicit_label)
        self.assertIsNone(canvas.last_smiles_input)
        self.assertEqual(canvas.atom_items[1].toPlainText(), "N")
        self.assertEqual(len(canvas.pushed_commands), 1)
        composite = canvas.pushed_commands[0]
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(
            [type(command) for command in composite.commands],
            [ChangeAtomLabelCommand, DeleteBondCommand],
        )
        service.merge_overlapping_atoms.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
