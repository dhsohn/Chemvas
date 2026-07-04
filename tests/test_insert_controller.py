import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
)
from core.model import Atom, Bond, MoleculeModel
from PyQt6.QtCore import QPointF, QRectF
from ui.canvas_insert_state import CanvasInsertState
from ui.canvas_mark_registry import CanvasMarkRegistry
from ui.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    set_scene_item_collection_for,
)
from ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from ui.history_commands import AddSceneItemsCommand, DeleteSceneItemsCommand
from ui.insert_controller import InsertController
from ui.sheet_setup_state import sheet_setup_state_for
from ui.template_insert_logic import (
    TemplateInsertRequest,
    TemplateInsertResolution,
    plan_template_commit,
)


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
    def __init__(self, kind: str, atom_id=None, state: dict | None = None) -> None:
        self.kind = kind
        self._payload = {}
        self._state = dict(state or {"kind": kind})
        if atom_id is not None:
            self._payload["atom_id"] = atom_id

    def data(self, role: int):
        if role == 1:
            return dict(self._payload)
        if role == 9:
            return dict(self._state)
        return None


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
        set_last_smiles_input_for(self, None)
        self.insert_state = CanvasInsertState()

        self.mark_registry = CanvasMarkRegistry()
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            set_scene_item_collection_for(self, name, [])
        self._scene = object()
        self._viewport_center = QPointF(60.0, 40.0)

        self.clear_scene = Mock()
        self.push_command = Mock()
        self.history_service = SimpleNamespace(push=self.push_command)
        self.rebuild_bond_adjacency = Mock()
        self._record_additions = Mock()
        self._add_bond_graphics = Mock()
        self.bond_renderer = SimpleNamespace(
            add_bond_graphics=self._add_bond_graphics,
            parallel_bond_segments=Mock(
                side_effect=lambda x1, y1, x2, y2, order: ((x1, y1, x2, y2),) * max(0, order)
            ),
        )
        self.add_benzene_ring = Mock()
        self.clear_benzene_preview = Mock()

        self._atom_state_dict = Mock(side_effect=lambda atom_id: {"atom_id": atom_id})
        self._bond_state_dict = Mock(side_effect=lambda bond: {"bond": (bond.a, bond.b, bond.order)})
        self.scene_item_state = Mock(side_effect=lambda item: {"kind": getattr(item, "kind", "item")})
        self.bond_exists = Mock(return_value=False)

        self.add_bond_calls: list[tuple[int, int, int]] = []
        self.add_atom_calls: list[tuple[str, float, float]] = []
        self.ensure_carbon_dot_calls: list[int] = []
        self.atom_label_calls: list[tuple[int, str, bool, bool, bool]] = []
        self.mark_calls: list[tuple[int, float, float, str | None, bool]] = []
        self.created_marks: list[_FakeSceneItem] = []
        self.services = SimpleNamespace(
            history_service=self.history_service,
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                ensure_carbon_dot=self.ensure_carbon_dot,
            ),
            benzene_preview_service=SimpleNamespace(clear_preview=self.clear_benzene_preview),
            canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
            canvas_bond_mutation_service=SimpleNamespace(add_bond=self.add_bond),
            canvas_graph_service=SimpleNamespace(
                rebuild_bond_adjacency=self.rebuild_bond_adjacency,
                bond_exists=self.bond_exists,
            ),
            canvas_history_recording_service=SimpleNamespace(record_additions=self._record_additions),
            canvas_mark_scene_service=SimpleNamespace(add_mark_for_atom=self.add_mark_for_atom),
            canvas_scene_reset_service=SimpleNamespace(clear_scene=lambda: self.clear_scene()),
            hit_testing_service=SimpleNamespace(find_bond_near=Mock(return_value=None)),
            structure_build_service=SimpleNamespace(
                render_model=Mock(),
                add_ring_from_points=Mock(),
                add_atom_with_merge=Mock(),
                add_benzene_ring=self.add_benzene_ring,
            ),
        )

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
        self.atom_label_calls.append((atom_id, text, clear_smiles, record, show_carbon))
        self.model.atoms[atom_id].element = text
        self.model.atoms[atom_id].explicit_label = show_carbon

    def add_mark_for_atom(self, atom_id: int, click_pos: QPointF, *, kind: str | None = None, record: bool = True):
        self.mark_calls.append((atom_id, click_pos.x(), click_pos.y(), kind, record))
        item = _FakeSceneItem("mark", atom_id=atom_id, state={"kind": "mark", "mark_kind": kind, "atom_id": atom_id})
        self.created_marks.append(item)
        return item


def _controller_for(canvas: _FakeCanvas, **kwargs) -> InsertController:
    hit_testing_service = kwargs.pop("hit_testing_service", canvas.services.hit_testing_service)
    graph_service = kwargs.pop("graph_service", canvas.services.canvas_graph_service)
    structure_build_service = kwargs.pop("structure_build_service", canvas.services.structure_build_service)
    return InsertController(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=canvas.services.history_service,
        **kwargs,
    )


