import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QPointF


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.history import AddAtomsCommand, AddBondCommand, CompositeCommand, DeleteAtomsCommand, DeleteBondCommand, DeleteSceneItemsCommand
from core.model import Atom, Bond, MoleculeModel
from ui.insert_controller import InsertController
from ui.template_insert_logic import TemplateInsertRequest, TemplateInsertResolution, plan_template_commit


def _point_tuples(points) -> list[tuple[float, float]]:
    return [(point.x(), point.y()) for point in points]


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


class _FakeSceneItem:
    def __init__(self, kind: str, atom_id=None) -> None:
        self.kind = kind
        self._payload = {}
        if atom_id is not None:
            self._payload["atom_id"] = atom_id

    def data(self, role: int):
        if role != 1:
            return None
        return dict(self._payload)


class _FakeCanvas:
    def __init__(self) -> None:
        self.rdkit = SimpleNamespace(
            smiles_to_2d=Mock(return_value=None),
            last_error=None,
        )
        self.renderer = SimpleNamespace(
            style=SimpleNamespace(
                bond_length_px=20.0,
                bond_line_width=1.0,
            ),
            bond_pen=Mock(return_value="pen"),
        )
        self.model = MoleculeModel()
        self.last_smiles_input = None

        self._template_insert_active = False
        self._template_ring_size = None
        self._template_ring_style = None
        self._template_preview_items = []
        self._template_preview_lines = []
        self._template_preview_dots = []

        self._smiles_insert_active = False
        self._smiles_preview_smiles = None
        self._smiles_preview_center = None
        self._smiles_preview_model = None
        self._smiles_preview_items = []
        self._smiles_preview_bond_items = {}
        self._smiles_preview_atom_items = {}

        self._marks_by_atom = {}
        self.ring_items = []
        self.note_items = []
        self.arrow_items = []
        self.ts_bracket_items = []
        self.orbital_items = []
        self.mark_items = []
        self._scene = object()
        self._viewport_center = QPointF(60.0, 40.0)

        self.clear_scene = Mock()
        self._push_command = Mock()
        self._rebuild_bond_adjacency = Mock()
        self._render_model = Mock()
        self._record_additions = Mock()
        self._add_ring_from_points = Mock()
        self._add_bond_graphics = Mock()
        self.add_benzene_ring = Mock()
        self._clear_benzene_preview = Mock()
        self._regular_ring_radius = Mock(return_value=12.0)
        self._ring_points = Mock(return_value=[])
        self._regular_ring_points_for_bond = Mock(return_value=None)
        self._cyclohexane_chair_points = Mock(return_value=[])
        self._cyclohexane_boat_points = Mock(return_value=[])
        self._template_points_for_bond = Mock(return_value=None)

        self._atom_state_dict = Mock(side_effect=lambda atom_id: {"atom_id": atom_id})
        self._bond_state_dict = Mock(side_effect=lambda bond: {"bond": (bond.a, bond.b, bond.order)})
        self._mark_state_dict = Mock(return_value={"kind": "mark"})
        self.scene_item_state = Mock(side_effect=lambda item: {"kind": getattr(item, "kind", "item")})
        self._add_atom_with_merge = Mock()
        self._bond_exists = Mock(return_value=False)
        self._find_bond_near = Mock(return_value=None)
        self._parallel_bond_segments = Mock(side_effect=lambda x1, y1, x2, y2, order: ((x1, y1, x2, y2),) * max(0, order))

        self.add_bond_calls: list[tuple[int, int, int]] = []
        self.add_atom_calls: list[tuple[str, float, float]] = []
        self.ensure_carbon_dot_calls: list[int] = []
        self.atom_label_calls: list[tuple[int, str, bool, bool, bool]] = []

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self._viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def scene(self):
        return self._scene

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.add_atom_calls.append((element, x, y))
        return self.model.add_atom(element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.add_bond_calls.append((a_id, b_id, order))
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

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
        self.atom_label_calls.append((atom_id, text, clear_smiles, record, show_carbon))
        self.model.atoms[atom_id].element = text
        self.model.atoms[atom_id].explicit_label = show_carbon


class InsertControllerTest(unittest.TestCase):
    def test_insert_session_state_and_apply_insert_session_state_track_and_clear_modes(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        canvas._template_ring_size = 6
        canvas._template_ring_style = "benzene"
        canvas._smiles_insert_active = True
        canvas._smiles_preview_smiles = "CC"
        canvas._smiles_preview_center = QPointF(12.0, 34.0)
        controller = InsertController(canvas)

        state = controller._insert_session_state()

        self.assertTrue(state.template_active)
        self.assertEqual(state.template_ring_size, 6)
        self.assertEqual(state.template_ring_style, "benzene")
        self.assertTrue(state.smiles_active)
        self.assertEqual(state.smiles_text, "CC")
        self.assertEqual(state.smiles_center, (12.0, 34.0))

        controller._clear_template_preview = Mock()
        controller._clear_smiles_preview = Mock()
        controller._apply_insert_session_state(
            state.__class__(
                template_active=False,
                template_ring_size=None,
                template_ring_style=None,
                smiles_active=False,
                smiles_text=None,
                smiles_center=None,
            )
        )

        self.assertFalse(canvas._template_insert_active)
        self.assertFalse(canvas._smiles_insert_active)
        self.assertIsNone(canvas._smiles_preview_center)
        controller._clear_template_preview.assert_called_once_with()
        controller._clear_smiles_preview.assert_called_once_with()

    def test_load_smiles_blank_is_no_op(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)

        controller.load_smiles("   ")

        canvas.rdkit.smiles_to_2d.assert_not_called()
        canvas.clear_scene.assert_not_called()
        canvas._push_command.assert_not_called()

    def test_load_smiles_warns_when_rdkit_conversion_fails(self) -> None:
        canvas = _FakeCanvas()
        canvas.last_smiles_input = "C"
        canvas.rdkit.last_error = "bad smiles"
        controller = InsertController(canvas)

        with patch("ui.insert_controller.QMessageBox.warning") as warning:
            controller.load_smiles("broken")

        warning.assert_called_once_with(canvas, "SMILES Error", "bad smiles")
        canvas.clear_scene.assert_not_called()
        canvas._push_command.assert_not_called()
        self.assertEqual(canvas.last_smiles_input, "C")

    def test_load_smiles_replaces_scene_and_pushes_history_command(self) -> None:
        canvas = _FakeCanvas()
        canvas.last_smiles_input = "before"
        canvas.model.add_atom("N", -5.0, -5.0)
        canvas.model.add_bond(0, 0, 1)
        bound_mark = _FakeSceneItem("bound-mark", atom_id=0)
        free_mark = _FakeSceneItem("free-mark")
        note = _FakeSceneItem("note")
        canvas._marks_by_atom = {0: [bound_mark]}
        canvas.mark_items = [bound_mark, free_mark]
        canvas.note_items = [note]
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
            atoms={0: Atom("C", 1.0, 2.0)},
            bonds=[Bond(0, 0, 1)],
        )

        def _clear_scene() -> None:
            canvas.model = MoleculeModel()

        canvas.clear_scene = Mock(side_effect=_clear_scene)
        controller = InsertController(canvas)

        controller.load_smiles(" C ")

        canvas.clear_scene.assert_called_once_with()
        canvas._rebuild_bond_adjacency.assert_called_once_with()
        canvas._render_model.assert_called_once_with()
        self.assertEqual(canvas.last_smiles_input, "C")
        command = canvas._push_command.call_args.args[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(
            [type(child) for child in command.commands],
            [DeleteBondCommand, DeleteAtomsCommand, DeleteSceneItemsCommand, AddAtomsCommand, AddBondCommand],
        )
        delete_bond = command.commands[0]
        delete_atoms = command.commands[1]
        delete_scene_items = command.commands[2]
        add_atoms = command.commands[3]
        add_bond = command.commands[4]
        self.assertEqual(delete_bond.before_smiles_input, "before")
        self.assertEqual(delete_bond.after_smiles_input, "C")
        self.assertEqual(delete_atoms.before_next_atom_id, 1)
        self.assertEqual(delete_atoms.after_next_atom_id, 0)
        self.assertEqual(delete_atoms.mark_states, [{"kind": "mark"}])
        self.assertEqual(delete_scene_items.item_states, [{"kind": "free-mark"}, {"kind": "note"}])
        self.assertEqual(add_atoms.before_next_atom_id, 0)
        self.assertEqual(add_atoms.after_next_atom_id, 1)
        self.assertEqual(add_bond.previous_bond_count, 0)

    def test_load_smiles_skips_push_when_history_builder_returns_none(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(atoms={0: Atom("C", 1.0, 2.0)})

        def _clear_scene() -> None:
            canvas.model = MoleculeModel()

        canvas.clear_scene = Mock(side_effect=_clear_scene)
        controller = InsertController(canvas)
        controller._smiles_load_transaction_builder.capture = Mock(return_value="snapshot")
        controller._smiles_load_transaction_builder.build_command = Mock(return_value=None)

        controller.load_smiles("C")

        controller._smiles_load_transaction_builder.capture.assert_called_once_with()
        controller._smiles_load_transaction_builder.build_command.assert_called_once_with(
            "snapshot",
            after_clear_next_atom_id=0,
            after_smiles_input="C",
        )
        canvas._push_command.assert_not_called()

    def test_begin_ring_template_insert_noops_for_invalid_request(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)
        controller._render_template_preview = Mock()
        controller._cancel_smiles_insert = Mock()

        controller.begin_ring_template_insert(2)

        self.assertFalse(canvas._template_insert_active)
        canvas._clear_benzene_preview.assert_not_called()
        controller._cancel_smiles_insert.assert_not_called()
        controller._render_template_preview.assert_not_called()

    def test_begin_ring_template_insert_cancels_smiles_and_renders_preview(self) -> None:
        canvas = _FakeCanvas()
        canvas._smiles_insert_active = True
        controller = InsertController(canvas)
        controller._cancel_smiles_insert = Mock()
        controller._render_template_preview = Mock()

        controller.begin_ring_template_insert(6, "benzene")

        controller._cancel_smiles_insert.assert_called_once_with()
        canvas._clear_benzene_preview.assert_called_once_with()
        self.assertTrue(canvas._template_insert_active)
        self.assertEqual(canvas._template_ring_size, 6)
        self.assertEqual(canvas._template_ring_style, "benzene")
        preview_pos = controller._render_template_preview.call_args.args[0]
        self.assertEqual((preview_pos.x(), preview_pos.y()), (60.0, 40.0))

    def test_begin_smiles_insert_blank_is_noop(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)
        controller._render_smiles_preview = Mock()

        controller.begin_smiles_insert("   ")

        canvas.rdkit.smiles_to_2d.assert_not_called()
        controller._render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_warns_when_rdkit_conversion_fails(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.last_error = "bad smiles"
        controller = InsertController(canvas)

        with patch("ui.insert_controller.QMessageBox.warning") as warning:
            controller.begin_smiles_insert("broken")

        warning.assert_called_once_with(canvas, "SMILES Error", "bad smiles")
        self.assertIsNone(canvas._smiles_preview_model)

    def test_begin_smiles_insert_clears_model_when_preview_center_is_missing(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel()
        controller = InsertController(canvas)
        controller._render_smiles_preview = Mock()

        controller.begin_smiles_insert("CC")

        self.assertIsNone(canvas._smiles_preview_model)
        controller._render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_clears_model_when_state_helper_returns_none(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        controller = InsertController(canvas)
        controller._render_smiles_preview = Mock()

        with patch("ui.insert_controller.begin_smiles_insert_state", return_value=None):
            controller.begin_smiles_insert("CC")

        self.assertIsNone(canvas._smiles_preview_model)
        controller._render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_cancels_template_and_renders_preview(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("O", 10.0, 0.0),
            }
        )
        controller = InsertController(canvas)
        controller._cancel_template_insert = Mock()
        controller._render_smiles_preview = Mock()

        controller.begin_smiles_insert(" CO ")

        controller._cancel_template_insert.assert_called_once_with()
        canvas._clear_benzene_preview.assert_called_once_with()
        self.assertTrue(canvas._smiles_insert_active)
        self.assertEqual(canvas._smiles_preview_smiles, "CO")
        self.assertEqual((canvas._smiles_preview_center.x(), canvas._smiles_preview_center.y()), (5.0, 0.0))
        preview_pos = controller._render_smiles_preview.call_args.args[0]
        self.assertEqual((preview_pos.x(), preview_pos.y()), (60.0, 40.0))

    def test_commit_smiles_insert_cancels_when_preview_center_is_missing(self) -> None:
        canvas = _FakeCanvas()
        canvas._smiles_insert_active = True
        canvas._smiles_preview_smiles = "CC"
        canvas._smiles_preview_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        controller = InsertController(canvas)
        controller._clear_smiles_preview = Mock()

        controller._commit_smiles_insert(QPointF(40.0, 20.0))

        self.assertFalse(canvas._smiles_insert_active)
        self.assertIsNone(canvas._smiles_preview_model)
        self.assertIsNone(canvas._smiles_preview_smiles)
        self.assertIsNone(canvas._smiles_preview_center)
        controller._clear_smiles_preview.assert_called_once_with()
        canvas._record_additions.assert_not_called()

    def test_commit_smiles_insert_adds_atoms_bonds_labels_and_history(self) -> None:
        canvas = _FakeCanvas()
        canvas.last_smiles_input = "before"
        canvas.model.add_atom("N", -5.0, -5.0)
        canvas.model.add_bond(0, 0, 1)
        canvas._smiles_preview_smiles = "CO"
        canvas._smiles_preview_center = QPointF(5.0, 0.0)
        canvas._smiles_preview_model = MoleculeModel(
            atoms={
                3: Atom("C", 0.0, 0.0, color="#111111", explicit_label=False),
                7: Atom("O", 10.0, 0.0, color="#222222", explicit_label=True),
            },
            bonds=[Bond(3, 7, 2, style="double", color="#333333")],
        )
        controller = InsertController(canvas)
        controller._cancel_smiles_insert = Mock()

        controller._commit_smiles_insert(QPointF(40.0, 20.0))

        self.assertEqual(canvas.add_atom_calls, [("C", 35.0, 20.0), ("O", 45.0, 20.0)])
        self.assertEqual(canvas.model.atoms[1].color, "#111111")
        self.assertFalse(canvas.model.atoms[1].explicit_label)
        self.assertEqual(canvas.model.atoms[2].color, "#222222")
        self.assertFalse(canvas.model.atoms[2].explicit_label)
        self.assertEqual(canvas.add_bond_calls, [(1, 2, 2)])
        self.assertEqual(canvas.model.bonds[1].style, "double")
        self.assertEqual(canvas.model.bonds[1].color, "#333333")
        self.assertEqual(canvas.ensure_carbon_dot_calls, [1])
        self.assertEqual(canvas.atom_label_calls, [(2, "O", False, False, False)])
        self.assertEqual([call.args[0] for call in canvas._add_bond_graphics.call_args_list], [1])
        self.assertEqual(canvas.last_smiles_input, "CO")
        controller._cancel_smiles_insert.assert_called_once_with()
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before",
        )

    def test_clear_smiles_preview_uses_helper_results(self) -> None:
        canvas = _FakeCanvas()
        canvas._smiles_preview_items = ["old"]
        controller = InsertController(canvas)

        with patch(
            "ui.insert_controller.clear_smiles_preview_helper",
            return_value=(["new-items"], {"bond": ["segments"]}, {1: "atom"}),
        ) as helper:
            controller._clear_smiles_preview()

        helper.assert_called_once_with(canvas.scene(), ["old"])
        self.assertEqual(canvas._smiles_preview_items, ["new-items"])
        self.assertEqual(canvas._smiles_preview_bond_items, {"bond": ["segments"]})
        self.assertEqual(canvas._smiles_preview_atom_items, {1: "atom"})

    def test_render_smiles_preview_clears_on_clear_plan(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)
        controller._clear_smiles_preview = Mock()

        with patch(
            "ui.insert_controller.plan_smiles_preview_update",
            return_value=SimpleNamespace(action="clear", geometry=None),
        ):
            controller._render_smiles_preview(QPointF(10.0, 20.0))

        controller._clear_smiles_preview.assert_called_once_with()

    def test_render_smiles_preview_applies_geometry(self) -> None:
        canvas = _FakeCanvas()
        canvas._smiles_preview_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        canvas._smiles_preview_center = QPointF(0.0, 0.0)
        canvas._smiles_preview_items = ["old"]
        canvas._smiles_preview_bond_items = {0: ["bond"]}
        canvas._smiles_preview_atom_items = {0: "atom"}
        controller = InsertController(canvas)

        with patch(
            "ui.insert_controller.plan_smiles_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"lines": 1}),
        ) as plan_update, patch(
            "ui.insert_controller.apply_smiles_preview_geometry_helper",
            return_value=(["items"], {0: ["new-bond"]}, {0: "new-atom"}),
        ) as apply_helper:
            controller._render_smiles_preview(QPointF(12.0, 18.0))

        self.assertEqual(plan_update.call_args.args[2], (12.0, 18.0))
        apply_helper.assert_called_once()
        self.assertEqual(canvas._smiles_preview_items, ["items"])
        self.assertEqual(canvas._smiles_preview_bond_items, {0: ["new-bond"]})
        self.assertEqual(canvas._smiles_preview_atom_items, {0: "new-atom"})

    def test_commit_template_insert_uses_free_ring_path_for_unattached_templates(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        canvas._template_ring_size = 5
        canvas._template_ring_style = "regular"
        canvas.last_smiles_input = "before"
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()

        request = TemplateInsertRequest(ring_size=5, cursor_pos=(12.0, 18.0), ring_style="regular")
        plan = plan_template_commit(request)
        assert plan is not None
        resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])

        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.resolve_template_insert",
            return_value=resolution,
        ):
            controller._commit_template_insert(QPointF(*request.cursor_pos))

        canvas._add_ring_from_points.assert_called_once()
        self.assertEqual(
            _point_tuples(canvas._add_ring_from_points.call_args.args[0]),
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
        )
        canvas.add_benzene_ring.assert_not_called()
        canvas._add_atom_with_merge.assert_not_called()
        self.assertFalse(canvas._template_insert_active)
        self.assertIsNone(canvas.last_smiles_input)
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before",
        )

    def test_commit_template_insert_routes_benzene_plan_to_canvas_helper(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        canvas._template_ring_size = 6
        canvas._template_ring_style = "benzene"
        canvas.last_smiles_input = "before"
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()

        request = TemplateInsertRequest(ring_size=6, cursor_pos=(8.0, 9.0), bond_id=4, ring_style="benzene")

        with patch.object(controller, "_template_insert_request", return_value=request):
            controller._commit_template_insert(QPointF(*request.cursor_pos))

        canvas.add_benzene_ring.assert_called_once()
        args = canvas.add_benzene_ring.call_args
        self.assertEqual((args.args[0].x(), args.args[0].y()), (8.0, 9.0))
        self.assertEqual(args.kwargs["attach_bond_id"], 4)
        self.assertEqual(args.kwargs["before_smiles_input"], "before")
        canvas._add_ring_from_points.assert_not_called()
        canvas._record_additions.assert_not_called()
        self.assertFalse(canvas._template_insert_active)
        self.assertIsNone(canvas.last_smiles_input)

    def test_commit_template_insert_merges_against_selected_bond_seed(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("C", 3.0, 4.0),
            },
            bonds=[Bond(1, 2)],
        )
        canvas._template_insert_active = True
        canvas._template_ring_size = 6
        canvas._template_ring_style = "chair"
        canvas.last_smiles_input = "before"
        canvas._add_atom_with_merge.side_effect = [10, 11, 12]
        canvas._bond_exists.side_effect = lambda a_id, b_id: {a_id, b_id} == {10, 11}
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()

        request = TemplateInsertRequest(ring_size=6, cursor_pos=(20.0, 30.0), bond_id=0, ring_style="chair")
        plan = plan_template_commit(request)
        assert plan is not None
        resolution = TemplateInsertResolution(plan=plan, points=[(9.0, 8.0), (7.0, 6.0), (5.0, 4.0)])

        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.resolve_template_insert",
            return_value=resolution,
        ):
            controller._commit_template_insert(QPointF(*request.cursor_pos))

        expected_merge = [(1, 1.0, 2.0), (2, 3.0, 4.0)]
        self.assertEqual(canvas._add_atom_with_merge.call_count, 3)
        self.assertEqual(
            [_point_tuples([call.args[0]])[0] for call in canvas._add_atom_with_merge.call_args_list],
            [(9.0, 8.0), (7.0, 6.0), (5.0, 4.0)],
        )
        for call in canvas._add_atom_with_merge.call_args_list:
            self.assertEqual(call.args[1], "C")
            self.assertEqual(call.args[2], expected_merge)
        self.assertEqual(canvas.add_bond_calls, [(11, 12, 1), (12, 10, 1)])
        self.assertEqual(
            [call.args[0] for call in canvas._add_bond_graphics.call_args_list],
            [1, 2],
        )
        canvas._add_ring_from_points.assert_not_called()
        self.assertFalse(canvas._template_insert_active)
        self.assertIsNone(canvas.last_smiles_input)
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=3,
            before_bond_count=1,
            before_smiles_input="before",
        )

    def test_template_helper_resolvers_and_request_roundtrip(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        canvas._template_ring_size = 6
        canvas._template_ring_style = "chair"
        canvas._find_bond_near.return_value = 5
        canvas._ring_points.return_value = [QPointF(1.0, 2.0), QPointF(3.0, 4.0)]
        canvas._regular_ring_points_for_bond.return_value = ([QPointF(5.0, 6.0)], "unused")
        canvas._cyclohexane_chair_points.return_value = [QPointF(7.0, 8.0)]
        canvas._cyclohexane_boat_points.return_value = [QPointF(9.0, 10.0)]
        canvas._template_points_for_bond.return_value = ([QPointF(11.0, 12.0)], "unused")
        controller = InsertController(canvas)

        request = controller._template_insert_request(QPointF(20.0, 30.0))

        self.assertEqual(request, TemplateInsertRequest(6, (20.0, 30.0), 5, "chair"))
        self.assertEqual(controller._resolve_ring_points_for_template((1.0, 2.0), 6, 12.0), [(1.0, 2.0), (3.0, 4.0)])
        self.assertEqual(controller._resolve_regular_ring_points_for_template_bond(6, 3, (4.0, 5.0)), [(5.0, 6.0)])
        self.assertEqual(controller._resolve_chair_points_for_template((0.0, 0.0)), [(7.0, 8.0)])
        self.assertEqual(controller._resolve_boat_points_for_template((0.0, 0.0)), [(9.0, 10.0)])
        self.assertEqual(
            controller._resolve_template_points_for_template_bond([(0.0, 0.0)], 4, (2.0, 3.0)),
            [(11.0, 12.0)],
        )
        self.assertIsNone(controller._template_points_from_pairs(None))
        self.assertEqual(_point_tuples(controller._template_points_from_pairs([(1.0, 1.5)])), [(1.0, 1.5)])

    def test_commit_template_insert_cancels_for_missing_request_or_plan(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()

        with patch.object(controller, "_template_insert_request", return_value=None):
            controller._commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas._template_insert_active)

        canvas._template_insert_active = True
        with patch.object(
            controller,
            "_template_insert_request",
            return_value=TemplateInsertRequest(2, (1.0, 2.0), ring_style="regular"),
        ):
            controller._commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas._template_insert_active)

    def test_commit_template_insert_cancels_for_missing_resolution_or_points(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_insert_active = True
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()
        request = TemplateInsertRequest(5, (1.0, 2.0), ring_style="regular")
        plan = plan_template_commit(request)
        assert plan is not None

        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.resolve_template_insert",
            return_value=None,
        ):
            controller._commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas._template_insert_active)

        canvas._template_insert_active = True
        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.resolve_template_insert",
            return_value=TemplateInsertResolution(plan=plan, points=None),
        ):
            controller._commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas._template_insert_active)

    def test_clear_template_preview_uses_helper_results(self) -> None:
        canvas = _FakeCanvas()
        canvas._template_preview_items = ["old"]
        controller = InsertController(canvas)

        with patch(
            "ui.insert_controller.clear_template_preview_helper",
            return_value=(["new-items"], ["lines"], ["dots"]),
        ) as helper:
            controller._clear_template_preview()

        helper.assert_called_once_with(canvas.scene(), ["old"])
        self.assertEqual(canvas._template_preview_items, ["new-items"])
        self.assertEqual(canvas._template_preview_lines, ["lines"])
        self.assertEqual(canvas._template_preview_dots, ["dots"])

    def test_render_template_preview_clears_for_missing_request_and_preview_plan(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)
        controller._clear_template_preview = Mock()

        with patch.object(controller, "_template_insert_request", return_value=None):
            controller._render_template_preview(QPointF(4.0, 5.0))
        controller._clear_template_preview.assert_called_once_with()

        controller._clear_template_preview.reset_mock()
        request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.plan_template_preview",
            return_value=None,
        ):
            controller._render_template_preview(QPointF(4.0, 5.0))
        controller._clear_template_preview.assert_called_once_with()

    def test_render_template_preview_applies_geometry(self) -> None:
        canvas = _FakeCanvas()
        controller = InsertController(canvas)
        request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
        plan = SimpleNamespace(generator="free_regular_ring")
        resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0)])

        with patch.object(controller, "_template_insert_request", return_value=request), patch(
            "ui.insert_controller.plan_template_preview",
            return_value=plan,
        ), patch(
            "ui.insert_controller.resolve_template_insert",
            return_value=resolution,
        ), patch(
            "ui.insert_controller.plan_template_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"segments": 2}),
        ) as preview_update, patch(
            "ui.insert_controller.apply_template_preview_geometry_helper",
            return_value=(["items"], ["lines"], ["dots"]),
        ) as apply_helper:
            controller._render_template_preview(QPointF(4.0, 5.0))

        self.assertEqual(preview_update.call_args.args[0], [(1.0, 2.0), (3.0, 4.0)])
        apply_helper.assert_called_once()
        self.assertEqual(canvas._template_preview_items, ["items"])
        self.assertEqual(canvas._template_preview_lines, ["lines"])
        self.assertEqual(canvas._template_preview_dots, ["dots"])

    def test_bond_merge_seed_handles_valid_and_invalid_bonds(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("O", 3.0, 4.0),
            },
            bonds=[Bond(1, 2), None, Bond(1, 99)],
        )
        controller = InsertController(canvas)

        self.assertEqual(controller._bond_merge_seed(0), [(1, 1.0, 2.0), (2, 3.0, 4.0)])
        self.assertEqual(controller._bond_merge_seed(-1), [])
        self.assertEqual(controller._bond_merge_seed(1), [])
        self.assertEqual(controller._bond_merge_seed(2), [])
        self.assertEqual(controller._bond_merge_seed(99), [])


if __name__ == "__main__":
    unittest.main()
