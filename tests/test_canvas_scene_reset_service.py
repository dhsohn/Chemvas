import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from core.model import MoleculeModel
from PyQt6.QtWidgets import QApplication
from ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for
from ui.canvas_graph_state import CanvasGraphState
from ui.canvas_hover_state import (
    hover_state_for,
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_insert_state import CanvasInsertState
from ui.canvas_mark_registry import CanvasMarkRegistry
from ui.canvas_rotation_state import CanvasRotationState
from ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    shape_items_for,
    ts_bracket_items_for,
)
from ui.canvas_scene_reset_service import CanvasSceneResetService
from ui.canvas_view import CanvasView
from ui.handle_state import (
    active_handles_for,
    handle_target_for,
    set_active_handles_for,
    set_handle_target_for,
)
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.insert_mode_logic import clear_insert_session
from ui.selection_info_state import SelectionInfoState, selection_info_state_for
from ui.selection_outline_state import (
    selection_outlines_for,
    set_selection_outlines_for,
)
from ui.selection_style_state import SelectionStyleState


class _FakeScene:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear(self) -> None:
        self.clear_calls += 1


class CanvasSceneResetServiceTest(unittest.TestCase):
    def test_history_verifier_cannot_repopulate_model_and_still_approve_reset(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        replacement = MoleculeModel()
        replacement.add_atom("C", 10.0, 20.0)
        selection_info_state_for(canvas).callback = None

        def poison_model_while_reporting_exact(_snapshot) -> bool:
            canvas.model = replacement
            return True

        with (
            mock.patch.object(
                HistoryStackSnapshot,
                "is_exact",
                autospec=True,
                side_effect=poison_model_while_reporting_exact,
            ),
            self.assertRaisesRegex(RuntimeError, "document state was re-mutated"),
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        canvas.close()
        app.processEvents()

    def test_actual_qt_empty_status_publishes_once_then_reasserts_full_clear(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        self.app = app
        canvas = CanvasView()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        atom_items_for(canvas)[atom_id].setSelected(True)
        history = canvas.services.history_service.state.history
        history_entry = object()
        history.append(history_entry)
        published: list[tuple[str, str]] = []

        def corrupt_after_empty_status(formula: str, mass: str) -> None:
            published.append((formula, mass))
            canvas.services.canvas_scene_reset_service.clear_scene()
            canvas.services.canvas_atom_mutation_service.add_atom(
                "C",
                100.0,
                100.0,
            )
            history.append(object())

        selection_info_state_for(canvas).callback = corrupt_after_empty_status

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(published, [("", "")])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.scene().items(), [])
        self.assertEqual(history, [history_entry])
        self.assertIs(
            selection_info_state_for(canvas).callback,
            corrupt_after_empty_status,
        )
        selection_info_state_for(canvas).callback = None
        canvas.close()

    def test_scene_block_interruption_is_repaired_before_mutation(self) -> None:
        class InterruptingScene:
            def __init__(self) -> None:
                self.blocked = False
                self.calls = 0
                self.clear_calls = 0

            def clearSelection(self) -> None:
                return None

            def signalsBlocked(self) -> bool:
                return self.blocked

            def clear(self) -> None:
                self.clear_calls += 1

            def blockSignals(self, blocked: bool) -> bool:
                self.calls += 1
                previous = self.blocked
                self.blocked = blocked
                if self.calls == 1:
                    raise SystemExit("scene reset signal blocking terminated")
                return previous

        scene = InterruptingScene()
        service = CanvasSceneResetService.__new__(CanvasSceneResetService)
        service.canvas = SimpleNamespace(scene=lambda: scene)

        service._clear_graphics_scene_without_callbacks()

        self.assertFalse(scene.signalsBlocked())
        self.assertEqual(scene.clear_calls, 1)
        self.assertEqual(scene.calls, 3)

    def test_live_scene_port_failure_is_pre_mutation_and_retryable(self) -> None:
        for failure_root in ("scene", "blockSignals"):
            with self.subTest(failure_root=failure_root):
                class FlakyScene:
                    def __init__(self, *, fail_block_once: bool) -> None:
                        self.blocked = False
                        self.block_port_reads = 0
                        self.signals_port_reads = 0
                        self.clear_selection_calls = 0
                        self.clear_calls = 0
                        self.fail_block_once = fail_block_once

                    def clearSelection(self) -> None:
                        self.clear_selection_calls += 1

                    def clear(self) -> None:
                        # Destruction must never run while callbacks are live.
                        if not self.blocked:
                            raise AssertionError(
                                "scene destruction was not signal-blocked"
                            )
                        self.clear_calls += 1

                    @property
                    def blockSignals(self):
                        self.block_port_reads += 1
                        if self.fail_block_once:
                            self.fail_block_once = False
                            raise AttributeError("blockSignals descriptor failed")
                        return self._block_signals

                    def _block_signals(self, blocked: bool) -> bool:
                        previous = self.blocked
                        self.blocked = blocked
                        return previous

                    @property
                    def signalsBlocked(self):
                        self.signals_port_reads += 1
                        return lambda: self.blocked

                class FlakyCanvas:
                    def __init__(self, scene, *, fail_scene_once: bool) -> None:
                        self._scene = scene
                        self.scene_port_reads = 0
                        self.fail_scene_once = fail_scene_once
                        self.model = object()
                        self.services = SimpleNamespace()

                    @property
                    def scene(self):
                        self.scene_port_reads += 1
                        if self.fail_scene_once:
                            self.fail_scene_once = False
                            raise AttributeError("scene descriptor failed")
                        return lambda: self._scene

                scene = FlakyScene(
                    fail_block_once=failure_root == "blockSignals",
                )
                canvas = FlakyCanvas(
                    scene,
                    fail_scene_once=failure_root == "scene",
                )
                hit_testing = SimpleNamespace(
                    mark_spatial_index_dirty=mock.Mock(),
                )
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=hit_testing,
                )
                selected_item = object()
                canvas.selection_style_state = SelectionStyleState(
                    selected_items=[selected_item],
                    suspend_outline=True,
                )
                selection_callback = mock.Mock()
                canvas.selection_info_state = SelectionInfoState(
                    callback=selection_callback,
                    signature=(frozenset({1}), frozenset({2})),
                    pending_signature=(frozenset({1}), frozenset({2})),
                    cache=("old", "selection"),
                    rdkit_warmup_pending=True,
                )
                original_model = canvas.model
                original_selected_items = canvas.selection_style_state.selected_items
                set_selection_outlines_for(canvas, [object()])
                set_active_handles_for(canvas, [object()])

                with self.assertRaisesRegex(
                    AttributeError,
                    rf"{failure_root} descriptor failed",
                ):
                    service.clear_scene()

                self.assertIs(canvas.model, original_model)
                self.assertIs(
                    canvas.selection_style_state.selected_items,
                    original_selected_items,
                )
                self.assertEqual(
                    canvas.selection_style_state.selected_items,
                    [selected_item],
                )
                self.assertTrue(canvas.selection_style_state.suspend_outline)
                self.assertEqual(
                    canvas.selection_info_state.cache,
                    ("old", "selection"),
                )
                self.assertTrue(canvas.selection_info_state.rdkit_warmup_pending)
                self.assertEqual(len(selection_outlines_for(canvas)), 1)
                self.assertEqual(len(active_handles_for(canvas)), 1)
                self.assertEqual(scene.clear_selection_calls, 0)
                self.assertEqual(scene.clear_calls, 0)
                hit_testing.mark_spatial_index_dirty.assert_not_called()

                service.clear_scene()

                self.assertEqual(canvas.scene_port_reads, 2)
                self.assertEqual(
                    scene.block_port_reads,
                    1 if failure_root == "scene" else 2,
                )
                self.assertEqual(scene.signals_port_reads, 1)
                self.assertEqual(scene.clear_selection_calls, 2)
                self.assertEqual(scene.clear_calls, 2)
                self.assertFalse(scene.blocked)
                self.assertEqual(canvas.selection_style_state.selected_items, [])
                self.assertFalse(canvas.selection_style_state.suspend_outline)
                self.assertIsNone(canvas.selection_info_state.signature)
                self.assertIsNone(canvas.selection_info_state.pending_signature)
                self.assertEqual(canvas.selection_info_state.cache, ("", ""))
                self.assertFalse(canvas.selection_info_state.rdkit_warmup_pending)
                selection_callback.assert_called_once_with("", "")

    def test_present_non_callable_block_port_is_not_treated_as_sparse(self) -> None:
        class MalformedScene(_FakeScene):
            blockSignals = None

        scene = MalformedScene()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            selection_style_state=SelectionStyleState(
                selected_items=[object()],
                suspend_outline=True,
            ),
        )
        service = CanvasSceneResetService.__new__(CanvasSceneResetService)
        service.canvas = canvas

        with self.assertRaisesRegex(TypeError, "blockSignals is not callable"):
            service.clear_scene()

        self.assertEqual(scene.clear_calls, 0)
        self.assertEqual(len(canvas.selection_style_state.selected_items), 1)
        self.assertTrue(canvas.selection_style_state.suspend_outline)

    def test_clear_scene_resets_canvas_state_and_clears_previews(self) -> None:
        scene = _FakeScene()
        apply_insert_session_state = mock.Mock()
        clear_benzene_preview = mock.Mock()
        selection_callback = mock.Mock()
        selected_highlight = object()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(dummy=True),
            services=SimpleNamespace(
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
                benzene_preview_service=SimpleNamespace(clear_preview=clear_benzene_preview),
                insert_controller=SimpleNamespace(
                    clear_template_preview=mock.Mock(),
                    clear_smiles_preview=mock.Mock(),
                    apply_insert_session_state=apply_insert_session_state,
                ),
            ),
            rotation_state=CanvasRotationState(
                projection_center_3d=(1.0, 1.0, 1.0),
                projection_anchor_2d=(2.0, 2.0),
                start_projection_center_3d=(3.0, 3.0, 3.0),
                start_projection_anchor_2d=(4.0, 4.0),
                axis_bond_id=7,
                axis_atoms=(1, 2),
                total_angle=1.2,
                mode="bond",
                free_angle_x=2.3,
                free_angle_y=4.5,
                start_positions={1: (0.0, 0.0)},
                start_coords_3d={1: (0.0, 0.0, 0.0)},
                coord_atom_ids={1},
            ),
            atom_items={1: object()},
            atom_dots={1: object()},
            graph_state=CanvasGraphState(
                atom_neighbors={1: {2}},
                atom_bond_ids={1: {0}},
                graph_version=9,
                selection_component_cache_signature="sig",
                selection_component_cache=[{1}],
            ),
            bond_items={0: [object()]},
            ring_items=[object()],
            note_items=[object()],
            mark_items=[object()],
            arrow_items=[object()],
            ts_bracket_items=[object()],
            shape_items=[object()],
            orbital_items=[object()],
            mark_registry=CanvasMarkRegistry({1: [object()]}),
            insert_state=CanvasInsertState(smiles_preview_model=object()),
            selection_style_state=SelectionStyleState(
                selected_items=[selected_highlight],
                suspend_outline=True,
            ),
            selection_info_state=SelectionInfoState(
                callback=selection_callback,
                signature=(frozenset({1}), frozenset({2})),
                pending_signature=(frozenset({1}), frozenset({2})),
                cache=("C", "12.01"),
                rdkit_warmup_pending=True,
            ),
        )
        set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0)})
        set_hover_items_for(canvas, [object()])
        set_hover_atom_id_for(canvas, 3)
        set_hover_bond_id_for(canvas, 4)
        set_selection_outlines_for(canvas, [object()])
        set_active_handles_for(canvas, [object()])
        set_handle_target_for(canvas, object())

        CanvasSceneResetService(
            canvas,
            hit_testing_service=canvas.services.hit_testing_service,
        ).clear_scene()

        self.assertEqual(scene.clear_calls, 2)
        self.assertEqual(hover_state_for(canvas).items, [])
        self.assertIsNone(hover_state_for(canvas).atom_id)
        self.assertIsNone(hover_state_for(canvas).bond_id)
        self.assertIsInstance(canvas.model, MoleculeModel)
        canvas.services.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()
        self.assertEqual(atom_coords_3d_for(canvas), {})
        self.assertIsNone(canvas.rotation_state.projection_center_3d)
        self.assertIsNone(canvas.rotation_state.projection_anchor_2d)
        self.assertIsNone(canvas.rotation_state.start_projection_center_3d)
        self.assertIsNone(canvas.rotation_state.start_projection_anchor_2d)
        self.assertIsNone(canvas.rotation_state.axis_bond_id)
        self.assertIsNone(canvas.rotation_state.axis_atoms)
        self.assertEqual(canvas.rotation_state.total_angle, 0.0)
        self.assertIsNone(canvas.rotation_state.mode)
        self.assertEqual(canvas.rotation_state.free_angle_x, 0.0)
        self.assertEqual(canvas.rotation_state.free_angle_y, 0.0)
        self.assertEqual(canvas.rotation_state.start_positions, {})
        self.assertEqual(canvas.rotation_state.start_coords_3d, {})
        self.assertEqual(canvas.rotation_state.coord_atom_ids, set())
        self.assertEqual(atom_items_for(canvas), {})
        self.assertEqual(atom_dots_for(canvas), {})
        self.assertEqual(canvas.graph_state.atom_neighbors, {})
        self.assertEqual(canvas.graph_state.atom_bond_ids, {})
        self.assertEqual(canvas.graph_state.graph_version, 0)
        self.assertIsNone(canvas.graph_state.selection_component_cache_signature)
        self.assertEqual(canvas.graph_state.selection_component_cache, [])
        self.assertEqual(bond_items_for(canvas), {})
        self.assertEqual(ring_items_for(canvas), [])
        self.assertEqual(note_items_for(canvas), [])
        self.assertEqual(mark_items_for(canvas), [])
        self.assertEqual(arrow_items_for(canvas), [])
        self.assertEqual(ts_bracket_items_for(canvas), [])
        self.assertEqual(shape_items_for(canvas), [])
        self.assertEqual(orbital_items_for(canvas), [])
        self.assertEqual(selection_outlines_for(canvas), [])
        self.assertEqual(canvas.selection_style_state.selected_items, [])
        self.assertFalse(canvas.selection_style_state.suspend_outline)
        self.assertIsNone(canvas.selection_info_state.signature)
        self.assertIsNone(canvas.selection_info_state.pending_signature)
        self.assertEqual(canvas.selection_info_state.cache, ("", ""))
        self.assertFalse(canvas.selection_info_state.rdkit_warmup_pending)
        selection_callback.assert_called_once_with("", "")
        self.assertEqual(active_handles_for(canvas), [])
        self.assertIsNone(handle_target_for(canvas))
        self.assertEqual(canvas.mark_registry.by_atom, {})
        self.assertIsNone(canvas.insert_state.smiles_preview_model)
        canvas.services.insert_controller.clear_template_preview.assert_called_once_with()
        clear_benzene_preview.assert_called_once_with()
        canvas.services.insert_controller.clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once_with(clear_insert_session())
