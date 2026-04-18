import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.model import Atom, Bond, MoleculeModel
from ui.insert_commit_service import (
    InsertCommitService,
    apply_smiles_commit_plan,
    apply_template_commit_resolution,
)
from ui.smiles_insert_logic import SmilesAtomPlacement, SmilesBondPlacement, SmilesCommitPlan
from ui.template_insert_logic import TemplateInsertPlan, TemplateInsertRequest, TemplateInsertResolution


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        self.last_smiles_input = "before"
        self.record_calls: list[dict] = []
        self.add_atom_calls: list[tuple[str, float, float]] = []
        self.add_bond_calls: list[tuple[int, int, int]] = []
        self.added_graphics: list[int] = []
        self.labels: list[tuple[int, str, bool, bool]] = []
        self.carbon_dots: list[int] = []
        self.ring_calls: list[list[tuple[float, float]]] = []
        self.benzene_calls: list[tuple[float, float, int | None]] = []

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.add_atom_calls.append((element, x, y))
        return self.model.add_atom(element, x, y)

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        self.add_bond_calls.append((a, b, order))
        self.model.add_bond(a, b, order)
        return len(self.model.bonds) - 1

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.added_graphics.append(bond_id)

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        self.carbon_dots.append(atom_id)

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
        self.labels.append((atom_id, text, clear_smiles, record))

    def _record_additions(self, **kwargs) -> None:
        self.record_calls.append(kwargs)

    def _bond_exists(self, a_id: int, b_id: int) -> bool:
        return any(
            (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id)
            for bond in self.model.bonds
        )

    def _add_atom_with_merge(self, point, element: str, merge: list) -> int:
        self.ring_calls.append(list(merge))
        return self.add_atom(element, point.x(), point.y())

    def _add_ring_from_points(self, points, elements=None, merge=None):
        self.ring_calls.append([tuple(entry) for entry in (merge or [])])
        atom_ids = []
        for point in points:
            atom_ids.append(self.add_atom("C", point.x(), point.y()))
        for index in range(len(atom_ids)):
            self.add_bond(atom_ids[index], atom_ids[(index + 1) % len(atom_ids)])
        for bond_id in range(len(self.model.bonds) - len(atom_ids), len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        return atom_ids

    def _benzene_ring_points(self, center, attach_atom_id=None, attach_bond_id=None):
        self.benzene_calls.append((center.x(), center.y(), attach_bond_id))
        return [(center.x() + 1.0, center.y() + 1.0)] * 6, []

    def add_benzene_ring(self, center, attach_atom_id=None, attach_bond_id=None, before_smiles_input=None):
        self.last_smiles_input = None
        points = [(center.x() + 1.0, center.y() + 1.0)] * 6
        atom_ids = []
        for point_x, point_y in points:
            atom_ids.append(self.add_atom("C", point_x, point_y))
        for index in range(len(atom_ids)):
            self.add_bond(atom_ids[index], atom_ids[(index + 1) % len(atom_ids)])
        for bond_id in range(len(self.model.bonds) - len(atom_ids), len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        self._record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input=before_smiles_input,
            added_scene_items=[],
        )


class InsertCommitServiceTest(unittest.TestCase):
    def test_apply_smiles_commit_plan_builds_atoms_bonds_and_history(self) -> None:
        canvas = _FakeCanvas()
        plan = SmilesCommitPlan(
            offset=(1.0, 1.0),
            atoms=[
                SmilesAtomPlacement(0, "C", 10.0, 20.0, "#111111", False),
                SmilesAtomPlacement(1, "N", 30.0, 40.0, "#222222", True),
            ],
            bonds=[
                SmilesBondPlacement(0, 0, 1, 2, "double", "#333333"),
            ],
        )

        applied = apply_smiles_commit_plan(
            canvas,
            plan,
            before_smiles_input="old",
            after_smiles_input="new",
        )

        self.assertTrue(applied)
        self.assertEqual(canvas.add_atom_calls, [("C", 10.0, 20.0), ("N", 30.0, 40.0)])
        self.assertEqual(canvas.add_bond_calls, [(0, 1, 2)])
        self.assertEqual(canvas.added_graphics, [0])
        self.assertEqual(canvas.carbon_dots, [0])
        self.assertEqual(canvas.labels, [(1, "N", False, False)])
        self.assertEqual(canvas.last_smiles_input, "new")
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "old",
                }
            ],
        )

    def test_apply_template_commit_resolution_handles_free_and_bond_paths(self) -> None:
        free_canvas = _FakeCanvas()
        free_request = TemplateInsertRequest(ring_size=6, cursor_pos=(5.0, 6.0), ring_style="regular")
        free_plan = TemplateInsertPlan(
            generator="free_regular_ring",
            ring_size=6,
            ring_style="regular",
            bond_id=None,
            radius_mode="regular_polygon",
        )
        free_resolution = TemplateInsertResolution(plan=free_plan, points=[(1.0, 2.0), (3.0, 4.0)])

        applied = apply_template_commit_resolution(
            free_canvas,
            free_request,
            free_plan,
            free_resolution,
            before_smiles_input="before-free",
            after_smiles_input=None,
        )

        self.assertTrue(applied)
        self.assertEqual(free_canvas.add_atom_calls, [("C", 1.0, 2.0), ("C", 3.0, 4.0)])
        self.assertEqual(free_canvas.add_bond_calls, [(0, 1, 1), (1, 0, 1)])
        self.assertEqual(free_canvas.record_calls[0]["before_smiles_input"], "before-free")
        self.assertIsNone(free_canvas.last_smiles_input)

        bond_canvas = _FakeCanvas()
        bond_canvas.model.atoms = {
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 10.0, 0.0),
        }
        bond_canvas.model.bonds = [Bond(0, 1, 1)]
        bond_canvas.model.next_atom_id = 2
        bond_request = TemplateInsertRequest(ring_size=6, cursor_pos=(8.0, 9.0), bond_id=0, ring_style="chair")
        bond_plan = TemplateInsertPlan(
            generator="bond_template_shape",
            ring_size=6,
            ring_style="chair",
            bond_id=0,
            template_shape="chair",
        )
        bond_resolution = TemplateInsertResolution(
            plan=bond_plan,
            points=[(11.0, 12.0), (13.0, 14.0), (15.0, 16.0)],
        )

        applied = apply_template_commit_resolution(
            bond_canvas,
            bond_request,
            bond_plan,
            bond_resolution,
            before_smiles_input="before-bond",
        )

        self.assertTrue(applied)
        self.assertEqual(bond_canvas.ring_calls[-1][:2], [(0, 0.0, 0.0), (1, 10.0, 0.0)])
        self.assertEqual(bond_canvas.record_calls[0]["before_smiles_input"], "before-bond")

    def test_apply_template_commit_resolution_uses_benzene_path_and_rejects_invalid_points(self) -> None:
        canvas = _FakeCanvas()
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(7.0, 8.0), bond_id=3, ring_style="benzene")
        plan = TemplateInsertPlan(
            generator="benzene",
            ring_size=6,
            ring_style="benzene",
            bond_id=3,
        )

        applied = apply_template_commit_resolution(
            canvas,
            request,
            plan,
            None,
            before_smiles_input="before-benzene",
        )

        self.assertTrue(applied)
        self.assertEqual(canvas.add_atom_calls, [("C", 8.0, 9.0)] * 6)
        self.assertEqual(len(canvas.add_bond_calls), 6)
        self.assertIsNone(canvas.last_smiles_input)

        blocked = _FakeCanvas()
        blocked.add_benzene_ring = lambda *args, **kwargs: None
        self.assertFalse(
            apply_template_commit_resolution(
                blocked,
                request,
                plan,
                None,
                before_smiles_input="before-benzene",
            )
        )

    def test_apply_smiles_commit_plan_prefers_atom_label_service_over_canvas_wrapper(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas._atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: service_calls.append((atom_id, text, kwargs))
        )
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[
                SmilesAtomPlacement(0, "C", 0.0, 0.0, "#111111", True),
                SmilesAtomPlacement(1, "Cl", 10.0, 0.0, "#222222", False),
            ],
            bonds=[],
        )

        applied = apply_smiles_commit_plan(
            canvas,
            plan,
            before_smiles_input="before",
            after_smiles_input="after",
        )

        self.assertTrue(applied)
        self.assertEqual(
            service_calls,
            [
                (0, "C", {"clear_smiles": False, "record": False, "allow_merge": True, "show_carbon": False}),
                (1, "Cl", {"clear_smiles": False, "record": False, "allow_merge": True, "show_carbon": False}),
            ],
        )
        self.assertEqual(canvas.labels, [])

    def test_service_wrapper_delegates_to_module_functions(self) -> None:
        canvas = _FakeCanvas()
        service = InsertCommitService(canvas)

        self.assertFalse(
            service.apply_smiles_commit_plan(None, before_smiles_input="before", after_smiles_input="after")
        )


if __name__ == "__main__":
    unittest.main()
