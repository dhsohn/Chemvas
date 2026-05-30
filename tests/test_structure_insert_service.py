import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QPointF

from core.model import Atom, Bond, MoleculeModel
from ui.structure_insert_service import StructureInsertService


def _point_tuple(point: QPointF) -> tuple[float, float]:
    return (point.x(), point.y())


class _FakeRect:
    def __init__(self, center: QPointF) -> None:
        self._center = center

    def center(self) -> QPointF:
        return self._center


class _FakeViewport:
    def __init__(self, center: QPointF) -> None:
        self._center = center

    def rect(self) -> _FakeRect:
        return _FakeRect(self._center)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        self.last_smiles_input = "before"
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self._viewport_center = QPointF(60.0, 40.0)

        self._record_additions = Mock()
        self._restore_selection_from_ids = Mock()

        self.add_bond_graphics_calls: list[int] = []
        self.ensure_carbon_dot_calls: list[int] = []
        self.atom_label_calls: list[tuple[int, str, bool, bool]] = []
        self.add_text_note_calls: list[tuple[QPointF, str]] = []
        self._atom_label_service = SimpleNamespace(add_or_update_atom_label=self.add_or_update_atom_label)

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self._viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def add_atom(self, element: str, x: float, y: float) -> int:
        return self.model.add_atom(element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.add_bond_graphics_calls.append(bond_id)

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        self.ensure_carbon_dot_calls.append(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        *,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        self.atom_label_calls.append((atom_id, text, clear_smiles, record))

    def add_text_note(self, pos: QPointF, text: str):
        self.add_text_note_calls.append((QPointF(pos.x(), pos.y()), text))
        return {"kind": "note", "text": text, "pos": _point_tuple(pos)}


class _EphemeralBondList(list):
    def __init__(self, items=(), *, none_after_first_read: set[int] | None = None) -> None:
        super().__init__(items)
        self._none_after_first_read = set(none_after_first_read or ())
        self._reads: dict[int, int] = {}

    def __getitem__(self, index):
        if isinstance(index, slice):
            return super().__getitem__(index)
        value = super().__getitem__(index)
        self._reads[index] = self._reads.get(index, 0) + 1
        if index in self._none_after_first_read and self._reads[index] > 1:
            return None
        return value


class StructureInsertServiceTest(unittest.TestCase):
    def test_insert_structure_model_is_no_op_for_empty_model(self) -> None:
        canvas = _FakeCanvas()
        service = StructureInsertService(canvas)

        inserted_atom_ids, inserted_bond_ids = service.insert_structure_model(MoleculeModel())

        self.assertEqual(inserted_atom_ids, set())
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        canvas._record_additions.assert_not_called()
        canvas._restore_selection_from_ids.assert_not_called()

    def test_insert_structure_model_recenters_atoms_and_adds_bond_graphics(self) -> None:
        canvas = _FakeCanvas()
        existing_atom_id = canvas.model.add_atom("N", -20.0, -10.0)
        canvas.model.atoms[existing_atom_id].explicit_label = True
        canvas.model.add_bond(existing_atom_id, existing_atom_id, 1)
        service = StructureInsertService(canvas)
        model = MoleculeModel(
            atoms={
                5: Atom("C", 10.0, 10.0, color="#112233", explicit_label=False),
                9: Atom("O", 14.0, 10.0, color="#445566", explicit_label=True),
            },
            bonds=[Bond(5, 9, order=2, style="double", color="#778899")],
        )

        inserted_atom_ids, inserted_bond_ids = service.insert_structure_model(
            model,
            center=QPointF(40.0, 30.0),
        )

        self.assertEqual(inserted_atom_ids, {1, 2})
        self.assertEqual(inserted_bond_ids, {1})
        self.assertEqual((canvas.model.atoms[1].x, canvas.model.atoms[1].y), (38.0, 30.0))
        self.assertEqual((canvas.model.atoms[2].x, canvas.model.atoms[2].y), (42.0, 30.0))
        self.assertEqual(canvas.model.atoms[1].color, "#112233")
        self.assertFalse(canvas.model.atoms[1].explicit_label)
        self.assertEqual(canvas.model.atoms[2].color, "#445566")
        self.assertTrue(canvas.model.atoms[2].explicit_label)
        self.assertEqual(len(canvas.model.bonds), 2)
        self.assertEqual(canvas.model.bonds[1].order, 2)
        self.assertEqual(canvas.model.bonds[1].style, "double")
        self.assertEqual(canvas.model.bonds[1].color, "#778899")
        self.assertEqual(canvas.add_bond_graphics_calls, [1])
        self.assertEqual(canvas.ensure_carbon_dot_calls, [1])
        self.assertEqual(canvas.atom_label_calls, [(2, "O", False, False)])
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before",
            added_scene_items=[],
        )
        canvas._restore_selection_from_ids.assert_called_once_with({1, 2}, {1})

    def test_insert_structure_model_uses_carbon_dot_for_implicit_carbon_and_labels_explicit_atoms(self) -> None:
        canvas = _FakeCanvas()
        service = StructureInsertService(canvas)
        model = MoleculeModel(
            atoms={
                10: Atom("C", 0.0, 0.0, explicit_label=False),
                20: Atom("C", 8.0, 0.0, explicit_label=True),
                30: Atom("Cl", 16.0, 0.0, explicit_label=False),
            }
        )

        inserted_atom_ids, inserted_bond_ids = service.insert_structure_model(
            model,
            center=QPointF(8.0, 0.0),
        )

        self.assertEqual(inserted_atom_ids, {0, 1, 2})
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(canvas.ensure_carbon_dot_calls, [0])
        self.assertEqual(
            canvas.atom_label_calls,
            [
                (1, "C", False, False),
                (2, "Cl", False, False),
            ],
        )
        self.assertFalse(canvas.model.atoms[0].explicit_label)
        self.assertTrue(canvas.model.atoms[1].explicit_label)
        self.assertFalse(canvas.model.atoms[2].explicit_label)

    def test_insert_structure_model_adds_title_note_and_restores_selection_history(self) -> None:
        canvas = _FakeCanvas()
        canvas.last_smiles_input = "CCO"
        canvas.model.add_atom("H", 100.0, 100.0)
        service = StructureInsertService(canvas)
        model = MoleculeModel(
            atoms={
                2: Atom("C", 0.0, 0.0, explicit_label=False),
                4: Atom("N", 10.0, 0.0, explicit_label=True),
            },
            bonds=[Bond(2, 4, order=1, style="single", color="#0000ff")],
        )

        inserted_atom_ids, inserted_bond_ids = service.insert_structure_model(
            model,
            center=None,
            title="Inserted fragment",
        )

        self.assertEqual(inserted_atom_ids, {1, 2})
        self.assertEqual(inserted_bond_ids, {0})
        self.assertEqual(len(canvas.add_text_note_calls), 1)
        note_pos, note_text = canvas.add_text_note_calls[0]
        self.assertEqual(note_text, "Inserted fragment")
        self.assertEqual(_point_tuple(note_pos), (55.0, 12.0))
        canvas._record_additions.assert_called_once()
        self.assertEqual(
            canvas._record_additions.call_args.kwargs,
            {
                "before_next_atom_id": 1,
                "before_bond_count": 0,
                "before_smiles_input": "CCO",
                "added_scene_items": [{"kind": "note", "text": "Inserted fragment", "pos": (55.0, 12.0)}],
            },
        )
        canvas._restore_selection_from_ids.assert_called_once_with({1, 2}, {0})

    def test_insert_structure_model_prefers_atom_label_service_over_canvas_wrapper(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas._atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )
        model = MoleculeModel(
            atoms={
                3: Atom("C", 0.0, 0.0, explicit_label=True),
                5: Atom("N", 10.0, 0.0, explicit_label=False),
            }
        )

        inserted_atom_ids, inserted_bond_ids = StructureInsertService(canvas).insert_structure_model(
            model,
            center=QPointF(5.0, 0.0),
        )

        self.assertEqual(inserted_atom_ids, {0, 1})
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(
            service_calls,
            [
                (0, "C", {"clear_smiles": False, "record": False, "allow_merge": True, "show_carbon": False}),
                (1, "N", {"clear_smiles": False, "record": False, "allow_merge": True, "show_carbon": False}),
            ],
        )
        self.assertEqual(canvas.atom_label_calls, [])

    def test_insert_structure_model_skips_none_and_unmapped_source_bonds(self) -> None:
        canvas = _FakeCanvas()
        model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0, explicit_label=False),
                2: Atom("O", 8.0, 0.0, explicit_label=True),
            },
            bonds=[
                None,
                Bond(1, 99, order=1, style="single", color="#111111"),
                Bond(1, 2, order=2, style="double", color="#222222"),
            ],
        )

        inserted_atom_ids, inserted_bond_ids = StructureInsertService(canvas).insert_structure_model(
            model,
            center=QPointF(4.0, 0.0),
        )

        self.assertEqual(inserted_atom_ids, {0, 1})
        self.assertEqual(inserted_bond_ids, {0})
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(canvas.add_bond_graphics_calls, [0])

    def test_insert_structure_model_skips_graphics_for_sparse_new_bond_slots(self) -> None:
        canvas = _FakeCanvas()
        canvas.model.bonds = _EphemeralBondList(canvas.model.bonds, none_after_first_read={0})
        model = MoleculeModel(
            atoms={
                4: Atom("C", 0.0, 0.0, explicit_label=False),
                8: Atom("C", 10.0, 0.0, explicit_label=False),
            },
            bonds=[Bond(4, 8, order=1, style="single", color="#333333")],
        )

        inserted_atom_ids, inserted_bond_ids = StructureInsertService(canvas).insert_structure_model(
            model,
            center=QPointF(5.0, 0.0),
        )

        self.assertEqual(inserted_atom_ids, {0, 1})
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(canvas.add_bond_graphics_calls, [])


if __name__ == "__main__":
    unittest.main()
