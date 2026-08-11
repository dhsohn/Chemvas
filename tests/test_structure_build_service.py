import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

from chemvas.core.history import CompositeCommand, RestoreOutcome
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.insertion import (
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
)
from chemvas.ui.atom_coords_access import CanvasAtomCoords3DState
from chemvas.ui.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas_graph_state import CanvasGraphState
from chemvas.ui.canvas_history_recording_service import CanvasHistoryRecordingService
from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas_scene_items_state import (
    CanvasSceneItemsState,
    ring_items_for,
    set_scene_item_collection_for,
)
from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.insert_template_commit_service import apply_template_commit_resolution
from chemvas.ui.structure_build_service import StructureBuildService
from PyQt6.QtCore import QPointF

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state


class _BrokenAddNoteInterrupt(KeyboardInterrupt):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


class _BrokenAddNoteSystemExit(SystemExit):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


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


class _FakePolygon:
    def __init__(self, contains: bool, points: list[QPointF] | None = None) -> None:
        self._contains = contains
        self._points = points or []

    def containsPoint(self, point: QPointF, fill_rule) -> bool:
        return self._contains

    def __iter__(self):
        return iter(self._points)


class _FakeRingItem:
    def __init__(
        self,
        contains: bool,
        points: list[QPointF] | None = None,
        atom_ids: list[int] | None = None,
    ) -> None:
        self._polygon = _FakePolygon(contains, points)
        ring_atom_ids = list(atom_ids or [])
        self._data = {
            0: "ring",
            2: ring_atom_ids,
            9: {
                "kind": "ring",
                "points": [(point.x(), point.y()) for point in points or []],
                "atom_ids": ring_atom_ids,
                "color": None,
                "alpha": 0.0,
            },
        }

    def polygon(self) -> _FakePolygon:
        return self._polygon

    def data(self, key: int):
        return self._data.get(key)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        self.renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=20.0))
        self.viewport_center = QPointF(50.0, 60.0)
        self.runtime_state = canvas_runtime_state(
            smiles_input_state=CanvasSmilesInputState(),
            scene_items_state=CanvasSceneItemsState(),
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            graph_state=CanvasGraphState(),
            mark_registry=CanvasMarkRegistry(),
        )
        set_last_smiles_input_for(self, "before")
        self.added_graphics: list[int] = []
        self.carbon_dots: list[int] = []
        self.wrapper_label_calls: list[tuple] = []
        self.ring_points_calls: list[tuple[int, tuple[float, float], float | None]] = []
        self.regular_ring_radius_calls: list[int] = []
        self.record_calls: list[dict] = []
        self.redrawn_bonds: list[int] = []
        self.redrawn_connected: list[tuple[int, int | None]] = []
        self.recorded_bond_updates: list[tuple] = []
        self.scene_items: list[object] = []
        set_scene_item_collection_for(self, "ring_items", [])
        self.find_atom_near = Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        self.hit_testing_find_atom_near = Mock(return_value=None)
        self.bond_renderer = SimpleNamespace(add_bond_graphics=self._add_bond_graphics)
        self.services = canvas_runtime_services(
            hit_testing_service=SimpleNamespace(
                find_atom_near=self.hit_testing_find_atom_near
            ),
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                ensure_carbon_dot=self.ensure_carbon_dot,
            ),
            canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
            canvas_bond_mutation_service=SimpleNamespace(add_bond=self.add_bond),
            canvas_history_recording_service=SimpleNamespace(
                record_additions=self._record_additions,
                record_bond_update=self._record_bond_update,
            ),
            scene_item_controller=SimpleNamespace(
                attach_scene_item=self.attach_scene_item,
                remove_scene_item=self.remove_scene_item,
                restore_scene_item=self.restore_scene_item,
            ),
            graph_service=SimpleNamespace(
                bond_id_between=self.bond_id_between,
                bond_exists=self.bond_exists,
            ),
            move_controller=SimpleNamespace(
                redraw_bond=self.redraw_bond,
                redraw_connected_bonds=self.redraw_connected_bonds,
            ),
            canvas_ring_fill_scene_service=SimpleNamespace(
                create_ring_fill_item=self._create_ring_fill_item
            ),
        )
        self.services.structure.canvas_atom_mutation_service.remove_atom_only = (
            self.remove_atom_only
        )
        self.services.structure.canvas_atom_mutation_service.restore_atom_from_state = (
            self.restore_atom_from_state
        )
        self.services.structure.canvas_bond_mutation_service.remove_bond_by_id = (
            self.remove_bond_by_id
        )
        self.services.structure.canvas_bond_mutation_service.restore_bond_from_state = (
            self.restore_bond_from_state
        )
        self.services.structure.canvas_bond_mutation_service.trim_bonds_to_length = (
            self.trim_bonds_to_length
        )

    def viewport(self) -> _FakeViewport:
        return _FakeViewport(self.viewport_center)

    def mapToScene(self, point: QPointF) -> QPointF:
        return QPointF(point.x(), point.y())

    def add_atom(self, element: str, x: float, y: float) -> int:
        return self.model.add_atom(element, x, y)

    def add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        self.model.add_bond(a_id, b_id, order)
        return len(self.model.bonds) - 1

    def bond_id_between(self, a_id: int, b_id: int) -> int | None:
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (
                bond.a == b_id and bond.b == a_id
            ):
                return bond_id
        return None

    def bond_exists(self, a_id: int, b_id: int) -> bool:
        return self.bond_id_between(a_id, b_id) is not None

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {"a": bond.a, "b": bond.b, "order": bond.order, "style": bond.style}

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.added_graphics.append(bond_id)

    def redraw_bond(self, bond_id: int) -> None:
        self.redrawn_bonds.append(bond_id)

    def redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        self.redrawn_connected.append((atom_id, skip_bond_id))

    def ensure_carbon_dot(self, atom_id: int) -> None:
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
        self.wrapper_label_calls.append(
            (atom_id, text, clear_smiles, record, allow_merge, show_carbon)
        )

    def _record_additions(self, **kwargs) -> None:
        self.record_calls.append(kwargs)

    def _record_bond_update(self, *args) -> None:
        self.recorded_bond_updates.append(args)

    def scene(self):
        return SimpleNamespace(addItem=lambda item: self.scene_items.append(item))

    @property
    def ring_items(self):
        return ring_items_for(self)

    @ring_items.setter
    def ring_items(self, value) -> None:
        set_scene_item_collection_for(self, "ring_items", value)

    def attach_scene_item(self, item) -> None:
        self.scene_items.append(item)
        data = getattr(item, "data", None)
        if callable(data) and data(0) == "ring":
            self.ring_items.append(item)

    def remove_scene_item(self, item) -> None:
        if item in self.scene_items:
            self.scene_items.remove(item)
        if item in self.ring_items:
            self.ring_items.remove(item)

    def restore_scene_item(self, item) -> None:
        if item not in self.scene_items:
            self.scene_items.append(item)
        data = getattr(item, "data", None)
        if callable(data) and data(0) == "ring" and item not in self.ring_items:
            self.ring_items.append(item)

    def remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        del remove_marks
        self.model.atoms.pop(atom_id, None)

    def restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        self.model.atoms[atom_id] = Atom(
            state.get("element", "C"),
            state.get("x", 0.0),
            state.get("y", 0.0),
            color=state.get("color", "#000000"),
            explicit_label=bool(state.get("explicit_label", False)),
        )
        self.model.next_atom_id = max(self.model.next_atom_id, atom_id + 1)

    def remove_bond_by_id(self, bond_id: int) -> None:
        if 0 <= bond_id < len(self.model.bonds):
            self.model.bonds[bond_id] = None

    def restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        while len(self.model.bonds) <= bond_id:
            self.model.bonds.append(None)
        self.model.bonds[bond_id] = Bond(
            bond_state.get("a", 0),
            bond_state.get("b", 0),
            bond_state.get("order", 1),
            style=bond_state.get("style", "single"),
            color=bond_state.get("color", "#000000"),
        )

    def trim_bonds_to_length(self, length: int) -> None:
        del self.model.bonds[length:]

    def _create_ring_fill_item(self, points, atom_ids):
        return _FakeRingItem(False, list(points), list(atom_ids))

    def _benzene_ring_points(self, center, attach_atom_id=None, attach_bond_id=None):
        return (
            [QPointF(center.x() + i * 10.0, center.y()) for i in range(6)],
            [],
        )


