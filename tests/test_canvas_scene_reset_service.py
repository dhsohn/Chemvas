import os
import subprocess
import sys
import textwrap
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from chemvas.core.renderer import Renderer
from chemvas.domain.document import MoleculeModel
from chemvas.features.hover import HoverState
from chemvas.ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_graph_state import CanvasGraphState, graph_state_for
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_insert_state import CanvasInsertState, insert_state_for
from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry, mark_registry_for
from chemvas.ui.canvas_rotation_state import CanvasRotationState, rotation_state_for
from chemvas.ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    orbital_items_for,
    ring_items_for,
    shape_items_for,
    ts_bracket_items_for,
)
from chemvas.ui.canvas_scene_reset_service import CanvasSceneResetService
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.handle_state import (
    active_handles_for,
    handle_target_for,
    set_active_handles_for,
    set_handle_target_for,
)
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.insert_mode_logic import clear_insert_session
from chemvas.ui.selection_info_state import SelectionInfoState, selection_info_state_for
from chemvas.ui.selection_outline_state import (
    selection_outlines_for,
    set_selection_outlines_for,
)
from chemvas.ui.selection_style_state import (
    SelectionStyleState,
)
from PyQt6 import sip
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsScene,
)


class _FakeScene:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear(self) -> None:
        self.clear_calls += 1


def _attach_minimal_runtime_state(canvas) -> None:
    canvas.renderer = Renderer()
    canvas.runtime_state = SimpleNamespace(
        graph_state=graph_state_for(canvas),
        rotation_state=rotation_state_for(canvas),
        insert_state=insert_state_for(canvas),
        mark_registry=mark_registry_for(canvas),
        hover_preview_state=HoverState(),
    )


