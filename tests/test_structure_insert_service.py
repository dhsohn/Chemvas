import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from core.model import Atom, Bond, MoleculeModel
from PyQt6.QtCore import QPointF
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
)
from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
from ui.canvas_smiles_input_state import set_last_smiles_input_for
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


class _SelectableItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self.kind = kind
        self.item_id = item_id
        self.selected = False

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None

    def setSelected(self, selected: bool) -> None:
        self.selected = bool(selected)

    def isSelected(self) -> bool:
        return self.selected


class _FakeScene:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.clear_selection_calls = 0

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in list(self.canvas.atom_items.values()) + list(self.canvas.atom_dots.values()):
            item.setSelected(False)
        for items in self.canvas.bond_items.values():
            for item in items:
                item.setSelected(False)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        set_last_smiles_input_for(self, "before")
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self._viewport_center = QPointF(60.0, 40.0)

        self._record_additions = Mock()
        set_atom_items_for(self, {})
        set_atom_dots_for(self, {})
        set_bond_items_for(self, {})
        self._scene = _FakeScene(self)

        self.add_bond_graphics_calls: list[int] = []
        self.ensure_carbon_dot_calls: list[int] = []
        self.atom_label_calls: list[tuple[int, str, bool, bool]] = []
        self.add_text_note_calls: list[tuple[QPointF, str]] = []
        self.services = SimpleNamespace(
            canvas_history_recording_service=SimpleNamespace(record_additions=self._record_additions),
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                ensure_carbon_dot=self.ensure_carbon_dot,
            ),
            note_controller=SimpleNamespace(create_text_note=self.add_text_note),
            canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
            canvas_bond_mutation_service=SimpleNamespace(add_bond=self.add_bond),
        )
        self.bond_renderer = SimpleNamespace(add_bond_graphics=self._add_bond_graphics)

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self._viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def scene(self) -> _FakeScene:
        return self._scene

    @property
    def atom_items(self):
        return atom_items_for(self)

    @atom_items.setter
    def atom_items(self, value) -> None:
        set_atom_items_for(self, value)

    @property
    def atom_dots(self):
        return atom_dots_for(self)

    @atom_dots.setter
    def atom_dots(self, value) -> None:
        set_atom_dots_for(self, value)

    @property
    def bond_items(self):
        return bond_items_for(self)

    @bond_items.setter
    def bond_items(self, value) -> None:
        set_bond_items_for(self, value)

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.model.add_atom(element, x, y)
        self.atom_items[atom_id] = _SelectableItem("atom", atom_id)
        return atom_id

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.add_bond_graphics_calls.append(bond_id)
        self.bond_items[bond_id] = [_SelectableItem("bond", bond_id)]

    def ensure_carbon_dot(self, atom_id: int) -> None:
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

    def selected_atom_ids(self) -> set[int]:
        return {
            atom_id
            for atom_id, item in {**self.atom_items, **self.atom_dots}.items()
            if item.isSelected()
        }

    def selected_bond_ids(self) -> set[int]:
        return {
            bond_id
            for bond_id, items in self.bond_items.items()
            if any(item.isSelected() for item in items)
        }


def _structure_insert_service(canvas: _FakeCanvas) -> StructureInsertService:
    return StructureInsertService(
        canvas,
        note_controller=canvas.services.note_controller,
    )


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
        service = _structure_insert_service(canvas)

        inserted_atom_ids, inserted_bond_ids = service.insert_structure_model(MoleculeModel())

        self.assertEqual(inserted_atom_ids, set())
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        canvas._record_additions.assert_not_called()
        self.assertEqual(canvas.selected_atom_ids(), set())
        self.assertEqual(canvas.selected_bond_ids(), set())

    def test_insert_structure_model_recenters_atoms_and_adds_bond_graphics(self) -> None:
        canvas = _FakeCanvas()
        existing_atom_id = canvas.model.add_atom("N", -20.0, -10.0)
        canvas.model.atoms[existing_atom_id].explicit_label = True
        canvas.model.add_bond(existing_atom_id, existing_atom_id, 1)
        service = _structure_insert_service(canvas)
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
        self.assertEqual(canvas.selected_atom_ids(), {1, 2})
        self.assertEqual(canvas.selected_bond_ids(), {1})

    def test_insert_structure_model_uses_carbon_dot_for_implicit_carbon_and_labels_explicit_atoms(self) -> None:
        canvas = _FakeCanvas()
        service = _structure_insert_service(canvas)
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
        set_last_smiles_input_for(canvas, "CCO")
        canvas.model.add_atom("H", 100.0, 100.0)
        service = _structure_insert_service(canvas)
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
        self.assertEqual(canvas.selected_atom_ids(), {1, 2})
        self.assertEqual(canvas.selected_bond_ids(), {0})

    def test_insert_structure_model_prefers_atom_label_service_over_canvas_wrapper(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas.services.atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )
        model = MoleculeModel(
            atoms={
                3: Atom("C", 0.0, 0.0, explicit_label=True),
                5: Atom("N", 10.0, 0.0, explicit_label=False),
            }
        )

        inserted_atom_ids, inserted_bond_ids = _structure_insert_service(canvas).insert_structure_model(
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

        inserted_atom_ids, inserted_bond_ids = _structure_insert_service(canvas).insert_structure_model(
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

        inserted_atom_ids, inserted_bond_ids = _structure_insert_service(canvas).insert_structure_model(
            model,
            center=QPointF(5.0, 0.0),
        )

        self.assertEqual(inserted_atom_ids, {0, 1})
        self.assertEqual(inserted_bond_ids, set())
        self.assertEqual(canvas.add_bond_graphics_calls, [])


if __name__ == "__main__":
    unittest.main()
