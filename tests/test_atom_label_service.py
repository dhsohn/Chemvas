import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
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

        self.scene_obj = _FakeScene()
        self.redraw_calls = []
        self.restore_calls = []
        self.record_calls = []
        self.rebuild_bond_adjacency_calls = 0

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

    def _atom_item_for_id(self, atom_id: int):
        return self.atom_items.get(atom_id) or self.atom_dots.get(atom_id)

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in self.atom_dots:
            return
        dot = _FakeGraphicsItem()
        self.atom_dots[atom_id] = dot
        self.scene_obj.addItem(dot)

    def _remove_carbon_dot(self, atom_id: int) -> None:
        dot = self.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.scene_obj.removeItem(dot)

    def _redraw_connected_bonds(self, atom_id: int) -> None:
        self.redraw_calls.append(atom_id)

    def _restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_atom_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        self.restore_calls.append(
            {
                "atom_id": atom_id,
                "previous_atom_item": previous_atom_item,
                "was_selected": was_selected,
                "refresh_hover": refresh_hover,
            }
        )

    def _record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        self.record_calls.append(
            (
                atom_id,
                before_element,
                before_explicit_label,
                before_smiles_input,
                merge_ids,
                merge_info,
            )
        )

    def _atom_pick_radius(self) -> float:
        return 4.0

    def _uses_compact_label_hit_shape(self, text: str) -> bool:
        return len(text.strip()) <= 2

    def _make_selectable(self, item) -> None:
        return None

    def _position_label(self, item, x: float, y: float) -> None:
        item.setPos(x, y)


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
        self.assertEqual(
            canvas.record_calls,
            [(1, "C", True, "keep-me", [], {})],
        )
        self.assertIn(existing_label, canvas.scene_obj.removed_items)
        self.assertTrue(canvas.restore_calls[0]["was_selected"])

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
        self.assertEqual(canvas.record_calls, [])

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
        self.assertTrue(canvas.restore_calls[0]["was_selected"])

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
        self.assertEqual(canvas.record_calls, [])
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
        self.assertEqual(
            canvas.record_calls,
            [(1, "C", False, "C=C", [7], merge_info)],
        )
        service.merge_overlapping_atoms.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