class CanvasSceneResetServiceTest(unittest.TestCase):
    def test_actual_qt_pre_destructive_failure_preserves_scene_and_history(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class BlockingFailureScene(QGraphicsScene):
            fail_blocking = False

            def blockSignals(self, blocked: bool) -> bool:
                if blocked and self.fail_blocking:
                    raise RuntimeError("signal block failed before clear")
                return super().blockSignals(blocked)

        scene = BlockingFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        command = AddSceneItemsCommand(items=[item], item_states=[{"kind": "shape"}])
        history = canvas.services.history_service.state.history
        history.append(command)
        callback = mock.Mock()
        selection_info_state_for(canvas).callback = callback
        original_model = canvas.model
        scene.fail_blocking = True

        with self.assertRaisesRegex(
            RuntimeError,
            "signal block failed before clear",
        ):
            canvas.services.document.canvas_scene_reset_service.clear_scene()

        self.assertIs(canvas.model, original_model)
        self.assertEqual(scene.items(), [item])
        self.assertFalse(sip.isdeleted(item))
        self.assertEqual(history, [command])
        self.assertIs(selection_info_state_for(canvas).callback, callback)
        callback.assert_not_called()
        scene.fail_blocking = False
        # The session service retries clear_scene after a failure; a
        # pre-destructive failure must leave the service fully retryable.
        canvas.services.document.canvas_scene_reset_service.clear_scene()
        self.assertEqual(scene.items(), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
        callback.assert_called_once_with("", "")
        canvas.services.history_service.undo()
        self.assertEqual(scene.items(), [])
        canvas.close()
        app.processEvents()

    def test_actual_qt_clear_fail_before_mutation_preserves_scene_and_history(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("clear failed before touching the scene")

        class ImmediateFailureScene(QGraphicsScene):
            def clear(self) -> None:
                raise primary

        scene = ImmediateFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        command = AddSceneItemsCommand(items=[item], item_states=[{"kind": "shape"}])
        history = canvas.services.history_service.state.history
        history.append(command)
        original_model = canvas.model

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.document.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertIs(canvas.model, original_model)
        self.assertEqual(QGraphicsScene.items(scene), [item])
        self.assertFalse(sip.isdeleted(item))
        self.assertEqual(history, [command])
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_actual_qt_clear_does_not_call_extension_clear_selection_afterward(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class CachedSelectionScene(QGraphicsScene):
            cached_item = None
            clear_selection_calls = 0

            def clearSelection(self) -> None:
                self.clear_selection_calls += 1
                if self.cached_item is not None:
                    # This becomes an invalid C++ access if the reset invokes
                    # the extension after QGraphicsScene.clear().
                    self.cached_item.isSelected()
                QGraphicsScene.clearSelection(self)

        scene = CachedSelectionScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        atom_id = canvas.services.structure.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        item = atom_items_for(canvas)[atom_id]
        scene.cached_item = item

        canvas.services.document.canvas_scene_reset_service.clear_scene()

        self.assertEqual(scene.clear_selection_calls, 0)
        self.assertTrue(sip.isdeleted(item))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(atom_items_for(canvas), {})
        scene.cached_item = None
        canvas.close()
        app.processEvents()

    def test_actual_qt_partial_clear_raise_is_classified_as_destructive(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("clear failed after deleting one item")

        class PartialFailureScene(QGraphicsScene):
            target = None
            failed = False

            def clear(self) -> None:
                if not self.failed and self.target is not None:
                    self.failed = True
                    QGraphicsScene.removeItem(self, self.target)
                    sip.delete(self.target)
                    raise primary
                QGraphicsScene.clear(self)

        scene = PartialFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        canvas.services.structure.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)
        target = scene.addRect(30.0, 0.0, 10.0, 10.0)
        scene.target = target
        history = canvas.services.history_service.state.history
        history.append(
            AddSceneItemsCommand(
                items=[target],
                item_states=[{"kind": "shape"}],
            )
        )

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.document.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertTrue(sip.isdeleted(target))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(atom_items_for(canvas), {})
        self.assertEqual(history, [])
        scene.target = None
        canvas.close()
        app.processEvents()

    def test_actual_qt_mid_apply_failure_finishes_consistent_empty_reset(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class SelectiveDeletingScene(QGraphicsScene):
            target = None

            def clear(self) -> None:
                if self.target is not None and not sip.isdeleted(self.target):
                    if self.target.scene() is self:
                        QGraphicsScene.removeItem(self, self.target)
                    sip.delete(self.target)
                QGraphicsScene.clear(self)

        canvas = CanvasView()
        deleting_scene = SelectiveDeletingScene()
        canvas.setScene(deleting_scene)
        canvas.services.structure.canvas_atom_mutation_service.add_atom(
            "C",
            10.0,
            20.0,
        )
        history = canvas.services.history_service.state.history
        retained_item = canvas.scene().addRect(30.0, 0.0, 10.0, 10.0)
        history_command = AddSceneItemsCommand(
            items=[retained_item],
            item_states=[{"kind": "shape"}],
        )
        history.append(history_command)
        deleting_scene.target = retained_item
        selection_callback = mock.Mock()
        selection_info_state_for(canvas).callback = selection_callback
        service = canvas.services.document.canvas_scene_reset_service

        service.hit_testing_service.mark_spatial_index_dirty = mock.Mock(
            side_effect=RuntimeError("reset failed after replacing the model")
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "reset failed after replacing the model",
        ):
            service.clear_scene()

        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.model.bonds, [])
        self.assertEqual(canvas.scene().items(), [])
        self.assertEqual(graph_state_for(canvas).atom_neighbors, {})
        self.assertEqual(graph_state_for(canvas).atom_bond_ids, {})
        self.assertEqual(atom_items_for(canvas), {})
        self.assertEqual(bond_items_for(canvas), {})
        self.assertEqual(history, [])
        self.assertTrue(sip.isdeleted(retained_item))
        # A failed destructive reset must not leave an undo command that can
        # dereference the deleted C++ item wrapper.
        canvas.services.history_service.undo()
        self.assertEqual(history, [])
        self.assertIs(
            selection_info_state_for(canvas).callback,
            selection_callback,
        )
        selection_callback.assert_not_called()
        canvas.close()
        app.processEvents()

    def test_successful_qt_clear_discards_deleted_wrapper_history(self) -> None:
        script = textwrap.dedent(
            """
            import os
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PyQt6.QtWidgets import QApplication
            from chemvas.ui.canvas_view import CanvasView
            from chemvas.ui.history_commands import AddSceneItemsCommand
            from chemvas.ui.selection_info_state import selection_info_state_for
            app = QApplication.instance() or QApplication([])
            canvas = CanvasView()
            item = canvas.scene().addRect(0, 0, 10, 10)
            history = canvas.services.history_service.state.history
            history.append(AddSceneItemsCommand(items=[item], item_states=[{}]))
            selection_info_state_for(canvas).callback = None
            canvas.services.document.canvas_scene_reset_service.clear_scene()
            assert history == []
            canvas.services.history_service.undo()
            canvas.close()
            app.processEvents()
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_empty_status_publication_reentry_publishes_once(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        canvas = CanvasView()
        canvas.services.structure.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        service = canvas.services.document.canvas_scene_reset_service
        published: list[tuple[str, str]] = []

        def reentrant_callback(formula: str, mass: str) -> None:
            published.append((formula, mass))
            # A status observer may trigger another reset (e.g. opening a
            # document from the callback); publication must not recurse.
            service.clear_scene()

        selection_info_state_for(canvas).callback = reentrant_callback

        service.clear_scene()

        self.assertEqual(published, [("", "")])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(canvas.scene().items(), [])
        selection_info_state_for(canvas).callback = None
        canvas.close()
        app.processEvents()

    def test_clear_scene_resets_canvas_state_and_clears_previews(self) -> None:
        scene = _FakeScene()
        apply_insert_session_state = mock.Mock()
        selection_callback = mock.Mock()
        selected_highlight = object()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(dummy=True),
            services=canvas_runtime_services(
                hit_testing_service=SimpleNamespace(
                    mark_spatial_index_dirty=mock.Mock()
                ),
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
        _attach_minimal_runtime_state(canvas)
        set_atom_coords_3d_for(canvas, {1: (1.0, 2.0, 3.0)})
        hover_state = hover_state_for(canvas)
        hover_state.items = [object()]
        hover_state.atom_id = 3
        hover_state.bond_id = 4
        hover_state.style = "single:1:10.0:20.0"
        set_selection_outlines_for(canvas, [object()])
        set_active_handles_for(canvas, [object()])
        set_handle_target_for(canvas, object())

        CanvasSceneResetService(
            canvas,
            hit_testing_service=canvas.services.selection.hit_testing_service,
        ).clear_scene()

        self.assertEqual(scene.clear_calls, 1)
        self.assertEqual(hover_state_for(canvas).items, [])
        self.assertIsNone(hover_state_for(canvas).atom_id)
        self.assertIsNone(hover_state_for(canvas).bond_id)
        self.assertIsNone(hover_state_for(canvas).style)
        self.assertIsInstance(canvas.model, MoleculeModel)
        canvas.services.selection.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()
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
        canvas.services.structure.insert_controller.clear_template_preview.assert_called_once_with()
        canvas.services.structure.insert_controller.clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once_with(clear_insert_session())
