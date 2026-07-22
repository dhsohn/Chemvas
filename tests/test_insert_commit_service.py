import unittest
from types import SimpleNamespace
from unittest import mock

from chemvas.core.history import HistoryTransactionRestoreResult
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.features.insertion import (
    SmilesAtomPlacement,
    SmilesBondPlacement,
    SmilesCommitPlan,
    SmilesMarkPlacement,
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
)
from chemvas.ui import insert_commit_rollback as insert_rollback_module
from chemvas.ui import (
    insert_smiles_commit_service as insert_smiles_commit_service_module,
)
from chemvas.ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_runtime_services import CanvasRuntimeServices
from chemvas.ui.canvas_scene_items_state import (
    append_scene_item_for,
    remove_scene_item_from_collection_for,
    ring_items_for,
)
from chemvas.ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.insert_commit_rollback import (
    capture_smiles_input_restore_authority,
    rollback_insert_mutation,
)
from chemvas.ui.insert_commit_service import InsertCommitService
from chemvas.ui.insert_smiles_commit_service import apply_smiles_commit_plan
from chemvas.ui.insert_template_commit_service import apply_template_commit_resolution
from chemvas.ui.structure_insert_access import (
    add_insert_ring_from_points_for,
    rollback_insert_mutation_for,
)
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF
from PyQt6.QtWidgets import QApplication

from tests.runtime_services import canvas_runtime_services


def _points(count: int, *, start: float = 1.0) -> list[tuple[float, float]]:
    return [(start + 2.0 * index, start + 2.0 * index + 1.0) for index in range(count)]


class _BrokenAddNoteInterrupt(KeyboardInterrupt):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


class _BrokenAddNoteSystemExit(SystemExit):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


class _FakeRingItem:
    def __init__(self, points, atom_ids: list[int]) -> None:
        self._data = {
            0: "ring",
            2: list(atom_ids),
            9: {
                "kind": "ring",
                "points": [(point.x(), point.y()) for point in points],
                "atom_ids": list(atom_ids),
                "color": None,
                "alpha": 0.0,
            },
        }

    def data(self, key: int):
        return self._data.get(key)