class InsertControllerTest(unittest.TestCase):
    def test_public_wrappers_delegate_to_internal_helpers(self) -> None:
        canvas = _FakeCanvas()
        commit_service = Mock()
        commit_service.bond_merge_seed.return_value = [(1, 2.0, 3.0)]
        controller = _controller_for(canvas, insert_commit_service=commit_service)
        state = controller.insert_session_state()
        request = TemplateInsertRequest(6, (1.0, 2.0), 3, "chair")
        resolvers = object()
        pairs = [(1.0, 2.0)]
        preview_snapshot = ({0: ["bond"]}, {1: "atom"})

        controller.insert_session_state = Mock(return_value=state)
        controller.smiles_preview_snapshot = Mock(return_value=preview_snapshot)
        controller.template_insert_request = Mock(return_value=request)
        controller.template_point_resolvers = Mock(return_value=resolvers)
        controller.resolve_ring_points_for_template = Mock(return_value=pairs)
        controller.resolve_regular_ring_points_for_template_bond = Mock(return_value=pairs)
        controller.resolve_chair_points_for_template = Mock(return_value=pairs)
        controller.resolve_boat_points_for_template = Mock(return_value=pairs)
        controller.resolve_template_points_for_template_bond = Mock(return_value=pairs)

        self.assertIs(controller.insert_session_state(), state)
        self.assertEqual(controller.smiles_preview_snapshot(), preview_snapshot)
        self.assertIs(controller.template_insert_request(QPointF(1.0, 2.0)), request)
        self.assertIs(controller.template_point_resolvers(), resolvers)
        self.assertEqual(controller.resolve_ring_points_for_template((1.0, 2.0), 6, 12.0), pairs)
        self.assertEqual(controller.resolve_regular_ring_points_for_template_bond(6, 3, (4.0, 5.0)), pairs)
        self.assertEqual(controller.resolve_chair_points_for_template((0.0, 0.0)), pairs)
        self.assertEqual(controller.resolve_boat_points_for_template((0.0, 0.0)), pairs)
        self.assertEqual(controller.resolve_template_points_for_template_bond([(0.0, 0.0)], 4, (2.0, 3.0)), pairs)
        self.assertEqual(controller.bond_merge_seed(7), [(1, 2.0, 3.0)])

        controller.insert_session_state.assert_called_once_with()
        controller.smiles_preview_snapshot.assert_called_once_with()
        controller.template_insert_request.assert_called_once_with(QPointF(1.0, 2.0))
        controller.template_point_resolvers.assert_called_once_with()
        controller.resolve_ring_points_for_template.assert_called_once_with((1.0, 2.0), 6, 12.0)
        controller.resolve_regular_ring_points_for_template_bond.assert_called_once_with(6, 3, (4.0, 5.0))
        controller.resolve_chair_points_for_template.assert_called_once_with((0.0, 0.0))
        controller.resolve_boat_points_for_template.assert_called_once_with((0.0, 0.0))
        controller.resolve_template_points_for_template_bond.assert_called_once_with([(0.0, 0.0)], 4, (2.0, 3.0))
        commit_service.bond_merge_seed.assert_called_once_with(7)

    def test_insert_session_state_and_apply_insert_session_state_track_and_clear_modes(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        canvas.insert_state.template_ring_style = "benzene"
        canvas.insert_state.smiles_active = True
        canvas.insert_state.smiles_preview_smiles = "CC"
        canvas.insert_state.smiles_preview_center = QPointF(12.0, 34.0)
        controller = _controller_for(canvas)

        state = controller.insert_session_state()

        self.assertTrue(state.template_active)
        self.assertEqual(state.template_ring_size, 6)
        self.assertEqual(state.template_ring_style, "benzene")
        self.assertTrue(state.smiles_active)
        self.assertEqual(state.smiles_text, "CC")
        self.assertEqual(state.smiles_center, (12.0, 34.0))

        controller.clear_template_preview = Mock()
        controller.clear_smiles_preview = Mock()
        controller.apply_insert_session_state(
            state.__class__(
                template_active=False,
                template_ring_size=None,
                template_ring_style=None,
                smiles_active=False,
                smiles_text=None,
                smiles_center=None,
            )
        )

        self.assertFalse(canvas.insert_state.template_active)
        self.assertFalse(canvas.insert_state.smiles_active)
        self.assertIsNone(canvas.insert_state.smiles_preview_center)
        controller.clear_template_preview.assert_called_once_with()
        controller.clear_smiles_preview.assert_called_once_with()

    def test_insert_preview_and_commit_skip_positions_outside_sheet(self) -> None:
        canvas = _FakeCanvas()
        sheet_setup_state_for(canvas).rect = QRectF(-10.0, -10.0, 20.0, 20.0)
        controller = _controller_for(canvas)
        controller.clear_template_preview = Mock()
        controller.clear_smiles_preview = Mock()
        controller.template_service.commit_template_request = Mock()
        controller.template_service.render_template_request_preview = Mock()
        controller.smiles_service.commit_smiles_insert = Mock()
        controller.smiles_service.render_smiles_preview = Mock()
        outside = QPointF(999.0, 999.0)

        controller.commit_template_insert(outside)
        controller.render_template_preview(outside)
        controller.commit_smiles_insert(outside)
        controller.render_smiles_preview(outside)

        self.assertEqual(controller.clear_template_preview.call_count, 2)
        self.assertEqual(controller.clear_smiles_preview.call_count, 2)
        controller.template_service.commit_template_request.assert_not_called()
        controller.template_service.render_template_request_preview.assert_not_called()
        controller.smiles_service.commit_smiles_insert.assert_not_called()
        controller.smiles_service.render_smiles_preview.assert_not_called()

    def test_load_smiles_blank_is_no_op(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)

        controller.load_smiles("   ")

        canvas.rdkit.smiles_to_2d.assert_not_called()
        canvas.clear_scene.assert_not_called()
        canvas.push_command.assert_not_called()

    def test_load_smiles_warns_when_rdkit_conversion_fails(self) -> None:
        canvas = _FakeCanvas()
        set_last_smiles_input_for(canvas, "C")
        canvas.rdkit.last_error = "bad smiles"
        controller = _controller_for(canvas)

        with patch("ui.insert_smiles_service.QMessageBox.warning") as warning:
            controller.load_smiles("broken")

        warning.assert_called_once_with(canvas, "SMILES Error", "bad smiles")
        canvas.clear_scene.assert_not_called()
        canvas.push_command.assert_not_called()
        self.assertEqual(last_smiles_input_for(canvas), "C")

    def test_load_smiles_replaces_scene_and_pushes_history_command(self) -> None:
        canvas = _FakeCanvas()
        set_last_smiles_input_for(canvas, "before")
        canvas.model.add_atom("N", -5.0, -5.0)
        canvas.model.bonds.append(Bond(0, 0, 1))
        bound_mark = _FakeSceneItem("bound-mark", atom_id=0, state={"kind": "mark"})
        free_mark = _FakeSceneItem("free-mark")
        note = _FakeSceneItem("note")
        canvas.mark_registry.by_atom = {0: [bound_mark]}
        set_scene_item_collection_for(canvas, "mark_items", [bound_mark, free_mark])
        set_scene_item_collection_for(canvas, "note_items", [note])
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
            atoms={0: Atom("C", 1.0, 2.0), 1: Atom("C", 3.0, 2.0)},
            bonds=[Bond(0, 1, 1)],
        )

        def _clear_scene() -> None:
            canvas.model = MoleculeModel()

        canvas.clear_scene = Mock(side_effect=_clear_scene)
        controller = _controller_for(canvas)

        controller.load_smiles(" C ")

        canvas.clear_scene.assert_called_once_with()
        canvas.rebuild_bond_adjacency.assert_called_once_with()
        canvas.services.structure_build_service.render_model.assert_called_once_with()
        self.assertEqual(last_smiles_input_for(canvas), "C")
        command = canvas.push_command.call_args.args[0]
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
        self.assertEqual(add_atoms.after_next_atom_id, 2)
        self.assertEqual(add_bond.previous_bond_count, 0)

    def test_load_smiles_adds_annotation_marks_to_transaction_history(self) -> None:
        canvas = _FakeCanvas()
        model = MoleculeModel(atoms={0: Atom("N", 1.0, 2.0)})
        model.atom_annotations = {0: {"formal_charge": 1}}
        canvas.rdkit.smiles_to_2d.return_value = model

        def _clear_scene() -> None:
            canvas.model = MoleculeModel()

        canvas.clear_scene = Mock(side_effect=_clear_scene)
        controller = _controller_for(canvas)

        controller.load_smiles("[NH4+]")

        self.assertEqual(canvas.mark_calls, [(0, 2.0, 1.0, "plus", False)])
        command = canvas.push_command.call_args.args[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertIsInstance(command.commands[-1], AddSceneItemsCommand)
        self.assertEqual(command.commands[-1].items, canvas.created_marks)

    def test_load_smiles_skips_push_when_history_builder_returns_none(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(atoms={0: Atom("C", 1.0, 2.0)})

        def _clear_scene() -> None:
            canvas.model = MoleculeModel()

        canvas.clear_scene = Mock(side_effect=_clear_scene)
        controller = _controller_for(canvas)
        controller.smiles_service.transaction_builder.capture = Mock(return_value="snapshot")
        controller.smiles_service.transaction_builder.build_command = Mock(return_value=None)

        controller.load_smiles("C")

        controller.smiles_service.transaction_builder.capture.assert_called_once_with()
        controller.smiles_service.transaction_builder.build_command.assert_called_once_with(
            "snapshot",
            after_clear_next_atom_id=0,
            after_smiles_input="C",
        )
        canvas.push_command.assert_not_called()

    def test_begin_ring_template_insert_noops_for_invalid_request(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        controller.render_template_preview = Mock()
        controller.cancel_smiles_insert = Mock()

        controller.begin_ring_template_insert(2)

        self.assertFalse(canvas.insert_state.template_active)
        canvas.clear_benzene_preview.assert_not_called()
        controller.cancel_smiles_insert.assert_not_called()
        controller.render_template_preview.assert_not_called()

    def test_begin_ring_template_insert_cancels_smiles_without_rendering_initial_preview(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.smiles_active = True
        controller = _controller_for(canvas)
        controller.cancel_smiles_insert = Mock()
        controller.render_template_preview = Mock()

        controller.begin_ring_template_insert(6, "benzene")

        controller.cancel_smiles_insert.assert_called_once_with()
        canvas.clear_benzene_preview.assert_called_once_with()
        self.assertTrue(canvas.insert_state.template_active)
        self.assertEqual(canvas.insert_state.template_ring_size, 6)
        self.assertEqual(canvas.insert_state.template_ring_style, "benzene")
        controller.render_template_preview.assert_not_called()

    def test_begin_smiles_insert_blank_is_noop(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        controller.render_smiles_preview = Mock()

        controller.begin_smiles_insert("   ")

        canvas.rdkit.smiles_to_2d.assert_not_called()
        controller.render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_warns_when_rdkit_conversion_fails(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.last_error = "bad smiles"
        controller = _controller_for(canvas)

        with patch("ui.insert_smiles_service.QMessageBox.warning") as warning:
            controller.begin_smiles_insert("broken")

        warning.assert_called_once_with(canvas, "SMILES Error", "bad smiles")
        self.assertIsNone(canvas.insert_state.smiles_preview_model)

    def test_begin_smiles_insert_clears_model_when_preview_center_is_missing(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel()
        controller = _controller_for(canvas)
        controller.render_smiles_preview = Mock()

        controller.begin_smiles_insert("CC")

        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        controller.render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_clears_model_when_state_helper_returns_none(self) -> None:
        canvas = _FakeCanvas()
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        controller = _controller_for(canvas)
        controller.render_smiles_preview = Mock()

        with patch("ui.insert_smiles_service.begin_smiles_insert_state", return_value=None):
            controller.begin_smiles_insert("CC")

        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        controller.render_smiles_preview.assert_not_called()

    def test_begin_smiles_insert_cancels_template_and_renders_preview(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("O", 10.0, 0.0),
            }
        )
        controller = _controller_for(canvas)
        controller.cancel_template_insert = Mock()
        controller.render_smiles_preview = Mock()

        controller.begin_smiles_insert(" CO ")

        controller.cancel_template_insert.assert_called_once_with()
        canvas.clear_benzene_preview.assert_called_once_with()
        self.assertTrue(canvas.insert_state.smiles_active)
        self.assertEqual(canvas.insert_state.smiles_preview_smiles, "CO")
        self.assertEqual((canvas.insert_state.smiles_preview_center.x(), canvas.insert_state.smiles_preview_center.y()), (5.0, 0.0))
        preview_pos = controller.render_smiles_preview.call_args.args[0]
        self.assertEqual((preview_pos.x(), preview_pos.y()), (60.0, 40.0))

    def test_commit_smiles_insert_cancels_when_preview_center_is_missing(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.smiles_active = True
        canvas.insert_state.smiles_preview_smiles = "CC"
        canvas.insert_state.smiles_preview_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        controller = _controller_for(canvas)
        controller.clear_smiles_preview = Mock()

        controller.commit_smiles_insert(QPointF(40.0, 20.0))

        self.assertFalse(canvas.insert_state.smiles_active)
        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        self.assertIsNone(canvas.insert_state.smiles_preview_smiles)
        self.assertIsNone(canvas.insert_state.smiles_preview_center)
        controller.clear_smiles_preview.assert_called_once_with()
        canvas._record_additions.assert_not_called()

    def test_commit_smiles_insert_cancels_when_commit_service_rejects_plan(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.smiles_active = True
        canvas.insert_state.smiles_preview_smiles = "CO"
        canvas.insert_state.smiles_preview_center = QPointF(5.0, 0.0)
        canvas.insert_state.smiles_preview_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        commit_service = Mock()
        commit_service.apply_smiles_commit.return_value = False
        controller = _controller_for(canvas, insert_commit_service=commit_service)
        controller.clear_smiles_preview = Mock()

        controller.commit_smiles_insert(QPointF(40.0, 20.0))

        commit_service.apply_smiles_commit.assert_called_once()
        self.assertFalse(canvas.insert_state.smiles_active)
        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        controller.clear_smiles_preview.assert_called_once_with()

    def test_commit_smiles_insert_adds_atoms_bonds_labels_and_history(self) -> None:
        canvas = _FakeCanvas()
        set_last_smiles_input_for(canvas, "before")
        canvas.model.add_atom("N", -5.0, -5.0)
        canvas.model.bonds.append(Bond(0, 0, 1))
        canvas.insert_state.smiles_preview_smiles = "CO"
        canvas.insert_state.smiles_preview_center = QPointF(5.0, 0.0)
        canvas.insert_state.smiles_preview_model = MoleculeModel(
            atoms={
                3: Atom("C", 0.0, 0.0, color="#111111", explicit_label=False),
                7: Atom("O", 10.0, 0.0, color="#222222", explicit_label=True),
            },
            bonds=[Bond(3, 7, 2, style="double", color="#333333")],
        )
        controller = _controller_for(canvas)
        controller.cancel_smiles_insert = Mock()

        controller.commit_smiles_insert(QPointF(40.0, 20.0))

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
        self.assertEqual(last_smiles_input_for(canvas), "CO")
        controller.cancel_smiles_insert.assert_called_once_with()
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=1,
            before_bond_count=1,
            before_smiles_input="before",
        )

    def test_clear_smiles_preview_uses_helper_results(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.smiles_preview_items = ["old"]
        controller = _controller_for(canvas)

        with patch(
            "ui.insert_smiles_service.clear_smiles_preview_helper",
            return_value=(["new-items"], {"bond": ["segments"]}, {1: "atom"}),
        ) as helper:
            controller.clear_smiles_preview()

        helper.assert_called_once_with(canvas, ["old"])
        self.assertEqual(canvas.insert_state.smiles_preview_items, ["new-items"])
        self.assertEqual(canvas.insert_state.smiles_preview_bond_items, {"bond": ["segments"]})
        self.assertEqual(canvas.insert_state.smiles_preview_atom_items, {1: "atom"})

    def test_render_smiles_preview_clears_on_clear_plan(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        controller.clear_smiles_preview = Mock()

        with patch(
            "ui.insert_smiles_service.plan_smiles_preview_update",
            return_value=SimpleNamespace(action="clear", geometry=None),
        ):
            controller.render_smiles_preview(QPointF(10.0, 20.0))

        controller.clear_smiles_preview.assert_called_once_with()

    def test_render_smiles_preview_applies_geometry(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.smiles_preview_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})
        canvas.insert_state.smiles_preview_center = QPointF(0.0, 0.0)
        canvas.insert_state.smiles_preview_items = ["old"]
        canvas.insert_state.smiles_preview_bond_items = {0: ["bond"]}
        canvas.insert_state.smiles_preview_atom_items = {0: "atom"}
        controller = _controller_for(canvas)

        with patch(
            "ui.insert_smiles_service.plan_smiles_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"lines": 1}),
        ) as plan_update, patch(
            "ui.insert_smiles_service.apply_smiles_preview_geometry_helper",
            return_value=(["items"], {0: ["new-bond"]}, {0: "new-atom"}),
        ) as apply_helper:
            controller.render_smiles_preview(QPointF(12.0, 18.0))

        self.assertEqual(plan_update.call_args.args[2], (12.0, 18.0))
        apply_helper.assert_called_once()
        self.assertEqual(canvas.insert_state.smiles_preview_items, ["items"])
        self.assertEqual(canvas.insert_state.smiles_preview_bond_items, {0: ["new-bond"]})
        self.assertEqual(canvas.insert_state.smiles_preview_atom_items, {0: "new-atom"})

    def test_commit_template_insert_uses_free_ring_path_for_unattached_templates(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 5
        canvas.insert_state.template_ring_style = "regular"
        set_last_smiles_input_for(canvas, "before")
        controller = _controller_for(canvas)

        request = TemplateInsertRequest(ring_size=5, cursor_pos=(12.0, 18.0), ring_style="regular")
        plan = plan_template_commit(request)
        assert plan is not None
        resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ):
            controller.commit_template_insert(QPointF(*request.cursor_pos))

        canvas.services.structure_build_service.add_ring_from_points.assert_called_once()
        self.assertEqual(
            _point_tuples(canvas.services.structure_build_service.add_ring_from_points.call_args.args[0]),
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
        )
        canvas.add_benzene_ring.assert_not_called()
        canvas.services.structure_build_service.add_atom_with_merge.assert_not_called()
        self.assertTrue(canvas.insert_state.template_active)
        self.assertEqual(canvas.insert_state.template_ring_size, 5)
        self.assertEqual(canvas.insert_state.template_ring_style, "regular")
        self.assertEqual(canvas.insert_state.template_preview_items, [])
        self.assertIsNone(last_smiles_input_for(canvas))
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before",
        )

    def test_commit_template_insert_routes_benzene_plan_to_canvas_helper(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        canvas.insert_state.template_ring_style = "benzene"
        set_last_smiles_input_for(canvas, "before")
        controller = _controller_for(canvas)

        request = TemplateInsertRequest(ring_size=6, cursor_pos=(8.0, 9.0), bond_id=4, ring_style="benzene")

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_commit_service.has_insert_mutation_since_for",
            return_value=True,
        ):
            controller.commit_template_insert(QPointF(*request.cursor_pos))

        canvas.add_benzene_ring.assert_called_once()
        args = canvas.add_benzene_ring.call_args
        self.assertEqual((args.args[0].x(), args.args[0].y()), (8.0, 9.0))
        self.assertEqual(args.kwargs["attach_bond_id"], 4)
        self.assertEqual(args.kwargs["before_smiles_input"], "before")
        canvas.services.structure_build_service.add_ring_from_points.assert_not_called()
        canvas._record_additions.assert_not_called()
        self.assertTrue(canvas.insert_state.template_active)
        self.assertEqual(canvas.insert_state.template_ring_size, 6)
        self.assertEqual(canvas.insert_state.template_ring_style, "benzene")
        self.assertEqual(canvas.insert_state.template_preview_items, [])
        self.assertIsNone(last_smiles_input_for(canvas))

    def test_commit_template_insert_routes_atom_benzene_plan_to_canvas_helper(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        canvas.insert_state.template_ring_style = "benzene"
        controller = _controller_for(canvas)
        request = TemplateInsertRequest(ring_size=6, cursor_pos=(8.0, 9.0), ring_style="benzene", atom_id=3)

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_commit_service.has_insert_mutation_since_for",
            return_value=True,
        ):
            controller.commit_template_insert(QPointF(*request.cursor_pos))

        canvas.add_benzene_ring.assert_called_once()
        args = canvas.add_benzene_ring.call_args
        self.assertEqual(args.kwargs["attach_atom_id"], 3)
        self.assertIsNone(args.kwargs["attach_bond_id"])

    def test_commit_template_insert_merges_against_selected_bond_seed(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("C", 3.0, 4.0),
            },
            bonds=[Bond(1, 2)],
        )
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        canvas.insert_state.template_ring_style = "chair"
        set_last_smiles_input_for(canvas, "before")

        atom_ids = iter([10, 11, 12])

        def add_atom_with_merge(point: QPointF, element: str, merge: list) -> int:
            atom_id = next(atom_ids)
            canvas.model.atoms[atom_id] = Atom(element, point.x(), point.y())
            canvas.model.next_atom_id = max(canvas.model.next_atom_id, atom_id + 1)
            return atom_id

        canvas.services.structure_build_service.add_atom_with_merge.side_effect = add_atom_with_merge
        canvas.bond_exists.side_effect = lambda a_id, b_id: {a_id, b_id} == {10, 11}
        controller = _controller_for(canvas)

        request = TemplateInsertRequest(ring_size=6, cursor_pos=(20.0, 30.0), bond_id=0, ring_style="chair")
        plan = plan_template_commit(request)
        assert plan is not None
        resolution = TemplateInsertResolution(plan=plan, points=[(9.0, 8.0), (7.0, 6.0), (5.0, 4.0)])

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ):
            controller.commit_template_insert(QPointF(*request.cursor_pos))

        expected_merge = [(1, 1.0, 2.0), (2, 3.0, 4.0)]
        self.assertEqual(canvas.services.structure_build_service.add_atom_with_merge.call_count, 3)
        self.assertEqual(
            [
                _point_tuples([call.args[0]])[0]
                for call in canvas.services.structure_build_service.add_atom_with_merge.call_args_list
            ],
            [(9.0, 8.0), (7.0, 6.0), (5.0, 4.0)],
        )
        for call in canvas.services.structure_build_service.add_atom_with_merge.call_args_list:
            self.assertEqual(call.args[1], "C")
            self.assertEqual(call.args[2], expected_merge)
        self.assertEqual(canvas.add_bond_calls, [(11, 12, 1), (12, 10, 1)])
        self.assertEqual(
            [call.args[0] for call in canvas._add_bond_graphics.call_args_list],
            [1, 2],
        )
        canvas.services.structure_build_service.add_ring_from_points.assert_not_called()
        self.assertTrue(canvas.insert_state.template_active)
        self.assertEqual(canvas.insert_state.template_ring_size, 6)
        self.assertEqual(canvas.insert_state.template_ring_style, "chair")
        self.assertEqual(canvas.insert_state.template_preview_items, [])
        self.assertIsNone(last_smiles_input_for(canvas))
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=3,
            before_bond_count=1,
            before_smiles_input="before",
        )

    def test_commit_template_insert_merges_against_selected_atom_seed(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={1: Atom("C", 1.0, 2.0)}, bonds=[])
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 5
        canvas.insert_state.template_ring_style = "regular"
        set_last_smiles_input_for(canvas, "before")

        atom_ids = iter([10, 11])

        def add_atom_with_merge(point: QPointF, element: str, merge: list) -> int:
            if (point.x(), point.y()) == (1.0, 2.0):
                return 1
            atom_id = next(atom_ids)
            canvas.model.atoms[atom_id] = Atom(element, point.x(), point.y())
            canvas.model.next_atom_id = max(canvas.model.next_atom_id, atom_id + 1)
            return atom_id

        canvas.services.structure_build_service.add_atom_with_merge.side_effect = add_atom_with_merge
        controller = _controller_for(canvas)
        request = TemplateInsertRequest(
            ring_size=5,
            cursor_pos=(20.0, 30.0),
            ring_style="regular",
            atom_id=1,
        )
        plan = plan_template_commit(request)
        assert plan is not None
        resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (7.0, 6.0), (5.0, 4.0)])

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ):
            controller.commit_template_insert(QPointF(*request.cursor_pos))

        expected_merge = [(1, 1.0, 2.0)]
        self.assertEqual(canvas.services.structure_build_service.add_atom_with_merge.call_count, 3)
        for call in canvas.services.structure_build_service.add_atom_with_merge.call_args_list:
            self.assertEqual(call.args[1], "C")
            self.assertEqual(call.args[2], expected_merge)
        self.assertEqual(canvas.add_bond_calls, [(1, 10, 1), (10, 11, 1), (11, 1, 1)])
        self.assertEqual([call.args[0] for call in canvas._add_bond_graphics.call_args_list], [0, 1, 2])
        canvas._record_additions.assert_called_once_with(
            before_next_atom_id=2,
            before_bond_count=0,
            before_smiles_input="before",
        )

    def test_template_helper_resolvers_and_request_roundtrip(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        canvas.insert_state.template_ring_style = "chair"
        canvas.services.hit_testing_service.find_bond_near.return_value = 5
        controller = _controller_for(canvas)
        with (
            patch(
                "ui.template_geometry_resolver_service.ring_points_for",
                return_value=[QPointF(1.0, 2.0), QPointF(3.0, 4.0)],
            ),
            patch(
                "ui.template_geometry_resolver_service.regular_ring_points_for_bond_for",
                return_value=([QPointF(5.0, 6.0)], "unused"),
            )
            as regular_ring_points_for_bond,
            patch(
                "ui.template_geometry_resolver_service.cyclohexane_chair_points_for",
                return_value=[QPointF(7.0, 8.0)],
            ),
            patch(
                "ui.template_geometry_resolver_service.cyclohexane_boat_points_for",
                return_value=[QPointF(9.0, 10.0)],
            ),
            patch(
                "ui.template_geometry_resolver_service.template_points_for_bond_for",
                return_value=([QPointF(11.0, 12.0)], "unused"),
            )
            as template_points_for_bond,
        ):
            request = controller.template_insert_request(QPointF(20.0, 30.0))

            self.assertEqual(request, TemplateInsertRequest(6, (20.0, 30.0), 5, "chair"))
            self.assertEqual(controller.resolve_ring_points_for_template((1.0, 2.0), 6, 12.0), [(1.0, 2.0), (3.0, 4.0)])
            self.assertEqual(controller.resolve_regular_ring_points_for_template_bond(6, 3, (4.0, 5.0)), [(5.0, 6.0)])
            self.assertEqual(controller.resolve_chair_points_for_template((0.0, 0.0)), [(7.0, 8.0)])
            self.assertEqual(controller.resolve_boat_points_for_template((0.0, 0.0)), [(9.0, 10.0)])
            self.assertEqual(
                controller.resolve_template_points_for_template_bond([(0.0, 0.0)], 4, (2.0, 3.0)),
                [(11.0, 12.0)],
            )
            regular_ring_points_for_bond.return_value = None
            template_points_for_bond.return_value = None
            self.assertIsNone(controller.resolve_regular_ring_points_for_template_bond(6, 3, (4.0, 5.0)))
            self.assertIsNone(controller.resolve_template_points_for_template_bond([(0.0, 0.0)], 4, (2.0, 3.0)))

    def test_template_request_uses_injected_hit_testing_service(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        canvas.insert_state.template_ring_size = 6
        injected_hit_testing = SimpleNamespace(find_bond_near=Mock(return_value=7))
        canvas.services.hit_testing_service = SimpleNamespace(
            find_bond_near=Mock(side_effect=AssertionError("registry service should not be used"))
        )
        canvas.find_bond_near = Mock(side_effect=AssertionError("canvas facade should not be used"))
        controller = _controller_for(canvas, hit_testing_service=injected_hit_testing)

        request = controller.template_insert_request(QPointF(1.0, 2.0))

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.bond_id, 7)
        injected_hit_testing.find_bond_near.assert_called_once_with(QPointF(1.0, 2.0), 7.0)
        canvas.services.hit_testing_service.find_bond_near.assert_not_called()
        canvas.find_bond_near.assert_not_called()

    def test_commit_template_insert_cancels_for_missing_request_or_plan(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        controller = _controller_for(canvas)
        controller.clear_template_preview = Mock()

        with patch.object(controller, "template_insert_request", return_value=None):
            controller.commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas.insert_state.template_active)

        canvas.insert_state.template_active = True
        with patch.object(
            controller,
            "template_insert_request",
            return_value=TemplateInsertRequest(2, (1.0, 2.0), ring_style="regular"),
        ):
            controller.commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas.insert_state.template_active)

    def test_commit_template_insert_cancels_for_missing_resolution_or_points(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_active = True
        controller = _controller_for(canvas)
        controller.clear_template_preview = Mock()
        request = TemplateInsertRequest(5, (1.0, 2.0), ring_style="regular")
        plan = plan_template_commit(request)
        assert plan is not None

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=None,
        ):
            controller.commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas.insert_state.template_active)

        canvas.insert_state.template_active = True
        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=TemplateInsertResolution(plan=plan, points=None),
        ):
            controller.commit_template_insert(QPointF(1.0, 2.0))
        self.assertFalse(canvas.insert_state.template_active)

    def test_clear_template_preview_uses_helper_results(self) -> None:
        canvas = _FakeCanvas()
        canvas.insert_state.template_preview_items = ["old"]
        controller = _controller_for(canvas)

        with patch(
            "ui.insert_template_service.clear_template_preview_helper",
            return_value=(["new-items"], ["lines"], ["dots"]),
        ) as helper:
            controller.clear_template_preview()

        helper.assert_called_once_with(canvas, ["old"])
        self.assertEqual(canvas.insert_state.template_preview_items, ["new-items"])
        self.assertEqual(canvas.insert_state.template_preview_lines, ["lines"])
        self.assertEqual(canvas.insert_state.template_preview_dots, ["dots"])

    def test_render_template_preview_clears_for_missing_request_and_preview_plan(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        controller.clear_template_preview = Mock()

        with patch.object(controller, "template_insert_request", return_value=None):
            controller.render_template_preview(QPointF(4.0, 5.0))
        controller.clear_template_preview.assert_called_once_with()

        controller.clear_template_preview.reset_mock()
        request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_service.plan_template_preview",
            return_value=None,
        ):
            controller.render_template_preview(QPointF(4.0, 5.0))
        controller.clear_template_preview.assert_called_once_with()

    def test_render_template_preview_clears_for_missing_resolution_points_and_clear_action(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        controller.clear_template_preview = Mock()
        request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
        plan = SimpleNamespace(generator="free_regular_ring")

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=None,
        ):
            controller.render_template_preview(QPointF(4.0, 5.0))
        controller.clear_template_preview.assert_called_once_with()

        controller.clear_template_preview.reset_mock()
        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=TemplateInsertResolution(plan=plan, points=None),
        ):
            controller.render_template_preview(QPointF(4.0, 5.0))
        controller.clear_template_preview.assert_called_once_with()

        controller.clear_template_preview.reset_mock()
        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=TemplateInsertResolution(plan=plan, points=[(1.0, 2.0)]),
        ), patch(
            "ui.insert_template_service.plan_template_preview_update",
            return_value=SimpleNamespace(action="clear", geometry=None),
        ):
            controller.render_template_preview(QPointF(4.0, 5.0))
        controller.clear_template_preview.assert_called_once_with()

    def test_render_template_preview_applies_geometry(self) -> None:
        canvas = _FakeCanvas()
        controller = _controller_for(canvas)
        request = TemplateInsertRequest(5, (4.0, 5.0), ring_style="regular")
        plan = SimpleNamespace(generator="free_regular_ring")
        resolution = TemplateInsertResolution(plan=plan, points=[(1.0, 2.0), (3.0, 4.0)])

        with patch.object(controller, "template_insert_request", return_value=request), patch(
            "ui.insert_template_service.plan_template_preview",
            return_value=plan,
        ), patch(
            "ui.template_geometry_resolver_service.resolve_template_insert",
            return_value=resolution,
        ), patch(
            "ui.insert_template_service.plan_template_preview_update",
            return_value=SimpleNamespace(action="update", geometry={"segments": 2}),
        ) as preview_update, patch(
            "ui.insert_template_service.apply_template_preview_geometry_helper",
            return_value=(["items"], ["lines"], ["dots"]),
        ) as apply_helper:
            controller.render_template_preview(QPointF(4.0, 5.0))

        self.assertEqual(preview_update.call_args.args[0], [(1.0, 2.0), (3.0, 4.0)])
        apply_helper.assert_called_once()
        self.assertEqual(canvas.insert_state.template_preview_items, ["items"])
        self.assertEqual(canvas.insert_state.template_preview_lines, ["lines"])
        self.assertEqual(canvas.insert_state.template_preview_dots, ["dots"])

    def test_bond_merge_seed_handles_valid_and_invalid_bonds(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 1.0, 2.0),
                2: Atom("O", 3.0, 4.0),
            },
            bonds=[Bond(1, 2), None, Bond(1, 99)],
        )
        controller = _controller_for(canvas)

        self.assertEqual(controller.bond_merge_seed(0), [(1, 1.0, 2.0), (2, 3.0, 4.0)])
        self.assertEqual(controller.bond_merge_seed(-1), [])
        self.assertEqual(controller.bond_merge_seed(1), [])
        self.assertEqual(controller.bond_merge_seed(2), [])
        self.assertEqual(controller.bond_merge_seed(99), [])


if __name__ == "__main__":
    unittest.main()