def _service_for(canvas: _FakeCanvas) -> StructureBuildService:
    return StructureBuildService(
        canvas,
        hit_testing_service=canvas.services.selection.hit_testing_service,
        move_controller=canvas.services.interaction.move_controller,
        graph_service=canvas.services.graph_service,
    )


class StructureBuildServiceTest(unittest.TestCase):
    def test_run_recorded_build_captures_history_snapshot_and_added_scene_items(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        canvas.model.add_atom("C", 1.0, 2.0)
        canvas.model.add_atom("C", 3.0, 4.0)
        canvas.model.add_bond(0, 1, 1)

        added_scene_items = service.run_recorded_build(lambda: [{"kind": "note"}])

        self.assertEqual(added_scene_items, [{"kind": "note"}])
        self.assertIsNone(last_smiles_input_for(canvas))
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": "before",
                    "added_scene_items": [{"kind": "note"}],
                }
            ],
        )

    def test_recorded_build_helpers_preserve_explicit_smiles_input_and_skip_failed_actions(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        service.run_recorded_build(lambda: [], before_smiles_input="explicit")

        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "explicit",
                    "added_scene_items": [],
                }
            ],
        )

        canvas.record_calls.clear()
        set_last_smiles_input_for(canvas, "current")
        self.assertEqual(service.run_recorded_build(lambda: None), [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "current")

        def failed_build() -> None:
            service.committer.add_atom("C", 1.0, 2.0)
            return None

        self.assertEqual(service.run_recorded_build(failed_build), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.record_calls, [])

        self.assertFalse(
            service._run_recorded_additions_action(
                lambda: False, before_smiles_input="kept"
            )
        )
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "kept")

    def test_run_recorded_build_rolls_back_when_history_recording_fails(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        ring = _FakeRingItem(
            False,
            [QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)],
            [0],
        )
        canvas.services.document.canvas_history_recording_service.record_additions = (
            Mock(side_effect=RuntimeError("history"))
        )

        def action() -> list:
            service.committer.add_atom("C", 1.0, 2.0)
            canvas.attach_scene_item(ring)
            return [ring]

        with self.assertRaisesRegex(RuntimeError, "history"):
            service.run_recorded_build(action)

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.ring_items, [])
        self.assertEqual(canvas.scene_items, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_recorded_build_continues_model_rollback_after_bond_trim_mutates_then_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        history_error = RuntimeError("original history failure")
        trim_error = RuntimeError("bond trim rollback failure")
        canvas.services.document.canvas_history_recording_service.record_additions = (
            Mock(side_effect=history_error)
        )
        original_trim = canvas.trim_bonds_to_length

        def trim_then_raise(length: int) -> None:
            original_trim(length)
            raise trim_error

        canvas.services.structure.canvas_bond_mutation_service.trim_bonds_to_length = (
            trim_then_raise
        )

        def action() -> list:
            atom_a = service.committer.add_atom("C", 1.0, 2.0)
            atom_b = service.committer.add_atom("C", 21.0, 2.0)
            service.committer.add_bond(atom_a, atom_b)
            return []

        with self.assertRaises(RuntimeError) as raised:
            service.run_recorded_build(action)

        self.assertIs(raised.exception, history_error)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.model.next_atom_id, 0)
        self.assertEqual(last_smiles_input_for(canvas), "before")
        self.assertTrue(
            any(
                "bond trim rollback failure" in note for note in history_error.__notes__
            )
        )

    def _assert_recorded_build_cleanup_failure(self, fail_after_remove: bool) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        history_error = RuntimeError("original history failure")
        cleanup_error = RuntimeError("ring cleanup failure")
        canvas.services.document.canvas_history_recording_service.record_additions = (
            Mock(side_effect=history_error)
        )
        refresh_ring_geometry = Mock()
        canvas.services.scene_view.scene_item_controller.refresh_bond_geometry_for_ring_item = refresh_ring_geometry
        canvas.scene = lambda: SimpleNamespace(
            removeItem=lambda item: (
                canvas.scene_items.remove(item) if item in canvas.scene_items else None
            )
        )
        original_remove = canvas.remove_scene_item

        def failing_remove(item) -> None:
            if fail_after_remove:
                original_remove(item)
            raise cleanup_error

        canvas.services.scene_view.scene_item_controller.remove_scene_item = (
            failing_remove
        )
        ring = _FakeRingItem(
            False,
            [QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)],
            [0],
        )

        def action() -> list:
            service.committer.add_atom("C", 1.0, 2.0)
            canvas.attach_scene_item(ring)
            return [ring]

        with self.assertRaises(RuntimeError) as raised:
            service.run_recorded_build(action)

        self.assertIs(raised.exception, history_error)
        self.assertTrue(
            any("ring cleanup failure" in note for note in history_error.__notes__)
        )
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.ring_items, [])
        self.assertEqual(canvas.scene_items, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")
        refresh_ring_geometry.assert_called_once_with(ring)

    def test_recorded_build_preserves_original_error_and_finishes_rollback_after_scene_cleanup_failure(
        self,
    ) -> None:
        for fail_after_remove in (False, True):
            with self.subTest(fail_after_remove=fail_after_remove):
                self._assert_recorded_build_cleanup_failure(fail_after_remove)

    def test_explicit_abort_reports_cleanup_failure_after_restoring_model_and_smiles(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        snapshot = service.committer.begin_recorded_change()
        service.committer.add_atom("C", 1.0, 2.0)
        ring = _FakeRingItem(
            False,
            [QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)],
            [0],
        )
        canvas.attach_scene_item(ring)
        canvas.scene = lambda: SimpleNamespace(
            removeItem=lambda item: (
                canvas.scene_items.remove(item) if item in canvas.scene_items else None
            )
        )
        canvas.services.scene_view.scene_item_controller.remove_scene_item = Mock(
            side_effect=RuntimeError("cleanup failure")
        )
        canvas.services.scene_view.scene_item_controller.refresh_bond_geometry_for_ring_item = Mock()

        with self.assertRaisesRegex(RuntimeError, "cleanup failure"):
            service.committer.abort_recorded_change(snapshot)

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.ring_items, [])
        self.assertEqual(canvas.scene_items, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_recorded_build_exact_restore_runs_once_and_reports_failure(
        self,
    ) -> None:
        from chemvas.ui import structure_build_committer as committer_module

        canvas = _FakeCanvas()
        service = _service_for(canvas)
        snapshot = service.committer.begin_recorded_change()
        service.committer.add_atom("N", 1.0, 2.0)
        primary = RuntimeError("recorded build failed")
        restore_error = ValueError("build exact restore failed")
        result = RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=(restore_error,),
        )

        with mock.patch.object(
            committer_module,
            "restore_history_transaction_for_history",
            return_value=result,
        ) as restore:
            service.committer.abort_recorded_change(
                snapshot,
                original_error=primary,
            )

        restore.assert_called_once()
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(last_smiles_input_for(canvas), "before")
        self.assertTrue(
            any(
                "build exact restore failed" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

    def test_run_recorded_additions_action_rolls_back_when_history_recording_fails(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        canvas.services.document.canvas_history_recording_service.record_additions = (
            Mock(side_effect=RuntimeError("history"))
        )

        def action() -> bool:
            service.committer.add_atom("C", 1.0, 2.0)
            return True

        with self.assertRaisesRegex(RuntimeError, "history"):
            service._run_recorded_additions_action(action)

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_free_template_insert_history_undo_redo_includes_ring_items(self) -> None:
        canvas = _FakeCanvas()
        pushed_commands = []
        canvas.services.document.canvas_history_recording_service = (
            CanvasHistoryRecordingService(
                canvas,
                history_service=SimpleNamespace(push=pushed_commands.append),
            )
        )
        service = _service_for(canvas)
        canvas.services.structure.structure_build_service = service
        request = TemplateInsertRequest(
            ring_size=5, cursor_pos=(0.0, 0.0), ring_style="regular"
        )
        plan = TemplateInsertPlan(
            generator="free_regular_ring",
            ring_size=5,
            ring_style="regular",
            bond_id=None,
            radius_mode="regular_polygon",
        )
        resolution = TemplateInsertResolution(
            plan=plan,
            points=[(0.0, 0.0), (10.0, 0.0), (12.0, 8.0), (5.0, 14.0), (-2.0, 8.0)],
        )

        applied = apply_template_commit_resolution(
            canvas,
            request,
            plan,
            resolution,
            before_smiles_input="before",
        )

        self.assertTrue(applied)
        self.assertEqual(len(pushed_commands), 1)
        command = pushed_commands[0]
        self.assertIsInstance(command, CompositeCommand)
        self.assertEqual(len(canvas.model.atoms), 5)
        self.assertEqual(
            len([bond for bond in canvas.model.bonds if bond is not None]), 5
        )
        self.assertEqual(len(canvas.ring_items), 1)
        self.assertEqual(len(canvas.scene_items), 1)

        command.undo(canvas)

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.ring_items, [])
        self.assertEqual(canvas.scene_items, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

        command.redo(canvas)

        self.assertEqual(len(canvas.model.atoms), 5)
        self.assertEqual(
            len([bond for bond in canvas.model.bonds if bond is not None]), 5
        )
        self.assertEqual(len(canvas.ring_items), 1)
        self.assertEqual(len(canvas.scene_items), 1)

    def test_attached_template_insert_history_includes_exact_ring_item_for_all_generators(
        self,
    ) -> None:
        cases = (
            (
                "atom_regular_ring",
                "regular",
                [(0.0, 0.0), (20.0, 0.0), (25.0, 15.0), (10.0, 25.0), (-5.0, 15.0)],
            ),
            (
                "bond_regular_ring",
                "regular",
                [(-10.0, 0.0), (10.0, 0.0), (10.0, 20.0), (-10.0, 20.0)],
            ),
            (
                "bond_template_shape",
                "chair",
                [
                    (-10.0, 0.0),
                    (10.0, 0.0),
                    (20.0, 12.0),
                    (8.0, 24.0),
                    (-12.0, 20.0),
                    (-20.0, 8.0),
                ],
            ),
            (
                "bond_template_shape",
                "boat",
                [
                    (-10.0, 0.0),
                    (10.0, 0.0),
                    (20.0, 14.0),
                    (0.0, 22.0),
                    (-20.0, 14.0),
                    (0.0, 8.0),
                ],
            ),
        )

        for generator, ring_style, point_pairs in cases:
            with self.subTest(generator=generator, ring_style=ring_style):
                canvas = _FakeCanvas()
                points = [QPointF(x, y) for x, y in point_pairs]
                if generator == "atom_regular_ring":
                    atom_id = canvas.model.add_atom("C", points[0].x(), points[0].y())
                    bond_id = None
                else:
                    atom_id = None
                    left = canvas.model.add_atom("C", points[0].x(), points[0].y())
                    right = canvas.model.add_atom("C", points[1].x(), points[1].y())
                    bond_id = canvas.model.add_bond(left, right)
                base_atom_count = len(canvas.model.atoms)
                base_bond_count = len(canvas.model.bonds)
                pushed_commands = []
                canvas.services.document.canvas_history_recording_service = (
                    CanvasHistoryRecordingService(
                        canvas,
                        history_service=SimpleNamespace(push=pushed_commands.append),
                    )
                )
                service = _service_for(canvas)
                canvas.services.structure.structure_build_service = service
                request = TemplateInsertRequest(
                    ring_size=len(points),
                    cursor_pos=(0.0, 0.0),
                    bond_id=bond_id,
                    atom_id=atom_id,
                    ring_style=ring_style,
                )
                plan = TemplateInsertPlan(
                    generator=generator,
                    ring_size=len(points),
                    ring_style=ring_style,
                    bond_id=bond_id,
                    atom_id=atom_id,
                    template_shape=ring_style
                    if generator == "bond_template_shape"
                    else None,
                )
                resolution = TemplateInsertResolution(
                    plan=plan,
                    points=point_pairs,
                )

                applied = apply_template_commit_resolution(
                    canvas,
                    request,
                    plan,
                    resolution,
                    before_smiles_input="before",
                )

                self.assertTrue(applied)
                self.assertEqual(len(pushed_commands), 1)
                command = pushed_commands[0]
                self.assertIsInstance(command, CompositeCommand)
                add_scene_commands = [
                    child
                    for child in command.commands
                    if isinstance(child, AddSceneItemsCommand)
                ]
                self.assertEqual(len(add_scene_commands), 1)
                self.assertEqual(len(canvas.ring_items), 1)
                self.assertEqual(len(canvas.scene_items), 1)
                ring_item = canvas.ring_items[0]
                self.assertEqual(add_scene_commands[0].items, [ring_item])
                ring_atom_ids = ring_item.data(2)
                self.assertEqual(len(ring_atom_ids), len(points))
                self.assertEqual(set(ring_atom_ids), set(canvas.model.atoms))

                command.undo(canvas)

                self.assertEqual(len(canvas.model.atoms), base_atom_count)
                self.assertEqual(len(canvas.model.bonds), base_bond_count)
                self.assertEqual(canvas.ring_items, [])
                self.assertEqual(canvas.scene_items, [])

                command.redo(canvas)

                self.assertEqual(len(canvas.ring_items), 1)
                self.assertIs(canvas.ring_items[0], ring_item)
                self.assertEqual(ring_item.data(2), ring_atom_ids)
                self.assertEqual(len(canvas.model.atoms), len(points))
                self.assertEqual(
                    len([bond for bond in canvas.model.bonds if bond is not None]),
                    len(points),
                )

    def test_add_atom_with_merge_reuses_close_points(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        merge = [(7, 10.0, 10.0)]

        existing_id = service.add_atom_with_merge(QPointF(11.0, 11.0), "C", merge)
        created_id = service.add_atom_with_merge(QPointF(40.0, 40.0), "N", merge)

        self.assertEqual(existing_id, 7)
        self.assertEqual(created_id, 0)
        self.assertEqual(merge[-1], (0, 40.0, 40.0))

    def test_add_ring_from_points_builds_bonds_and_labels_hetero_atoms(self) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas.services.atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: (
                service_calls.append((atom_id, text, kwargs))
            )
        )

        atom_ids = _service_for(canvas).add_ring_from_points(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 8.0)],
            elements=["C", "N", "O"],
        )

        self.assertEqual(atom_ids, [0, 1, 2])
        self.assertEqual(len(canvas.model.bonds), 3)
        self.assertEqual(canvas.added_graphics, [0, 1, 2])
        self.assertEqual(
            service_calls,
            [
                (
                    1,
                    "N",
                    {
                        "clear_smiles": True,
                        "record": False,
                        "allow_merge": True,
                        "show_carbon": False,
                    },
                ),
                (
                    2,
                    "O",
                    {
                        "clear_smiles": True,
                        "record": False,
                        "allow_merge": True,
                        "show_carbon": False,
                    },
                ),
            ],
        )

    def test_add_ring_from_points_accepts_custom_bond_orders(self) -> None:
        canvas = _FakeCanvas()

        atom_ids = _service_for(canvas).add_ring_from_points(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(5.0, 8.0)],
            bond_orders=[2, 1, 2],
        )

        self.assertEqual(atom_ids, [0, 1, 2])
        self.assertEqual(
            [bond.order for bond in canvas.model.bonds if bond is not None], [2, 1, 2]
        )

    def test_add_linear_chain_and_render_model_use_atom_label_service(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        atom_ids = service.add_linear_chain(
            [QPointF(0.0, 0.0), QPointF(10.0, 0.0), QPointF(20.0, 0.0)],
            ["C", "N", "C"],
            [1, 2],
        )

        self.assertEqual(atom_ids, [0, 1, 2])
        self.assertEqual(canvas.added_graphics, [0, 1])
        self.assertEqual(
            canvas.wrapper_label_calls, [(1, "N", True, False, True, False)]
        )

        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0, explicit_label=False),
                1: Atom("C", 10.0, 0.0, explicit_label=True),
                2: Atom("Cl", 20.0, 0.0, explicit_label=False),
            },
            bonds=[Bond(0, 1, 1), None, Bond(1, 2, 1)],
        )
        canvas.added_graphics.clear()
        canvas.carbon_dots.clear()
        canvas.wrapper_label_calls.clear()

        service.render_model()

        self.assertEqual(canvas.added_graphics, [0, 2])
        self.assertEqual(canvas.carbon_dots, [0])
        self.assertEqual(
            canvas.wrapper_label_calls,
            [
                (1, "C", False, False, True, True),
                (2, "Cl", False, False, True, False),
            ],
        )

    def test_add_bond_between_points_creates_or_updates_bonds_with_history(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        result = service.add_bond_between_points(
            QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2
        )

        self.assertEqual(result, (0, 1))
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(
            (canvas.model.bonds[0].style, canvas.model.bonds[0].order), ("double", 2)
        )
        self.assertEqual(canvas.added_graphics, [0])
        self.assertEqual(canvas.redrawn_connected, [(0, 0), (1, 0)])
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

        canvas.record_calls.clear()
        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        updated = service.add_bond_between_points(
            QPointF(0.0, 0.0), QPointF(10.0, 0.0), "wedge", 1
        )

        self.assertEqual(updated, (0, 1))
        self.assertEqual(canvas.redrawn_bonds, [0])
        self.assertEqual(canvas.redrawn_connected[-2:], [(0, 0), (1, 0)])
        self.assertEqual(len(canvas.recorded_bond_updates), 1)
        self.assertEqual(canvas.record_calls, [])

    def test_add_bond_between_points_uses_hit_testing_service_for_snap_lookup(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(side_effect=[None, None])
        )
        canvas.services.selection.hit_testing_service = hit_testing_service
        canvas.find_atom_near = Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        service = _service_for(canvas)

        result = service.add_bond_between_points(
            QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
        )

        self.assertEqual(result, (0, 1))
        self.assertEqual(
            hit_testing_service.find_atom_near.call_args_list,
            [mock.call(0.0, 0.0, 2.0), mock.call(10.0, 0.0, 2.0)],
        )
        canvas.find_atom_near.assert_not_called()

    def test_add_bond_between_points_uses_injected_hit_testing_over_canvas_aliases(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(side_effect=[None, None])
        )
        registry_hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(
                side_effect=AssertionError("registry service should not be used")
            )
        )
        direct_alias_hit_testing_service = SimpleNamespace(
            find_atom_near=Mock(
                side_effect=AssertionError("direct alias should not be used")
            )
        )
        canvas.services.selection.hit_testing_service = registry_hit_testing_service
        canvas.hit_testing = direct_alias_hit_testing_service
        canvas.find_atom_near = Mock(
            side_effect=AssertionError("canvas facade should not be used")
        )
        service = StructureBuildService(
            canvas,
            hit_testing_service=hit_testing_service,
            move_controller=canvas.services.interaction.move_controller,
            graph_service=canvas.services.graph_service,
        )

        result = service.add_bond_between_points(
            QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
        )

        self.assertEqual(result, (0, 1))
        self.assertEqual(
            hit_testing_service.find_atom_near.call_args_list,
            [mock.call(0.0, 0.0, 2.0), mock.call(10.0, 0.0, 2.0)],
        )
        registry_hit_testing_service.find_atom_near.assert_not_called()
        direct_alias_hit_testing_service.find_atom_near.assert_not_called()
        canvas.find_atom_near.assert_not_called()

    def test_add_bond_between_points_ignores_short_drag_before_mutation(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        result = service.add_bond_between_points(
            QPointF(0.0, 0.0), QPointF(1.5, 1.0), "single", 1
        )

        self.assertIsNone(result)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.record_calls, [])
        canvas.hit_testing_find_atom_near.assert_not_called()

    def test_add_bond_between_points_rolls_back_new_bond_if_graphics_raise(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        service.committer.add_bond_graphics = Mock(
            side_effect=RuntimeError("graphics failed")
        )

        with self.assertRaisesRegex(RuntimeError, "graphics failed"):
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
            )

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_add_bond_between_points_restores_existing_bond_if_redraw_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 10.0, 0.0)},
            bonds=[Bond(0, 1, 1, style="single", color="#123456")],
        )
        canvas.model.next_atom_id = 2
        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        canvas.services.interaction.move_controller.redraw_bond = Mock(
            side_effect=RuntimeError("redraw failed")
        )
        service = _service_for(canvas)

        with self.assertRaisesRegex(RuntimeError, "redraw failed"):
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2
            )

        bond = canvas.model.bonds[0]
        self.assertIsNotNone(bond)
        self.assertEqual((bond.order, bond.style, bond.color), (1, "single", "#123456"))
        self.assertEqual(canvas.recorded_bond_updates, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_add_bond_between_points_redraws_restored_existing_bond_if_connected_redraw_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 10.0, 0.0)},
            bonds=[Bond(0, 1, 1, style="single", color="#123456")],
        )
        canvas.model.next_atom_id = 2
        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        redrawn_states: list[tuple[int, str]] = []

        def redraw_bond(bond_id: int) -> None:
            bond = canvas.model.bonds[bond_id]
            assert bond is not None
            redrawn_states.append((bond.order, bond.style))

        canvas.services.interaction.move_controller.redraw_bond = Mock(
            side_effect=redraw_bond
        )
        canvas.services.interaction.move_controller.redraw_connected_bonds = Mock(
            side_effect=RuntimeError("connected failed")
        )
        service = _service_for(canvas)

        with self.assertRaisesRegex(RuntimeError, "connected failed"):
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2
            )

        bond = canvas.model.bonds[0]
        self.assertIsNotNone(bond)
        self.assertEqual((bond.order, bond.style, bond.color), (1, "single", "#123456"))
        self.assertEqual(redrawn_states, [(2, "double"), (1, "single")])
        self.assertEqual(canvas.recorded_bond_updates, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_add_bond_between_points_redraws_restored_connected_bonds_if_later_redraw_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
                2: Atom("C", -10.0, 0.0),
                3: Atom("C", 20.0, 0.0),
            },
            bonds=[
                Bond(0, 1, 1, style="single", color="#123456"),
                Bond(0, 2, 1, style="single"),
                Bond(1, 3, 1, style="single"),
            ],
        )
        canvas.model.next_atom_id = 4
        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        redrawn_bond_states: list[tuple[int, str]] = []
        redrawn_connected_states: list[tuple[int, int, str]] = []
        failed_once = False

        def main_bond_state() -> tuple[int, str]:
            bond = canvas.model.bonds[0]
            assert bond is not None
            return bond.order, bond.style

        def redraw_bond(bond_id: int) -> None:
            assert bond_id == 0
            redrawn_bond_states.append(main_bond_state())

        def redraw_connected_bonds(
            atom_id: int, skip_bond_id: int | None = None
        ) -> None:
            nonlocal failed_once
            assert skip_bond_id == 0
            order, style = main_bond_state()
            redrawn_connected_states.append((atom_id, order, style))
            if atom_id == 1 and not failed_once:
                failed_once = True
                raise RuntimeError("connected failed")

        canvas.services.interaction.move_controller.redraw_bond = Mock(
            side_effect=redraw_bond
        )
        canvas.services.interaction.move_controller.redraw_connected_bonds = Mock(
            side_effect=redraw_connected_bonds
        )
        service = _service_for(canvas)

        with self.assertRaisesRegex(RuntimeError, "connected failed"):
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "double", 2
            )

        bond = canvas.model.bonds[0]
        self.assertIsNotNone(bond)
        self.assertEqual((bond.order, bond.style, bond.color), (1, "single", "#123456"))
        self.assertEqual(redrawn_bond_states, [(2, "double"), (1, "single")])
        self.assertEqual(
            redrawn_connected_states,
            [
                (0, 2, "double"),
                (1, 2, "double"),
                (0, 1, "single"),
                (1, 1, "single"),
            ],
        )
        self.assertEqual(canvas.recorded_bond_updates, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_add_benzene_ring_builds_ring_item_and_records_scene_item(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        ring_item = service.add_benzene_ring(QPointF(5.0, 6.0))

        self.assertEqual(ring_item, canvas.ring_items[0])
        self.assertEqual(canvas.scene_items, [ring_item])
        self.assertEqual(len(canvas.model.bonds), 6)
        self.assertEqual(canvas.added_graphics, [0, 1, 2, 3, 4, 5])
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [ring_item],
                }
            ],
        )

    def test_benzene_ring_points_prefers_bond_then_atom_then_free_geometry(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        service = _service_for(canvas)
        service.regular_ring_points_for_bond = Mock(
            return_value=([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)])
        )
        service.regular_ring_points_for_atom = Mock(
            return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)])
        )

        bond_result = service.benzene_ring_points(
            QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0
        )
        atom_result = service.benzene_ring_points(
            QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=9
        )

        self.assertEqual(bond_result, ([QPointF(1.0, 2.0)], [(1, 0.0, 0.0)]))
        self.assertEqual(atom_result, ([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)]))
        service.regular_ring_points_for_bond.assert_called_once_with(
            6, 0, QPointF(5.0, 6.0)
        )
        service.regular_ring_points_for_atom.assert_called_once_with(6, 1)

    def test_benzene_ring_points_treats_failed_valid_bond_geometry_as_terminal(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(1, 2, 1)],
        )
        service = _service_for(canvas)
        service.regular_ring_points_for_bond = Mock(return_value=None)
        service.regular_ring_points_for_atom = Mock(
            return_value=([QPointF(3.0, 4.0)], [(1, 0.0, 0.0)])
        )

        self.assertIsNone(
            service.benzene_ring_points(
                QPointF(5.0, 6.0), attach_atom_id=1, attach_bond_id=0
            )
        )
        service.regular_ring_points_for_atom.assert_not_called()

    def test_benzene_ring_points_blocks_free_ring_inside_existing_ring_and_uses_pure_fallback(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(True)])
        service = _service_for(canvas)

        self.assertIsNone(service.benzene_ring_points(QPointF(5.0, 6.0)))

        set_scene_item_collection_for(canvas, "ring_items", [_FakeRingItem(False)])
        with mock.patch(
            "chemvas.ui.structure_benzene_build_service.compute_free_benzene_ring_points",
            return_value=[(1.0, 2.0), (3.0, 4.0)],
        ) as free_ring:
            result = service.benzene_ring_points(QPointF(7.0, 8.0))

        self.assertEqual(result, ([QPointF(1.0, 2.0), QPointF(3.0, 4.0)], []))
        free_ring.assert_called_once_with((7.0, 8.0), bond_length=20.0)

    def test_sprout_bond_and_benzene_helpers_delegate_with_expected_points(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(atoms={3: Atom("C", 4.0, 5.0)}, bonds=[])
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.add_bond_between_points = Mock(return_value=(3, 4))
        service.add_benzene_ring = Mock(return_value="ring")

        result = service.sprout_bond_from_atom(3, style="double", order=2, cyclic=True)
        ring = service.sprout_benzene_from_atom(3)

        self.assertEqual(result, (3, 4))
        self.assertEqual(ring, "ring")
        service.add_bond_between_points.assert_called_once_with(
            QPointF(4.0, 5.0),
            QPointF(20.0, 0.0),
            "double",
            2,
        )
        service.add_benzene_ring.assert_called_once_with(
            QPointF(4.0, 5.0), attach_atom_id=3
        )

    def test_sprout_and_fuse_helpers_return_early_when_geometry_resolution_fails(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(0, 1, 1)],
        )
        service = _service_for(canvas)
        service.default_bond_endpoint = Mock(return_value=QPointF(30.0, 0.0))
        service.add_bond_between_points = Mock()
        service.add_ring_from_points = Mock()

        service.sprout_bond_endpoint = Mock(return_value=None)
        self.assertIsNone(service.sprout_bond_from_atom(0, style="single", order=1))
        service.sprout_acetyl_from_atom(0)
        service.add_bond_between_points.assert_not_called()
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

        set_last_smiles_input_for(canvas, "before")
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.default_bond_endpoint = Mock(return_value=None)
        service.sprout_acetyl_from_atom(0)
        service.add_bond_between_points.assert_not_called()
        self.assertEqual(sorted(canvas.model.atoms), [0, 1])
        self.assertEqual(len(canvas.model.bonds), 1)
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

        service.regular_ring_points_for_bond = Mock(return_value=None)
        service.template_points_for_bond = Mock(return_value=None)
        service.fuse_regular_ring_to_bond(99, 6)
        service.fuse_regular_ring_to_bond(0, 6)
        service.fuse_chair_to_bond(99)
        service.fuse_chair_to_bond(0)
        service.add_ring_from_points.assert_not_called()

    def test_sprout_acetyl_from_atom_builds_three_bonds_and_labels_oxygen(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
            },
            bonds=[],
        )
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.default_bond_endpoint = Mock(
            side_effect=[QPointF(20.0, 10.0), QPointF(20.0, -10.0)]
        )
        service.add_bond_between_points = Mock()

        service.sprout_acetyl_from_atom(0)

        service.add_bond_between_points.assert_not_called()
        self.assertEqual(
            {
                atom_id: (atom.element, atom.x, atom.y)
                for atom_id, atom in canvas.model.atoms.items()
            },
            {
                0: ("C", 0.0, 0.0),
                1: ("C", 20.0, 0.0),
                2: ("O", 20.0, 10.0),
                3: ("C", 20.0, -10.0),
            },
        )
        self.assertEqual(
            [
                (bond.a, bond.b, bond.order, bond.style)
                for bond in canvas.model.bonds
                if bond is not None
            ],
            [
                (0, 1, 1, "single"),
                (1, 2, 2, "double"),
                (1, 3, 1, "single"),
            ],
        )
        self.assertEqual(canvas.added_graphics, [0, 1, 2])
        self.assertEqual(
            canvas.wrapper_label_calls, [(2, "O", True, False, True, True)]
        )
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 1,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

    def test_sprout_dimethyl_from_atom_builds_two_methyls_in_one_record(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
            },
            bonds=[],
        )
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(
            side_effect=[QPointF(20.0, 0.0), QPointF(20.0, 10.0)]
        )
        service.add_bond_between_points = Mock()

        service.sprout_dimethyl_from_atom(0)

        service.add_bond_between_points.assert_not_called()
        self.assertEqual(
            {
                atom_id: (atom.element, atom.x, atom.y)
                for atom_id, atom in canvas.model.atoms.items()
            },
            {
                0: ("C", 0.0, 0.0),
                1: ("C", 20.0, 0.0),
                2: ("C", 20.0, 10.0),
            },
        )
        self.assertEqual(
            [
                (bond.a, bond.b, bond.order, bond.style)
                for bond in canvas.model.bonds
                if bond is not None
            ],
            [
                (0, 1, 1, "single"),
                (0, 2, 1, "single"),
            ],
        )
        self.assertEqual(canvas.added_graphics, [0, 1])
        self.assertEqual(len(canvas.record_calls), 1)

    def test_sprout_dimethyl_from_atom_keeps_first_methyl_when_second_endpoint_missing(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
            },
            bonds=[],
        )
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(side_effect=[QPointF(20.0, 0.0), None])
        service.add_bond_between_points = Mock()

        service.sprout_dimethyl_from_atom(0)

        service.add_bond_between_points.assert_not_called()
        self.assertEqual(sorted(canvas.model.atoms), [0, 1])
        self.assertEqual(
            [
                (bond.a, bond.b, bond.order, bond.style)
                for bond in canvas.model.bonds
                if bond is not None
            ],
            [(0, 1, 1, "single")],
        )
        self.assertEqual(len(canvas.record_calls), 1)

    def test_sprout_acetyl_from_atom_rolls_back_if_recorded_build_raises(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
            },
            bonds=[],
        )
        canvas.model.next_atom_id = 1
        service = _service_for(canvas)
        service.sprout_bond_endpoint = Mock(return_value=QPointF(20.0, 0.0))
        service.committer.add_bond_graphics = Mock(
            side_effect=RuntimeError("graphics failed")
        )

        with self.assertRaisesRegex(RuntimeError, "graphics failed"):
            service.sprout_acetyl_from_atom(0)

        self.assertEqual(
            {
                atom_id: (atom.element, atom.x, atom.y)
                for atom_id, atom in canvas.model.atoms.items()
            },
            {0: ("C", 0.0, 0.0)},
        )
        self.assertEqual(canvas.model.next_atom_id, 1)
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_fuse_benzene_to_bond_uses_midpoint_and_skips_missing_geometry(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 4.0),
            },
            bonds=[Bond(0, 1, 1), None],
        )
        service = _service_for(canvas)
        service.add_benzene_ring = Mock(return_value="ring")

        self.assertEqual(service.fuse_benzene_to_bond(0), "ring")
        self.assertIsNone(service.fuse_benzene_to_bond(1))
        service.add_benzene_ring.assert_called_once_with(
            QPointF(5.0, 2.0), attach_bond_id=0
        )

    def test_add_bond_between_points_returns_none_for_collapsed_or_invalid_paths(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 10.0, 0.0)}, bonds=[]
        )
        service = _service_for(canvas)

        self.assertIsNone(
            service.add_bond_between_points(
                QPointF(1.0, 2.0), QPointF(1.0, 2.0), "single", 1
            )
        )

        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 0])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        self.assertIsNone(
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
            )
        )

        canvas.hit_testing_find_atom_near = Mock(side_effect=[0, 1])
        canvas.services.selection.hit_testing_service.find_atom_near = (
            canvas.hit_testing_find_atom_near
        )
        canvas.model.bonds = [None]
        canvas.services.graph_service.bond_id_between = Mock(return_value=0)
        self.assertIsNone(
            service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
            )
        )
        self.assertEqual(last_smiles_input_for(canvas), "before")
        self.assertEqual(canvas.record_calls, [])

        failed_canvas = _FakeCanvas()
        failed_service = _service_for(failed_canvas)
        failed_canvas.services.structure.canvas_bond_mutation_service.add_bond = Mock(
            return_value=0
        )
        self.assertIsNone(
            failed_service.add_bond_between_points(
                QPointF(0.0, 0.0), QPointF(10.0, 0.0), "single", 1
            )
        )
        self.assertEqual(failed_canvas.model.atoms, {})
        self.assertEqual(failed_canvas.model.bonds, [])
        self.assertEqual(failed_canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(failed_canvas), "before")

    def test_ring_growth_helpers_record_only_when_geometry_resolves(self) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()
        service.regular_ring_points_for_atom = Mock(return_value=None)

        service.sprout_regular_ring_from_atom(7, 6)

        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")
        service.add_ring_from_points.assert_not_called()

        set_last_smiles_input_for(canvas, "before")
        service.regular_ring_points_for_atom = Mock(
            return_value=([QPointF(0.0, 0.0), QPointF(1.0, 1.0)], [(7, 1.0, 2.0)])
        )
        service.sprout_regular_ring_from_atom(7, 6)

        service.add_ring_from_points.assert_called_once_with(
            [QPointF(0.0, 0.0), QPointF(1.0, 1.0)],
            merge=[(7, 1.0, 2.0)],
        )
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                }
            ],
        )

    def test_bond_fuse_helpers_build_templates_and_record_history(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
            },
            bonds=[Bond(0, 1, 1)],
        )
        service = _service_for(canvas)
        service.add_ring_from_points = Mock()
        service.regular_ring_points_for_bond = Mock(
            return_value=([QPointF(5.0, 0.0), QPointF(6.0, -1.0)], [(0, 5.0, 0.0)])
        )
        service.template_points_for_bond = Mock(
            return_value=([QPointF(6.0, 2.0), QPointF(8.0, -4.0)], [(0, 5.0, 0.0)])
        )
        service.cyclohexane_chair_points = Mock(
            return_value=[QPointF(1.0, 2.0), QPointF(3.0, -4.0)]
        )

        service.fuse_regular_ring_to_bond(0, 5)
        service.fuse_chair_to_bond(0, mirrored=True)

        first_midpoint = service.regular_ring_points_for_bond.call_args.args[2]
        self.assertEqual((first_midpoint.x(), first_midpoint.y()), (5.0, 0.0))
        chair_points = service.template_points_for_bond.call_args.args[0]
        self.assertEqual(
            [(point.x(), point.y()) for point in chair_points],
            [(1.0, -2.0), (3.0, 4.0)],
        )
        second_midpoint = service.template_points_for_bond.call_args.args[2]
        self.assertEqual((second_midpoint.x(), second_midpoint.y()), (5.0, 0.0))
        self.assertEqual(
            service.add_ring_from_points.call_args_list,
            [
                mock.call(
                    [QPointF(5.0, 0.0), QPointF(6.0, -1.0)], merge=[(0, 5.0, 0.0)]
                ),
                mock.call(
                    [QPointF(6.0, 2.0), QPointF(8.0, -4.0)], merge=[(0, 5.0, 0.0)]
                ),
            ],
        )
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": "before",
                },
                {
                    "before_next_atom_id": 2,
                    "before_bond_count": 1,
                    "before_smiles_input": None,
                },
            ],
        )

    def test_add_benzene_ring_handles_failed_geometry_and_preexisting_ring_bonds(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        service.benzene_ring_points = Mock(return_value=None)
        self.assertIsNone(service.add_benzene_ring(QPointF(5.0, 6.0)))
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "before",
                    "added_scene_items": [],
                }
            ],
        )

        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={index: Atom("C", float(index), 0.0) for index in range(6)},
            bonds=[Bond(0, 1, 1)],
        )
        service = _service_for(canvas)
        points = [QPointF(float(index), float(index % 2)) for index in range(6)]
        service.benzene_ring_points = Mock(return_value=(points, []))
        service.add_atom_with_merge = Mock(side_effect=list(range(6)))

        ring_item = service.add_benzene_ring(QPointF(1.0, 2.0))

        self.assertIsNotNone(ring_item)
        assert ring_item is not None
        self.assertEqual(len(canvas.model.bonds), 6)
        self.assertEqual(
            sum(
                1 for bond in canvas.model.bonds if bond is not None and bond.order == 2
            ),
            3,
        )
        self.assertEqual(canvas.added_graphics, [1, 2, 3, 4, 5])
        self.assertEqual(canvas.scene_items, [ring_item])

    def test_add_benzene_ring_fused_to_existing_benzene_single_edges_preserves_valid_valence(
        self,
    ) -> None:
        for bond_id in (1, 3, 5):
            with self.subTest(bond_id=bond_id):
                canvas = _FakeCanvas()
                service = _service_for(canvas)
                service.add_benzene_ring(QPointF(50.0, 60.0))

                service.fuse_benzene_to_bond(bond_id)

                bonds = [bond for bond in canvas.model.bonds if bond is not None]
                bond_pairs = [frozenset((bond.a, bond.b)) for bond in bonds]
                order_sums = {atom_id: 0 for atom_id in canvas.model.atoms}
                for built_bond in bonds:
                    order_sums[built_bond.a] += built_bond.order
                    order_sums[built_bond.b] += built_bond.order

                self.assertEqual(len(canvas.model.atoms), 10)
                self.assertEqual(len(bonds), 11)
                self.assertEqual(len(bond_pairs), len(set(bond_pairs)))
                self.assertEqual(
                    sum(1 for built_bond in bonds if built_bond.order == 2), 5
                )
                self.assertLessEqual(max(order_sums.values()), 4)

    def test_add_benzene_ring_fused_to_existing_double_bond_counts_shared_double_once(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        atom_a_id = canvas.model.add_atom("C", 0.0, 0.0)
        atom_b_id = canvas.model.add_atom("C", 20.0, 0.0)
        bond_id = canvas.model.add_bond(atom_a_id, atom_b_id, 2)

        service.add_benzene_ring(QPointF(10.0, 20.0), attach_bond_id=bond_id)

        bonds = [bond for bond in canvas.model.bonds if bond is not None]
        order_sums = {atom_id: 0 for atom_id in canvas.model.atoms}
        for built_bond in bonds:
            order_sums[built_bond.a] += built_bond.order
            order_sums[built_bond.b] += built_bond.order

        self.assertEqual(len(canvas.model.atoms), 6)
        self.assertEqual(len(bonds), 6)
        self.assertEqual(sum(1 for bond in bonds if bond.order == 2), 3)
        self.assertLessEqual(max(order_sums.values()), 4)

    def test_fuse_benzene_to_existing_triple_bond_is_rejected_without_mutation(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = _service_for(canvas)
        atom_a_id = canvas.model.add_atom("C", 0.0, 0.0)
        atom_b_id = canvas.model.add_atom("C", 20.0, 0.0)
        bond_id = canvas.model.add_bond(atom_a_id, atom_b_id, 3)

        self.assertIsNone(
            service.benzene_ring_points(QPointF(10.0, 10.0), attach_bond_id=bond_id)
        )
        self.assertIsNone(service.fuse_benzene_to_bond(bond_id))

        self.assertEqual(len(canvas.model.atoms), 2)
        self.assertEqual(
            [
                (bond.a, bond.b, bond.order)
                for bond in canvas.model.bonds
                if bond is not None
            ],
            [(atom_a_id, atom_b_id, 3)],
        )
        self.assertEqual(canvas.added_graphics, [])
        self.assertEqual(canvas.scene_items, [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")


if __name__ == "__main__":
    unittest.main()