class _FakeCanvas:
    def __init__(self) -> None:
        self.model = MoleculeModel()
        set_last_smiles_input_for(self, "before")
        self.record_calls: list[dict] = []
        self.add_atom_calls: list[tuple[str, float, float]] = []
        self.add_bond_calls: list[tuple[int, int, int]] = []
        self.added_graphics: list[int] = []
        self.labels: list[tuple[int, str, bool, bool]] = []
        self.carbon_dots: list[int] = []
        self.mark_calls: list[tuple[int, float, float, str | None, bool]] = []
        self.created_marks: list[object] = []
        self.ring_calls: list[list[tuple[float, float]]] = []
        self.benzene_calls: list[tuple[float, float, int | None]] = []
        self.bond_renderer = SimpleNamespace(add_bond_graphics=self._add_bond_graphics)
        self.services = CanvasRuntimeServices(
            atom_label_service=SimpleNamespace(
                add_or_update_atom_label=self.add_or_update_atom_label,
                ensure_carbon_dot=self.ensure_carbon_dot,
            ),
            document=SimpleNamespace(
                canvas_history_recording_service=SimpleNamespace(
                    record_additions=self._record_additions
                )
            ),
            graph=SimpleNamespace(
                canvas_graph_service=SimpleNamespace(bond_exists=self.bond_exists)
            ),
            input=SimpleNamespace(),
            interaction=SimpleNamespace(),
            scene_view=SimpleNamespace(
                canvas_ring_fill_scene_service=SimpleNamespace(
                    create_ring_fill_item=self.create_ring_fill_item,
                ),
                scene_item_controller=SimpleNamespace(
                    attach_scene_item=self.attach_scene_item,
                    remove_scene_item=self.remove_scene_item,
                    restore_scene_item=self.attach_scene_item,
                ),
            ),
            handles=SimpleNamespace(),
            hover=SimpleNamespace(),
            scene_decoration=SimpleNamespace(
                canvas_mark_scene_service=SimpleNamespace(
                    add_mark_for_atom=self.add_mark_for_atom
                )
            ),
            scene_operations=SimpleNamespace(),
            selection=SimpleNamespace(),
            structure=SimpleNamespace(
                canvas_atom_mutation_service=SimpleNamespace(add_atom=self.add_atom),
                canvas_bond_mutation_service=SimpleNamespace(add_bond=self.add_bond),
                structure_build_service=SimpleNamespace(
                    add_atom_with_merge=self.add_atom_with_merge,
                    add_ring_from_points=self.add_ring_from_points,
                    add_benzene_ring=self.add_benzene_ring,
                ),
            ),
            tooling=SimpleNamespace(),
            history_service=None,
        )

    def add_atom(self, element: str, x: float, y: float) -> int:
        self.add_atom_calls.append((element, x, y))
        return self.model.add_atom(element, x, y)

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        self.add_bond_calls.append((a, b, order))
        return self.model.add_bond(a, b, order)

    def _add_bond_graphics(self, bond_id: int) -> None:
        self.added_graphics.append(bond_id)

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
        self.labels.append((atom_id, text, clear_smiles, record))

    def _record_additions(self, **kwargs) -> None:
        self.record_calls.append(kwargs)

    def add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None = None,
        record: bool = True,
    ):
        self.mark_calls.append((atom_id, click_pos.x(), click_pos.y(), kind, record))
        item = object()
        self.created_marks.append(item)
        return item

    def remove_scene_item(self, item) -> None:
        if item in self.created_marks:
            self.created_marks.remove(item)
        remove_scene_item_from_collection_for(self, "ring_items", item)

    def attach_scene_item(self, item) -> None:
        if item.data(0) == "ring":
            append_scene_item_for(self, "ring_items", item)

    def create_ring_fill_item(self, points, atom_ids: list[int]):
        return _FakeRingItem(points, atom_ids)

    def bond_exists(self, a_id: int, b_id: int) -> bool:
        return any(
            (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id)
            for bond in self.model.bonds
        )

    def add_atom_with_merge(self, point, element: str, merge: list) -> int:
        self.ring_calls.append(list(merge))
        return self.add_atom(element, point.x(), point.y())

    def add_ring_from_points(self, points, elements=None, merge=None):
        self.ring_calls.append([tuple(entry) for entry in (merge or [])])
        atom_ids = []
        for point in points:
            atom_ids.append(self.add_atom("C", point.x(), point.y()))
        before_bond_count = len(self.model.bonds)
        for index in range(len(atom_ids)):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            # Mirror production behavior: bond creation deduplicates instead
            # of pushing duplicate pairs into the model.
            if not self.bond_exists(a_id, b_id):
                self.add_bond(a_id, b_id)
        for bond_id in range(before_bond_count, len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        return atom_ids

    def _benzene_ring_points(self, center, attach_atom_id=None, attach_bond_id=None):
        self.benzene_calls.append((center.x(), center.y(), attach_bond_id))
        return [(center.x() + 1.0, center.y() + 1.0)] * 6, []

    def add_benzene_ring(
        self, center, attach_atom_id=None, attach_bond_id=None, before_smiles_input=None
    ):
        set_last_smiles_input_for(self, None)
        points = [(center.x() + 1.0, center.y() + 1.0)] * 6
        atom_ids = []
        for point_x, point_y in points:
            atom_ids.append(self.add_atom("C", point_x, point_y))
        for index in range(len(atom_ids)):
            self.add_bond(atom_ids[index], atom_ids[(index + 1) % len(atom_ids)])
        for bond_id in range(
            len(self.model.bonds) - len(atom_ids), len(self.model.bonds)
        ):
            self._add_bond_graphics(bond_id)
        self._record_additions(
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input=before_smiles_input,
            added_scene_items=[],
        )


class _DetachableSourceId:
    """SMILES source id that compares equal to a same-label twin during plan
    validation, then "detaches" (compares equal to nothing but itself) once the
    atoms have been created.

    The earlier ``_MutableSourceId`` bumped ``hash(label)`` by one and relied on
    the mutated key landing on an empty dict bucket so the later ``id_map``
    lookup would miss. Whether it actually missed depended on the bucket layout,
    i.e. on ``PYTHONHASHSEED`` -- so this test was flaky. Driving the miss
    through equality instead is deterministic: once detached, no stored key is
    identity- or ``==``-equal to the lookup key, so ``dict.get`` must return
    ``None`` regardless of hash seed or table layout.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.attached = True

    def __hash__(self) -> int:
        return hash(self.label)

    def __eq__(self, other) -> bool:
        if self is other:
            return True
        if not isinstance(other, _DetachableSourceId):
            return NotImplemented
        return self.attached and other.attached and self.label == other.label


class _DetachingCanvas(_FakeCanvas):
    def __init__(self, key_to_detach: _DetachableSourceId) -> None:
        super().__init__()
        self._key_to_detach = key_to_detach
        self._add_atom_count = 0

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = super().add_atom(element, x, y)
        self._add_atom_count += 1
        if self._add_atom_count == 2:
            self._key_to_detach.attached = False
        return atom_id


class InsertCommitServiceTest(unittest.TestCase):
    def test_smiles_commit_capture_failure_restores_poisoned_input_authority(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        set_last_smiles_input_for(canvas, "old")
        primary = SystemExit("renderer style capture terminated")

        class PoisoningRenderer:
            @property
            def style(self):
                set_last_smiles_input_for(canvas, "poisoned-by-capture")
                raise primary

        canvas.renderer = PoisoningRenderer()
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[SmilesAtomPlacement(0, "N", 1.0, 2.0, "#111111", True)],
            bonds=[],
        )

        with self.assertRaises(SystemExit) as raised:
            apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        self.assertIs(raised.exception, primary)
        self.assertEqual(last_smiles_input_for(canvas), "old")
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.next_atom_id, 0)

    def test_benzene_capture_failure_restores_poisoned_input_authority(self) -> None:
        canvas = _FakeCanvas()
        set_last_smiles_input_for(canvas, "old")
        primary = KeyboardInterrupt("benzene style capture interrupted")

        class PoisoningRenderer:
            @property
            def style(self):
                set_last_smiles_input_for(canvas, "poisoned-by-capture")
                raise primary

        canvas.renderer = PoisoningRenderer()
        request = TemplateInsertRequest(
            ring_size=6,
            cursor_pos=(7.0, 8.0),
            ring_style="benzene",
        )
        plan = TemplateInsertPlan(
            generator="benzene",
            ring_size=6,
            ring_style="benzene",
            bond_id=None,
        )

        with self.assertRaises(KeyboardInterrupt) as raised:
            apply_template_commit_resolution(
                canvas,
                request,
                plan,
                None,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        self.assertIs(raised.exception, primary)
        self.assertEqual(last_smiles_input_for(canvas), "old")
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.next_atom_id, 0)

    def test_insert_exact_restore_retries_authority_and_preserves_primary(self) -> None:
        for behavior in ("fail_once", "persistent"):
            with self.subTest(behavior=behavior):
                canvas = _FakeCanvas()
                primary = KeyboardInterrupt(f"{behavior} insert mutation failed")
                first_error = SystemExit("first insert exact restore failed")
                first = HistoryTransactionRestoreResult(
                    authoritative=False,
                    fallback_to_inverse=False,
                    errors=(first_error,),
                )
                second = (
                    HistoryTransactionRestoreResult(authoritative=True)
                    if behavior == "fail_once"
                    else HistoryTransactionRestoreResult(
                        authoritative=False,
                        fallback_to_inverse=False,
                        errors=(RuntimeError("persistent insert restore failure"),),
                    )
                )

                with (
                    mock.patch.object(
                        insert_rollback_module,
                        "rollback_insert_mutation_for",
                    ),
                    mock.patch.object(
                        insert_rollback_module,
                        "restore_history_transaction_for_history",
                        side_effect=(first, second),
                    ) as restore,
                ):
                    rollback_insert_mutation(
                        canvas,
                        before_next_atom_id=0,
                        before_bond_count=0,
                        before_smiles_input="before",
                        exact_transaction=object(),
                        original_error=primary,
                    )

                self.assertEqual(restore.call_count, 2)
                self.assertEqual(last_smiles_input_for(canvas), "before")
                self.assertTrue(
                    any(
                        "first insert exact restore failed" in note
                        for note in getattr(primary, "__notes__", [])
                    )
                )
                if behavior == "persistent":
                    self.assertTrue(
                        any(
                            "persistent insert restore failure" in note
                            for note in getattr(primary, "__notes__", [])
                        )
                    )

    def test_insert_smiles_target_persistent_noop_is_nonauthoritative_and_retryable(
        self,
    ) -> None:
        blocked = False

        class AdversarialSmilesState:
            def __init__(self) -> None:
                self._value = "captured"

            @property
            def last_smiles_input(self):
                return self._value

            @last_smiles_input.setter
            def last_smiles_input(self, value) -> None:
                if not blocked:
                    self._value = value

        canvas = _FakeCanvas()
        state = AdversarialSmilesState()
        canvas.smiles_input_state = state
        authority = capture_smiles_input_restore_authority(canvas)
        blocked = True
        exact = HistoryTransactionRestoreResult(authoritative=True)

        with (
            mock.patch.object(
                insert_rollback_module,
                "rollback_insert_mutation_for",
            ),
            mock.patch.object(
                insert_rollback_module,
                "restore_history_transaction_for_history",
                return_value=exact,
            ),
            self.assertRaisesRegex(BaseExceptionGroup, "Insert rollback failed"),
        ):
            rollback_insert_mutation(
                canvas,
                before_next_atom_id=0,
                before_bond_count=0,
                before_smiles_input="before",
                exact_transaction=object(),
                smiles_authority=authority,
            )

        self.assertEqual(state.last_smiles_input, "captured")
        blocked = False
        result = rollback_insert_mutation(
            canvas,
            before_next_atom_id=0,
            before_bond_count=0,
            before_smiles_input="before",
            exact_transaction=None,
            smiles_authority=authority,
        )
        self.assertTrue(result.authoritative)
        self.assertEqual(state.last_smiles_input, "before")

    def test_smiles_value_verifier_cannot_replace_root_and_report_authoritative(
        self,
    ) -> None:
        replacement = SimpleNamespace(last_smiles_input="replacement")

        class RootPoisoningSmilesState:
            def __init__(self, owner) -> None:
                self.owner = owner
                self.value = "captured"
                self.poison = False

            @property
            def last_smiles_input(self):
                if self.poison:
                    self.owner.smiles_input_state = replacement
                return self.value

            @last_smiles_input.setter
            def last_smiles_input(self, value) -> None:
                self.value = value

        canvas = SimpleNamespace()
        state = RootPoisoningSmilesState(canvas)
        canvas.smiles_input_state = state
        authority = capture_smiles_input_restore_authority(canvas)
        state.poison = True

        result = authority.restore("before")

        self.assertFalse(result.authoritative)
        self.assertIsNot(canvas.smiles_input_state, state)
        self.assertTrue(result.errors)

    def test_structure_insert_access_routes_ring_build_to_structure_service(
        self,
    ) -> None:
        structure_build_service = SimpleNamespace(
            add_ring_from_points=mock.Mock(return_value=[7])
        )
        canvas = SimpleNamespace(
            services=canvas_runtime_services(
                structure=SimpleNamespace(
                    structure_build_service=structure_build_service
                )
            ),
        )
        points = [QPointF(1.0, 2.0), QPointF(3.0, 4.0)]

        atom_ids = add_insert_ring_from_points_for(canvas, points)

        self.assertEqual(atom_ids, [7])
        structure_build_service.add_ring_from_points.assert_called_once_with(
            points,
            elements=None,
            merge=None,
        )

    def test_rollback_insert_mutation_direct_fallback_removes_atom_coords_3d(
        self,
    ) -> None:
        canvas = SimpleNamespace(model=MoleculeModel())
        atom_id = canvas.model.add_atom("C", 1.0, 2.0)
        set_atom_coords_3d_for(canvas, {atom_id: (1.0, 2.0, 3.0)})

        rollback_insert_mutation_for(canvas, before_next_atom_id=0, before_bond_count=0)

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(atom_coords_3d_for(canvas), {})

    def test_rollback_insert_mutation_continues_after_one_atom_removal_fails(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        for offset in range(3):
            canvas.model.add_atom("C", float(offset), 0.0)
        removal_error = RuntimeError("atom rollback failure")
        attempted_atom_ids: list[int] = []

        def remove_atom(atom_id: int, *, remove_marks: bool = True) -> None:
            del remove_marks
            attempted_atom_ids.append(atom_id)
            if atom_id == 2:
                raise removal_error
            canvas.model.atoms.pop(atom_id, None)

        canvas.services.structure.canvas_atom_mutation_service.remove_atom_only = (
            remove_atom
        )

        with self.assertRaises(RuntimeError) as raised:
            rollback_insert_mutation_for(
                canvas,
                before_next_atom_id=0,
                before_bond_count=0,
            )

        self.assertIs(raised.exception, removal_error)
        self.assertEqual(attempted_atom_ids, [2, 1, 0])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.next_atom_id, 0)

    def test_rollback_insert_mutation_raw_fallback_clears_graph_graphics_and_scene(
        self,
    ) -> None:
        class _SceneItem:
            def __init__(self, scene) -> None:
                self._scene = scene

            def scene(self):
                return self._scene

        class _Scene:
            def __init__(self) -> None:
                self.items: list[_SceneItem] = []

            def removeItem(self, item) -> None:
                self.items.remove(item)
                item._scene = None

        canvas = _FakeCanvas()
        scene = _Scene()
        canvas.scene = lambda: scene
        atom_id = canvas.model.add_atom("N", 1.0, 2.0)
        canvas.model.atom_annotations[atom_id] = {"formal_charge": 1}
        set_atom_coords_3d_for(canvas, {atom_id: (1.0, 2.0, 3.0)})
        graph = graph_state_for(canvas)
        graph.atom_neighbors[atom_id] = set()
        graph.atom_bond_ids[atom_id] = set()
        label = _SceneItem(scene)
        scene.items.append(label)
        atom_items_for(canvas)[atom_id] = label
        removal_error = KeyboardInterrupt("persistent atom lifecycle interruption")

        def pop_graphics_then_raise(
            removed_atom_id: int,
            *,
            remove_marks: bool = True,
        ) -> None:
            del remove_marks
            atom_items_for(canvas).pop(removed_atom_id, None)
            raise removal_error

        canvas.services.structure.canvas_atom_mutation_service.remove_atom_only = (
            mock.Mock(side_effect=pop_graphics_then_raise)
        )

        with self.assertRaises(KeyboardInterrupt) as raised:
            rollback_insert_mutation_for(
                canvas,
                before_next_atom_id=0,
                before_bond_count=0,
            )

        self.assertIs(raised.exception, removal_error)
        self.assertNotIn(atom_id, canvas.model.atoms)
        self.assertNotIn(atom_id, canvas.model.atom_annotations)
        self.assertNotIn(atom_id, atom_coords_3d_for(canvas))
        self.assertNotIn(atom_id, graph.atom_neighbors)
        self.assertNotIn(atom_id, graph.atom_bond_ids)
        self.assertNotIn(atom_id, atom_items_for(canvas))
        self.assertEqual(scene.items, [])
        self.assertIsNone(label.scene())
        self.assertEqual(canvas.model.next_atom_id, 0)

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
        self.assertEqual(last_smiles_input_for(canvas), "new")
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

    def test_apply_smiles_commit_plan_rolls_back_mutate_then_keyboard_interrupt(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[SmilesAtomPlacement(0, "N", 10.0, 20.0, "#111111", True)],
            bonds=[],
        )
        interruption = KeyboardInterrupt("SMILES insertion interrupted")
        original_add_atom = insert_smiles_commit_service_module.add_insert_atom_for

        def add_then_interrupt(target_canvas, element: str, x: float, y: float) -> int:
            original_add_atom(target_canvas, element, x, y)
            raise interruption

        with (
            mock.patch.object(
                insert_smiles_commit_service_module,
                "add_insert_atom_for",
                side_effect=add_then_interrupt,
            ),
            self.assertRaises(KeyboardInterrupt) as raised,
        ):
            apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        self.assertIs(raised.exception, interruption)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.model.next_atom_id, 0)
        self.assertEqual(last_smiles_input_for(canvas), "old")

    def test_smiles_commit_history_record_failure_restores_model_and_input_root(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[SmilesAtomPlacement(0, "N", 10.0, 20.0, "#111111", True)],
            bonds=[],
        )
        primary = SystemExit("insert history push terminated")

        def mutate_input_then_fail(**_kwargs) -> None:
            set_last_smiles_input_for(canvas, "poisoned-after-push")
            raise primary

        canvas.services.document.canvas_history_recording_service.record_additions = (
            mutate_input_then_fail
        )

        with self.assertRaises(SystemExit) as caught:
            apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        self.assertIs(caught.exception, primary)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.model.next_atom_id, 0)
        self.assertEqual(last_smiles_input_for(canvas), "old")

    def test_smiles_commit_outer_rollback_and_broken_add_note_preserve_primary_and_retry(
        self,
    ) -> None:
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[SmilesAtomPlacement(0, "N", 10.0, 20.0, "#111111", True)],
            bonds=[],
        )
        for error_type in (_BrokenAddNoteInterrupt, _BrokenAddNoteSystemExit):
            with self.subTest(error_type=error_type.__name__):
                canvas = _FakeCanvas()
                primary_error = error_type("SMILES insertion interrupted")
                original_add_atom = (
                    insert_smiles_commit_service_module.add_insert_atom_for
                )
                original_rollback = (
                    insert_smiles_commit_service_module.rollback_insert_mutation
                )

                def add_then_interrupt(
                    target_canvas,
                    element: str,
                    x: float,
                    y: float,
                    error: BaseException = primary_error,
                    add_atom=original_add_atom,
                ) -> int:
                    add_atom(target_canvas, element, x, y)
                    raise error

                def rollback_then_fail(
                    *args,
                    rollback=original_rollback,
                    **kwargs,
                ) -> None:
                    rollback(*args, **kwargs)
                    raise RuntimeError("outer rollback reported failure")

                with (
                    mock.patch.object(
                        insert_smiles_commit_service_module,
                        "add_insert_atom_for",
                        side_effect=add_then_interrupt,
                    ),
                    mock.patch.object(
                        insert_smiles_commit_service_module,
                        "rollback_insert_mutation",
                        side_effect=rollback_then_fail,
                    ),
                    self.assertRaises(error_type) as raised,
                ):
                    apply_smiles_commit_plan(
                        canvas,
                        plan,
                        before_smiles_input="old",
                        after_smiles_input="new",
                    )

                self.assertIs(raised.exception, primary_error)
                self.assertEqual(canvas.model.atoms, {})
                self.assertEqual(canvas.model.next_atom_id, 0)
                self.assertEqual(last_smiles_input_for(canvas), "old")

                self.assertTrue(
                    apply_smiles_commit_plan(
                        canvas,
                        plan,
                        before_smiles_input="old",
                        after_smiles_input="new",
                    )
                )
                self.assertEqual(set(canvas.model.atoms), {0})
                self.assertEqual(last_smiles_input_for(canvas), "new")

    def test_apply_smiles_commit_plan_adds_annotation_marks_to_history(self) -> None:
        canvas = _FakeCanvas()
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[
                SmilesAtomPlacement(3, "N", 10.0, 20.0, "#111111", True),
            ],
            bonds=[],
            marks=[
                SmilesMarkPlacement(3, "plus", 11.0, 19.0),
            ],
            annotations={3: {"formal_charge": 1}},
        )

        applied = apply_smiles_commit_plan(
            canvas,
            plan,
            before_smiles_input="old",
            after_smiles_input="new",
        )

        self.assertTrue(applied)
        self.assertEqual(canvas.mark_calls, [(0, 11.0, 19.0, "plus", False)])
        self.assertEqual(canvas.model.atom_annotations, {0: {"formal_charge": 1}})
        self.assertEqual(
            canvas.record_calls,
            [
                {
                    "before_next_atom_id": 0,
                    "before_bond_count": 0,
                    "before_smiles_input": "old",
                    "added_scene_items": canvas.created_marks,
                }
            ],
        )

    def test_apply_smiles_commit_plan_removes_created_marks_if_later_mark_creation_raises(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[
                SmilesAtomPlacement(3, "N", 10.0, 20.0, "#111111", True),
            ],
            bonds=[],
            marks=[
                SmilesMarkPlacement(3, "plus", 11.0, 19.0),
                SmilesMarkPlacement(3, "minus", 9.0, 21.0),
            ],
        )

        def add_first_mark_then_fail(
            atom_id: int,
            click_pos: QPointF,
            *,
            kind: str | None = None,
            record: bool = True,
        ):
            if not canvas.created_marks:
                return canvas.add_mark_for_atom(
                    atom_id, click_pos, kind=kind, record=record
                )
            raise RuntimeError("mark failed")

        canvas.services.scene_decoration.canvas_mark_scene_service.add_mark_for_atom = (
            add_first_mark_then_fail
        )

        with self.assertRaisesRegex(RuntimeError, "mark failed"):
            apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.created_marks, [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "old")

    def test_apply_template_commit_resolution_handles_free_and_bond_paths(self) -> None:
        free_canvas = _FakeCanvas()
        free_request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(5.0, 6.0), ring_style="regular"
        )
        free_plan = TemplateInsertPlan(
            generator="free_regular_ring",
            ring_size=6,
            ring_style="regular",
            bond_id=None,
            radius_mode="regular_polygon",
        )
        free_resolution = TemplateInsertResolution(plan=free_plan, points=_points(6))

        applied = apply_template_commit_resolution(
            free_canvas,
            free_request,
            free_plan,
            free_resolution,
            before_smiles_input="before-free",
            after_smiles_input=None,
        )

        self.assertTrue(applied)
        self.assertEqual(
            free_canvas.add_atom_calls, [("C", x, y) for x, y in _points(6)]
        )
        self.assertEqual(
            free_canvas.add_bond_calls,
            [(0, 1, 1), (1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 5, 1), (5, 0, 1)],
        )
        self.assertEqual(
            free_canvas.record_calls[0]["before_smiles_input"], "before-free"
        )
        self.assertIsNone(last_smiles_input_for(free_canvas))

        bond_canvas = _FakeCanvas()
        bond_canvas.model.atoms = {
            0: Atom("C", 0.0, 0.0),
            1: Atom("C", 10.0, 0.0),
        }
        bond_canvas.model.bonds = [Bond(0, 1, 1)]
        bond_canvas.model.next_atom_id = 2
        bond_request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(8.0, 9.0), bond_id=0, ring_style="chair"
        )
        bond_plan = TemplateInsertPlan(
            generator="bond_template_shape",
            ring_size=6,
            ring_style="chair",
            bond_id=0,
            template_shape="chair",
        )
        bond_resolution = TemplateInsertResolution(
            plan=bond_plan,
            points=_points(6, start=11.0),
        )

        applied = apply_template_commit_resolution(
            bond_canvas,
            bond_request,
            bond_plan,
            bond_resolution,
            before_smiles_input="before-bond",
        )

        self.assertTrue(applied)
        self.assertEqual(
            bond_canvas.ring_calls[-1][:2], [(0, 0.0, 0.0), (1, 10.0, 0.0)]
        )
        self.assertEqual(
            bond_canvas.record_calls[0]["before_smiles_input"], "before-bond"
        )
        self.assertEqual(len(ring_items_for(bond_canvas)), 1)
        ring_item = ring_items_for(bond_canvas)[0]
        self.assertEqual(ring_item.data(2), [2, 3, 4, 5, 6, 7])
        self.assertEqual(bond_canvas.record_calls[0]["added_scene_items"], [ring_item])

    def test_apply_template_commit_resolution_rejects_degenerate_point_sets(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(5.0, 6.0), ring_style="regular"
        )
        plan = TemplateInsertPlan(
            generator="free_regular_ring",
            ring_size=6,
            ring_style="regular",
            bond_id=None,
            radius_mode="regular_polygon",
        )
        resolution = TemplateInsertResolution(
            plan=plan, points=[(1.0, 2.0), (3.0, 4.0)]
        )

        applied = apply_template_commit_resolution(
            canvas,
            request,
            plan,
            resolution,
            before_smiles_input="before-free",
        )

        self.assertFalse(applied)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.record_calls, [])
        self.assertEqual(last_smiles_input_for(canvas), "before")

    def test_apply_template_commit_resolution_uses_benzene_path_and_rejects_invalid_points(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(7.0, 8.0), bond_id=3, ring_style="benzene"
        )
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
        self.assertIsNone(last_smiles_input_for(canvas))

        blocked = _FakeCanvas()
        blocked.services.structure.structure_build_service.add_benzene_ring = (
            lambda *args, **kwargs: None
        )
        self.assertFalse(
            apply_template_commit_resolution(
                blocked,
                request,
                plan,
                None,
                before_smiles_input="before-benzene",
            )
        )

    def test_benzene_template_preserves_original_error_when_outer_rollback_fails(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        request = TemplateInsertRequest(
            ring_size=6,
            cursor_pos=(7.0, 8.0),
            ring_style="benzene",
        )
        plan = TemplateInsertPlan(
            generator="benzene",
            ring_size=6,
            ring_style="benzene",
            bond_id=None,
        )
        original_error = RuntimeError("original benzene failure")
        canvas.services.structure.structure_build_service.add_benzene_ring = mock.Mock(
            side_effect=original_error
        )

        with (
            mock.patch(
                "chemvas.ui.insert_template_commit_service.rollback_insert_mutation",
                side_effect=RuntimeError("outer rollback failure"),
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            apply_template_commit_resolution(
                canvas,
                request,
                plan,
                None,
                before_smiles_input="before-benzene",
            )

        self.assertIs(raised.exception, original_error)
        self.assertTrue(
            any("outer rollback failure" in note for note in original_error.__notes__)
        )

    def test_benzene_template_broken_add_note_preserves_control_flow_primary(
        self,
    ) -> None:
        request = TemplateInsertRequest(
            ring_size=6,
            cursor_pos=(7.0, 8.0),
            ring_style="benzene",
        )
        plan = TemplateInsertPlan(
            generator="benzene",
            ring_size=6,
            ring_style="benzene",
            bond_id=None,
        )
        for error_type in (_BrokenAddNoteInterrupt, _BrokenAddNoteSystemExit):
            with self.subTest(error_type=error_type.__name__):
                canvas = _FakeCanvas()
                primary_error = error_type("benzene interrupted")
                canvas.services.structure.structure_build_service.add_benzene_ring = (
                    mock.Mock(side_effect=primary_error)
                )

                with (
                    mock.patch(
                        "chemvas.ui.insert_template_commit_service.rollback_insert_mutation",
                        side_effect=RuntimeError("outer rollback failure"),
                    ),
                    self.assertRaises(error_type) as raised,
                ):
                    apply_template_commit_resolution(
                        canvas,
                        request,
                        plan,
                        None,
                        before_smiles_input="before-benzene",
                    )

                self.assertIs(raised.exception, primary_error)

    def test_apply_smiles_commit_plan_prefers_atom_label_service_over_canvas_wrapper(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service_calls = []
        canvas.services.atom_label_service = SimpleNamespace(
            add_or_update_atom_label=lambda atom_id, text, **kwargs: (
                service_calls.append((atom_id, text, kwargs))
            )
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
                (
                    0,
                    "C",
                    {
                        "clear_smiles": False,
                        "record": False,
                        "allow_merge": True,
                        "show_carbon": False,
                    },
                ),
                (
                    1,
                    "Cl",
                    {
                        "clear_smiles": False,
                        "record": False,
                        "allow_merge": True,
                        "show_carbon": False,
                    },
                ),
            ],
        )
        self.assertEqual(canvas.labels, [])

    def test_service_wrapper_delegates_to_module_functions(self) -> None:
        canvas = _FakeCanvas()
        service = InsertCommitService(canvas)

        self.assertFalse(
            service.apply_smiles_commit_plan(
                None, before_smiles_input="before", after_smiles_input="after"
            )
        )

    def test_service_template_wrappers_rewrite_cursor_delegate_and_handle_none_merge_seed(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        service = InsertCommitService(canvas)
        request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(1.0, 2.0), bond_id=4, ring_style="chair"
        )
        plan = TemplateInsertPlan(
            generator="free_regular_ring",
            ring_size=6,
            ring_style="chair",
            bond_id=4,
            template_shape="chair",
        )
        resolution = TemplateInsertResolution(plan=plan, points=_points(6, start=0.0))

        with mock.patch(
            "chemvas.ui.insert_commit_service.apply_template_commit_resolution",
            return_value=True,
        ) as patched:
            applied = service.apply_template_commit(
                QPointF(9.0, 10.0),
                request=request,
                plan=plan,
                resolution=resolution,
            )

        self.assertTrue(applied)
        called_request = patched.call_args.args[1]
        self.assertEqual(called_request.cursor_pos, (9.0, 10.0))
        self.assertEqual(patched.call_args.kwargs["before_smiles_input"], "before")
        self.assertEqual(service.bond_merge_seed(None), [])

        with mock.patch(
            "chemvas.ui.insert_commit_service.apply_template_commit_resolution",
            return_value=False,
        ) as patched:
            self.assertFalse(
                service.apply_template_commit_resolution(
                    request,
                    plan,
                    resolution,
                    before_smiles_input="old",
                    after_smiles_input="new",
                )
            )
        self.assertEqual(patched.call_args.kwargs["after_smiles_input"], "new")

    def test_apply_smiles_commit_plan_rejects_duplicate_and_unknown_bond_sources(
        self,
    ) -> None:
        duplicate_canvas = _FakeCanvas()
        duplicate_plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[
                SmilesAtomPlacement(7, "C", 0.0, 0.0, "#111111", False),
                SmilesAtomPlacement(7, "N", 1.0, 1.0, "#222222", False),
            ],
            bonds=[],
        )
        self.assertFalse(
            apply_smiles_commit_plan(
                duplicate_canvas,
                duplicate_plan,
                before_smiles_input="before",
                after_smiles_input="after",
            )
        )

        invalid_bond_canvas = _FakeCanvas()
        invalid_bond_plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[SmilesAtomPlacement(0, "C", 0.0, 0.0, "#111111", False)],
            bonds=[SmilesBondPlacement(0, 0, 99, 1, "solid", "#222222")],
        )
        self.assertFalse(
            apply_smiles_commit_plan(
                invalid_bond_canvas,
                invalid_bond_plan,
                before_smiles_input="before",
                after_smiles_input="after",
            )
        )

    def test_apply_smiles_commit_plan_returns_false_when_id_lookup_breaks_after_atom_creation(
        self,
    ) -> None:
        # atom_source and bond_source are equal twins during validation, so the
        # plan clears the up-front bond-source check. _DetachingCanvas detaches
        # atom_source once both atoms exist, so the bond's id_map lookup misses
        # and the commit must roll back -- deterministic across PYTHONHASHSEED.
        atom_source = _DetachableSourceId("a")
        bond_source = _DetachableSourceId("a")
        other_source = _DetachableSourceId("b")
        canvas = _DetachingCanvas(atom_source)
        plan = SmilesCommitPlan(
            offset=(0.0, 0.0),
            atoms=[
                SmilesAtomPlacement(atom_source, "C", 0.0, 0.0, "#111111", False),
                SmilesAtomPlacement(other_source, "N", 1.0, 0.0, "#222222", True),
            ],
            bonds=[
                SmilesBondPlacement(0, bond_source, other_source, 1, "solid", "#333333")
            ],
        )

        self.assertFalse(
            apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="before",
                after_smiles_input="after",
            )
        )
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.model.next_atom_id, 0)
        self.assertEqual(last_smiles_input_for(canvas), "before")
        self.assertEqual(canvas.record_calls, [])

    def test_apply_template_commit_resolution_rejects_bond_generators_without_bond_id(
        self,
    ) -> None:
        canvas = _FakeCanvas()
        request = TemplateInsertRequest(
            ring_size=6, cursor_pos=(3.0, 4.0), ring_style="regular"
        )
        plan = TemplateInsertPlan(
            generator="bond_regular_ring",
            ring_size=6,
            ring_style="regular",
            bond_id=None,
            radius_mode="regular_polygon",
        )
        resolution = TemplateInsertResolution(plan=plan, points=_points(6))

        self.assertFalse(
            apply_template_commit_resolution(
                canvas,
                request,
                plan,
                resolution,
                before_smiles_input="before",
            )
        )
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])

    def test_successful_insert_history_observer_cannot_rewrite_command_after_state(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        def free_template(canvas: CanvasView) -> bool:
            points = [
                (0.0, 0.0),
                (20.0, 0.0),
                (25.0, 15.0),
                (10.0, 25.0),
                (-5.0, 15.0),
            ]
            request = TemplateInsertRequest(
                ring_size=5,
                cursor_pos=(0.0, 0.0),
                ring_style="regular",
            )
            plan = TemplateInsertPlan(
                generator="free_regular_ring",
                ring_size=5,
                ring_style="regular",
                bond_id=None,
                radius_mode="regular_polygon",
            )
            return apply_template_commit_resolution(
                canvas,
                request,
                plan,
                TemplateInsertResolution(plan=plan, points=points),
                before_smiles_input="old",
            )

        def benzene_template(canvas: CanvasView) -> bool:
            request = TemplateInsertRequest(
                ring_size=6,
                cursor_pos=(0.0, 0.0),
                ring_style="benzene",
            )
            plan = TemplateInsertPlan(
                generator="benzene",
                ring_size=6,
                ring_style="benzene",
                bond_id=None,
            )
            return apply_template_commit_resolution(
                canvas,
                request,
                plan,
                None,
                before_smiles_input="old",
            )

        def smiles(canvas: CanvasView) -> bool:
            plan = SmilesCommitPlan(
                offset=(0.0, 0.0),
                atoms=[
                    SmilesAtomPlacement(
                        0,
                        "N",
                        1.0,
                        2.0,
                        "#123456",
                        True,
                    )
                ],
                bonds=[],
            )
            return apply_smiles_commit_plan(
                canvas,
                plan,
                before_smiles_input="old",
                after_smiles_input="new",
            )

        for label, operation in (
            ("smiles", smiles),
            ("free-template", free_template),
            ("benzene-template", benzene_template),
        ):
            with self.subTest(label=label):
                canvas = CanvasView()
                history = canvas.services.history_service
                before_history = tuple(history.state.history)
                before_redo = tuple(history.state.redo_stack)

                def poison_published_atom(target: CanvasView = canvas) -> None:
                    if target.model.atoms:
                        target.model.atoms[max(target.model.atoms)].color = "#abcdef"

                history.set_change_callback(poison_published_atom)
                try:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "recorded atom state changed after history publication",
                    ):
                        operation(canvas)

                    self.assertEqual(canvas.model.atoms, {})
                    self.assertEqual(canvas.model.bonds, [])
                    self.assertEqual(canvas.model.next_atom_id, 0)
                    self.assertEqual(tuple(history.state.history), before_history)
                    self.assertEqual(tuple(history.state.redo_stack), before_redo)
                finally:
                    history.set_change_callback(None)
                    schedule_canvas_deletion_for(canvas)
                    QCoreApplication.sendPostedEvents(
                        canvas,
                        QEvent.Type.DeferredDelete,
                    )


if __name__ == "__main__":
    unittest.main()
