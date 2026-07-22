import os
import subprocess
import sys
import textwrap
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from chemvas.domain.document import MoleculeModel
from chemvas.domain.transactions import HistoryStackSnapshot
from chemvas.features.hover import HoverState
from chemvas.ui.atom_coords_access import atom_coords_3d_for, set_atom_coords_3d_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_graph_state import CanvasGraphState, graph_state_for
from chemvas.ui.canvas_history_state import CanvasHistoryState, history_state_for
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_insert_state import CanvasInsertState, insert_state_for
from chemvas.ui.canvas_mark_registry import CanvasMarkRegistry, mark_registry_for
from chemvas.ui.canvas_rotation_preview_state import (
    CanvasRotationPreviewState,
    rotation_preview_state_for,
)
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
from chemvas.ui.canvas_window_access import history_service_for_canvas
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
    selection_style_state_for,
)
from PyQt6 import sip
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


class _FakeScene:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear(self) -> None:
        self.clear_calls += 1


def _attach_minimal_runtime_state(canvas) -> None:
    canvas.runtime_state = SimpleNamespace(
        graph_state=graph_state_for(canvas),
        rotation_state=rotation_state_for(canvas),
        rotation_preview_state=rotation_preview_state_for(canvas),
        insert_state=insert_state_for(canvas),
        mark_registry=mark_registry_for(canvas),
        hover_preview_state=HoverState(),
    )


class CanvasSceneResetServiceTest(unittest.TestCase):
    def test_qt_document_snapshot_deletion_finishes_consistent_empty_reset(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("document snapshot deleted a scene item")

        canvas = CanvasView()
        scene = canvas.scene()
        canvas.model.add_atom("C", 1.0, 2.0)
        target = scene.addRect(0.0, 0.0, 10.0, 10.0)

        class PoisonNote(QGraphicsTextItem):
            armed = False

            def toHtml(self) -> str:
                if self.armed:
                    self.armed = False
                    QGraphicsScene.removeItem(scene, target)
                    sip.delete(target)
                    raise primary
                return QGraphicsTextItem.toHtml(self)

        note = PoisonNote("poison")
        scene.addItem(note)
        note_items_for(canvas).append(note)
        note.armed = True
        history = canvas.services.history_service.state.history
        command = AddSceneItemsCommand(
            items=[target],
            item_states=[{"kind": "shape"}],
        )
        history.append(command)
        callback = mock.Mock()
        selection_info_state_for(canvas).callback = callback

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertTrue(sip.isdeleted(target))
        self.assertTrue(sip.isdeleted(note))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
        self.assertIs(selection_info_state_for(canvas).callback, callback)
        callback.assert_not_called()
        canvas.close()
        app.processEvents()

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
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(canvas.model, original_model)
        self.assertEqual(scene.items(), [item])
        self.assertFalse(sip.isdeleted(item))
        self.assertEqual(history, [command])
        self.assertIs(selection_info_state_for(canvas).callback, callback)
        callback.assert_not_called()
        scene.fail_blocking = False
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
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertIs(canvas.model, original_model)
        self.assertEqual(QGraphicsScene.items(scene), [item])
        self.assertFalse(sip.isdeleted(item))
        self.assertEqual(history, [command])
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_qt_port_capture_side_effect_uses_base_destructive_recovery(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class CapturePoisoningScene(QGraphicsScene):
            target = None
            armed = True

            @property
            def clear(self):
                if self.armed and self.target is not None:
                    self.armed = False
                    QGraphicsScene.removeItem(self, self.target)
                    sip.delete(self.target)
                return lambda: QGraphicsScene.clear(self)

            @property
            def blockSignals(self):
                raise AttributeError("later scene port capture failed")

        scene = CapturePoisoningScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        canvas.model.add_atom("C", 1.0, 2.0)
        target = scene.addRect(0.0, 0.0, 10.0, 10.0)
        scene.target = target
        history = canvas.services.history_service.state.history
        history.append(
            AddSceneItemsCommand(
                items=[target],
                item_states=[{"kind": "shape"}],
            )
        )

        with self.assertRaises(AttributeError):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertTrue(sip.isdeleted(target))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
        scene.target = None
        canvas.close()
        app.processEvents()

    def test_history_preflight_deletion_discards_deleted_wrapper_command(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("history capture deleted a scene item")

        canvas = CanvasView()
        scene = canvas.scene()
        canvas.model.add_atom("C", 1.0, 2.0)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        command = AddSceneItemsCommand(
            items=[item],
            item_states=[{"kind": "shape"}],
        )

        class DeletingHistoryService:
            def __init__(self) -> None:
                self._state = CanvasHistoryState(
                    history=[command],
                    redo_stack=[],
                )
                self.armed = True

            @property
            def state(self):
                if self.armed:
                    self.armed = False
                    QGraphicsScene.removeItem(scene, item)
                    sip.delete(item)
                    raise primary
                return self._state

            @state.setter
            def state(self, value) -> None:
                self._state = value

            def notify_change(self) -> None:
                return None

        history_service = DeletingHistoryService()
        canvas.services.history_service = history_service

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertTrue(sip.isdeleted(item))
        self.assertTrue(sip.isdeleted(command.items[0]))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history_service.state.history, [])
        self.assertEqual(history_service.state.redo_stack, [])
        canvas.close()
        app.processEvents()

    def test_history_state_getter_poison_is_restored_before_qt_clear(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        canvas = CanvasView()
        scene = canvas.scene()
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        original_entry = object()
        injected_entry = object()
        state = CanvasHistoryState(history=[original_entry])

        class PoisoningHistoryService:
            def __init__(self) -> None:
                self._state = state
                self.armed = True

            @property
            def state(self):
                if self.armed:
                    self.armed = False
                    self._state.history.append(injected_entry)
                return self._state

            @state.setter
            def state(self, value) -> None:
                self._state = value

            def notify_change(self) -> None:
                return None

        history_service = PoisoningHistoryService()
        canvas.services.history_service = history_service

        with self.assertRaisesRegex(
            RuntimeError,
            "history preflight changed callback-free authority",
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(state.history, [original_entry])
        self.assertNotIn(injected_entry, state.history)
        self.assertEqual(QGraphicsScene.items(scene), [item])
        self.assertFalse(sip.isdeleted(item))
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_private_history_backing_getter_cannot_redefine_reset_baseline(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        canvas = CanvasView()
        canvas.model.add_atom("C", 1.0, 2.0)
        injected_entry = object()

        class DescriptorHistoryState:
            def __init__(self) -> None:
                self._history: list[object] = []
                self._redo_stack: list[object] = []
                self._enabled = True
                self._limit = 17
                self.armed = True

            @property
            def history(self) -> list[object]:
                if self.armed:
                    self.armed = False
                    self._history.append(injected_entry)
                return self._history

            @history.setter
            def history(self, value: list[object]) -> None:
                self._history = value

            @property
            def redo_stack(self) -> list[object]:
                return self._redo_stack

            @redo_stack.setter
            def redo_stack(self, value: list[object]) -> None:
                self._redo_stack = value

            @property
            def enabled(self) -> bool:
                return self._enabled

            @enabled.setter
            def enabled(self, value: bool) -> None:
                self._enabled = value

            @property
            def limit(self) -> int:
                return self._limit

            @limit.setter
            def limit(self, value: int) -> None:
                self._limit = value

        state = DescriptorHistoryState()

        class HistoryService:
            def __init__(self) -> None:
                self._state = state

            @property
            def state(self) -> DescriptorHistoryState:
                return self._state

            @state.setter
            def state(self, value: DescriptorHistoryState) -> None:
                self._state = value

            @staticmethod
            def notify_change() -> None:
                return None

        canvas.services.history_service = HistoryService()

        with self.assertRaisesRegex(
            RuntimeError,
            "history preflight changed callback-free authority",
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(state._history, [])
        self.assertNotIn(injected_entry, state._history)
        self.assertEqual(state._redo_stack, [])
        self.assertTrue(state._enabled)
        self.assertEqual(state._limit, 17)
        self.assertEqual(set(canvas.model.atoms), {0})
        canvas.close()
        app.processEvents()

    def test_ambiguous_private_history_backings_fail_before_reset(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        canvas = CanvasView()
        canvas.model.add_atom("N", 3.0, 4.0)
        public_state = CanvasHistoryState()
        private_state = CanvasHistoryState()
        canvas.services.history_service = SimpleNamespace(
            state=public_state,
            _state=private_state,
            notify_change=lambda: None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "ambiguous callback-free scene-reset history stack backings",
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(set(canvas.model.atoms), {0})
        self.assertEqual(public_state.history, [])
        self.assertEqual(private_state.history, [])
        canvas.close()
        app.processEvents()

    def test_history_policy_getter_poison_is_restored_before_qt_clear(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class PoisoningPolicyState(CanvasHistoryState):
            def __init__(self) -> None:
                super().__init__(enabled=True, limit=17)
                self.armed = True

            def __getattribute__(self, name: str):
                if name == "enabled" and object.__getattribute__(self, "armed"):
                    object.__setattr__(self, "armed", False)
                    object.__setattr__(self, "enabled", False)
                return object.__getattribute__(self, name)

        canvas = CanvasView()
        scene = canvas.scene()
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        state = PoisoningPolicyState()
        original_entry = object()
        state.history.append(original_entry)
        history_service = SimpleNamespace(
            state=state,
            notify_change=lambda: None,
        )
        canvas.services.history_service = history_service

        with self.assertRaisesRegex(
            RuntimeError,
            "history preflight changed callback-free authority",
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 17)
        self.assertEqual(state.history, [original_entry])
        self.assertEqual(QGraphicsScene.items(scene), [item])
        self.assertFalse(sip.isdeleted(item))
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_qt_clear_runtime_poison_is_not_classified_pre_destructive(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("clear poisoned runtime before failing")

        class RuntimePoisoningScene(QGraphicsScene):
            canvas = None

            def clear(self) -> None:
                assert self.canvas is not None
                self.canvas.model = MoleculeModel()
                raise primary

        scene = RuntimePoisoningScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        scene.canvas = canvas
        canvas.model.add_atom("C", 1.0, 2.0)
        target = scene.addRect(0.0, 0.0, 10.0, 10.0)
        history = canvas.services.history_service.state.history
        history.append(
            AddSceneItemsCommand(
                items=[target],
                item_states=[{"kind": "shape"}],
            )
        )

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
        scene.canvas = None
        canvas.close()
        app.processEvents()

    def test_qt_permanent_partial_clear_failure_bypasses_extension_on_recovery(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("partial clear remains unavailable")

        class PermanentFailureScene(QGraphicsScene):
            target = None
            clear_calls = 0

            def clear(self) -> None:
                self.clear_calls += 1
                if self.clear_calls == 1 and self.target is not None:
                    QGraphicsScene.removeItem(self, self.target)
                    sip.delete(self.target)
                raise primary

        scene = PermanentFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        canvas.model.add_atom("C", 1.0, 2.0)
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        target = scene.addRect(20.0, 0.0, 10.0, 10.0)
        scene.target = target
        history = canvas.services.history_service.state.history
        history.append(
            AddSceneItemsCommand(
                items=[target],
                item_states=[{"kind": "shape"}],
            )
        )

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertEqual(scene.clear_calls, 1)
        self.assertTrue(sip.isdeleted(target))
        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
        scene.target = None
        canvas.close()
        app.processEvents()

    def test_qt_normal_noop_clear_verification_finishes_destructive_recovery(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)

        class NoOpClearScene(QGraphicsScene):
            def clear(self) -> None:
                return None

        scene = NoOpClearScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        canvas.model.add_atom("C", 1.0, 2.0)
        target = scene.addRect(0.0, 0.0, 10.0, 10.0)
        history = canvas.services.history_service.state.history
        history.append(
            AddSceneItemsCommand(
                items=[target],
                item_states=[{"kind": "shape"}],
            )
        )
        selection_info_state_for(canvas).callback = None

        with self.assertRaisesRegex(
            RuntimeError,
            "scene reset left graphics items behind",
        ):
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(QGraphicsScene.items(scene), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history, [])
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
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "N",
            0.0,
            0.0,
        )
        item = atom_items_for(canvas)[atom_id]
        scene.cached_item = item

        canvas.services.canvas_scene_reset_service.clear_scene()

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
        canvas.services.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)
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
            canvas.services.canvas_scene_reset_service.clear_scene()

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
        canvas.services.canvas_atom_mutation_service.add_atom(
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
        service = canvas.services.canvas_scene_reset_service

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

    def test_callback_restore_cannot_leave_history_contaminated(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        canvas = CanvasView()
        history = canvas.services.history_service.state.history
        history_entry = object()
        poison_entry = object()
        history.append(history_entry)
        callback = mock.Mock()

        class PoisoningSelectionInfo:
            def __init__(self) -> None:
                self.armed = False
                self.callback = callback
                self.signature = None
                self.pending_signature = None
                self.cache = ("old", "status")
                self.rdkit_warmup_pending = False
                self.armed = True

            def __setattr__(self, name: str, value: object) -> None:
                object.__setattr__(self, name, value)
                if (
                    name == "callback"
                    and value is callback
                    and object.__getattribute__(self, "armed")
                ):
                    history.append(poison_entry)

        selection_info = PoisoningSelectionInfo()
        canvas.runtime_state.selection_info_state = selection_info

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(selection_info.callback, callback)
        self.assertEqual(history, [history_entry])
        self.assertNotIn(poison_entry, history)
        callback.assert_called_once_with("", "")
        canvas.close()
        app.processEvents()

    def test_callback_restore_cannot_change_history_policy(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        canvas = CanvasView()
        history = canvas.services.history_service
        callback = mock.Mock()
        before_enabled = history.state.enabled
        before_limit = history.state.limit

        class PolicyPoisoningSelectionInfo:
            def __init__(self) -> None:
                self.armed = False
                self.callback = callback
                self.signature = None
                self.pending_signature = None
                self.cache = ("old", "status")
                self.rdkit_warmup_pending = False
                self.armed = True

            def __setattr__(self, name: str, value: object) -> None:
                object.__setattr__(self, name, value)
                if (
                    name == "callback"
                    and value is callback
                    and object.__getattribute__(self, "armed")
                ):
                    history.state.enabled = False
                    history.state.limit = 1

        selection_info = PolicyPoisoningSelectionInfo()
        canvas.runtime_state.selection_info_state = selection_info

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(selection_info.callback, callback)
        self.assertIs(history.state.enabled, before_enabled)
        self.assertEqual(history.state.limit, before_limit)
        callback.assert_called_once_with("", "")
        canvas.close()
        app.processEvents()

    def test_history_restore_poisoning_callback_is_closed_in_reverse_order(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        primary = RuntimeError("signal block failed before clear")

        class BlockingFailureScene(QGraphicsScene):
            def blockSignals(self, blocked: bool) -> bool:
                if blocked:
                    raise primary
                return QGraphicsScene.blockSignals(self, blocked)

        scene = BlockingFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        selection_info = selection_info_state_for(canvas)
        callback = mock.Mock()
        selection_info.callback = callback
        history_entry = object()

        class CallbackPoisoningHistoryState(CanvasHistoryState):
            poison_callback = False

            def __setattr__(self, name: str, value: object) -> None:
                object.__setattr__(self, name, value)
                if self.poison_callback and name in {"history", "redo_stack"}:
                    selection_info.callback = None

        state = CallbackPoisoningHistoryState(
            history=[history_entry],
            redo_stack=[],
        )
        state.poison_callback = True
        canvas.services.history_service = SimpleNamespace(
            state=state,
            notify_change=lambda: None,
        )

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertIs(selection_info.callback, callback)
        self.assertEqual(state.history, [history_entry])
        self.assertEqual(state.redo_stack, [])
        self.assertEqual(QGraphicsScene.items(scene), [item])
        QGraphicsScene.blockSignals(scene, True)
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_pre_destructive_history_restore_cannot_poison_model_root(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        primary = RuntimeError("signal block failed before clear")

        class BlockingFailureScene(QGraphicsScene):
            def blockSignals(self, blocked: bool) -> bool:
                if blocked:
                    raise primary
                return QGraphicsScene.blockSignals(self, blocked)

        class ModelPoisoningHistoryState(CanvasHistoryState):
            canvas = None
            armed = False

            def __setattr__(self, name: str, value: object) -> None:
                object.__setattr__(self, name, value)
                if self.armed and name in {"history", "redo_stack"}:
                    replacement = MoleculeModel()
                    replacement.add_atom("O", 99.0, 99.0)
                    self.canvas.model = replacement

        scene = BlockingFailureScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        canvas.model.add_atom("C", 1.0, 2.0)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        history_entry = object()
        state = ModelPoisoningHistoryState(
            history=[history_entry],
            redo_stack=[],
        )
        state.canvas = canvas
        state.armed = True
        canvas.services.history_service = SimpleNamespace(
            state=state,
            notify_change=lambda: None,
        )
        original_model = canvas.model

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertIs(canvas.model, original_model)
        self.assertEqual(canvas.model.atoms[0].element, "C")
        self.assertEqual(QGraphicsScene.items(scene), [item])
        self.assertEqual(state.history, [history_entry])
        QGraphicsScene.blockSignals(scene, True)
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

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
        self.assertEqual(history, [])
        self.assertIs(
            selection_info_state_for(canvas).callback,
            corrupt_after_empty_status,
        )
        selection_info_state_for(canvas).callback = None
        canvas.close()

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
            canvas.services.canvas_scene_reset_service.clear_scene()
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

    def test_clear_override_scene_replacement_is_cleared_and_restored(self) -> None:
        app = QApplication.instance() or QApplication([])

        class ReplacingScene(QGraphicsScene):
            canvas = None
            replacement = None

            def clear(self) -> None:
                assert self.canvas is not None and self.replacement is not None
                self.canvas.setScene(self.replacement)
                QGraphicsScene.clear(self)

        original = ReplacingScene()
        replacement = QGraphicsScene()
        replacement.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = CanvasView()
        canvas.setScene(original)
        original.canvas = canvas
        original.replacement = replacement
        selection_info_state_for(canvas).callback = None

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(canvas.scene(), original)
        self.assertEqual(QGraphicsScene.items(replacement), [])
        self.assertEqual(QGraphicsScene.items(original), [])
        original.canvas = None
        original.replacement = None
        canvas.close()
        app.processEvents()

    def test_publication_scene_detach_restores_captured_qt_root(self) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        original_scene = QGraphicsView.scene(canvas)
        canvas.services.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)

        def detach_scene(_formula: str, _mass: str) -> None:
            QGraphicsView.setScene(canvas, None)

        selection_info = selection_info_state_for(canvas)
        selection_info.callback = detach_scene

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(QGraphicsView.scene(canvas), original_scene)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(QGraphicsScene.items(original_scene), [])
        self.assertIs(selection_info.callback, detach_scene)
        selection_info.callback = None
        canvas.close()
        app.processEvents()

    def test_signal_block_deletion_is_reclassified_and_discards_history(self) -> None:
        app = QApplication.instance() or QApplication([])
        primary = RuntimeError("blocking deleted an item")

        class PoisoningScene(QGraphicsScene):
            target = None
            armed = True

            def blockSignals(self, blocked: bool) -> bool:
                if blocked and self.armed:
                    self.armed = False
                    QGraphicsScene.removeItem(self, self.target)
                    sip.delete(self.target)
                    raise primary
                if blocked:
                    raise primary
                return QGraphicsScene.blockSignals(self, blocked)

        scene = PoisoningScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        scene.target = item
        history = canvas.services.history_service.state.history
        history.append(AddSceneItemsCommand(items=[item], item_states=[{}]))

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertEqual(history, [])
        self.assertEqual(QGraphicsScene.items(scene), [])
        scene.target = None
        canvas.close()
        app.processEvents()

    def test_publication_root_replacements_are_closed(self) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        original_info = selection_info_state_for(canvas)
        original_history = canvas.services.history_service
        replacement_info = SelectionInfoState(callback=lambda *_: None)
        replacement_history = SimpleNamespace(
            state=CanvasHistoryState(),
            notify_change=lambda: None,
        )

        def replace_roots(_formula: str, _mass: str) -> None:
            canvas.runtime_state.selection_info_state = replacement_info
            canvas.services.history_service = replacement_history

        original_info.callback = replace_roots
        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(selection_info_state_for(canvas), original_info)
        self.assertIs(canvas.services.history_service, original_history)
        self.assertIs(original_info.callback, replace_roots)
        original_info.callback = None
        canvas.close()
        app.processEvents()

    def test_publication_runtime_history_alias_replacements_are_closed(self) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        canvas.services.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)
        original_info = selection_info_state_for(canvas)
        original_history_service = canvas.runtime_state.history_service
        original_history_state = canvas.runtime_state.history_state
        replacement_history_service = SimpleNamespace(
            state=CanvasHistoryState(),
            notify_change=lambda: None,
        )
        replacement_history_state = CanvasHistoryState(limit=7)

        def replace_runtime_aliases(_formula: str, _mass: str) -> None:
            canvas.runtime_state.history_service = replacement_history_service
            canvas.runtime_state.history_state = replacement_history_state

        original_info.callback = replace_runtime_aliases
        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(
            canvas.runtime_state.history_service,
            original_history_service,
        )
        self.assertIs(canvas.runtime_state.history_state, original_history_state)
        self.assertIs(canvas.services.history_service, original_history_service)
        self.assertIs(history_service_for_canvas(canvas), original_history_service)
        self.assertIs(history_state_for(canvas), original_history_state)
        original_info.callback = None
        canvas.close()
        app.processEvents()

    def test_publication_graph_root_replacement_is_closed(self) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        original_graph = graph_state_for(canvas)
        replacement_graph = CanvasGraphState(
            atom_neighbors={99: {100}},
            atom_bond_ids={99: {7}},
            graph_version=42,
        )

        def replace_graph_root(_formula: str, _mass: str) -> None:
            canvas.runtime_state.graph_state = replacement_graph

        selection_info = selection_info_state_for(canvas)
        selection_info.callback = replace_graph_root

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(graph_state_for(canvas), original_graph)
        self.assertEqual(original_graph.atom_neighbors, {})
        self.assertEqual(original_graph.atom_bond_ids, {})
        self.assertEqual(original_graph.graph_version, 0)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(QGraphicsScene.items(canvas.scene()), [])
        self.assertIs(selection_info.callback, replace_graph_root)
        selection_info.callback = None
        canvas.close()
        app.processEvents()

    def test_publication_cannot_poison_cached_reset_state_aliases(self) -> None:
        app = QApplication.instance() or QApplication([])
        canvas = CanvasView()
        service = canvas.services.canvas_scene_reset_service
        original_graph = graph_state_for(canvas)
        original_aliases = {
            "graph": original_graph,
            "rotation": rotation_state_for(canvas),
            "rotation_preview": rotation_preview_state_for(canvas),
            "insert_state": insert_state_for(canvas),
            "marks": mark_registry_for(canvas),
        }
        replacements = {
            "graph": CanvasGraphState(atom_neighbors={99: {100}}, graph_version=7),
            "rotation": CanvasRotationState(total_angle=2.5),
            "rotation_preview": CanvasRotationPreviewState(center=object()),
            "insert_state": CanvasInsertState(smiles_active=True),
            "marks": CanvasMarkRegistry({99: [object()]}),
        }

        def poison_aliases(_formula: str, _mass: str) -> None:
            for name, replacement in replacements.items():
                setattr(service, name, replacement)

        selection_info = selection_info_state_for(canvas)
        selection_info.callback = poison_aliases
        service.clear_scene()

        for name, original in original_aliases.items():
            self.assertIs(getattr(service, name), original)

        selection_info.callback = None
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)
        self.assertEqual(original_graph.atom_neighbors, {0: set()})

        service.clear_scene()

        self.assertEqual(original_graph.atom_neighbors, {})
        for name, original in original_aliases.items():
            self.assertIs(getattr(service, name), original)
        canvas.close()
        app.processEvents()

    def test_port_capture_registry_poison_is_restored_pre_destructively(self) -> None:
        app = QApplication.instance() or QApplication([])
        primary = RuntimeError("later port capture failed")

        class RegistryPoisonScene(QGraphicsScene):
            canvas = None

            @property
            def clear(self):
                atom_items_for(self.canvas).clear()
                return lambda: QGraphicsScene.clear(self)

            @property
            def blockSignals(self):
                raise primary

        scene = RegistryPoisonScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        scene.canvas = canvas
        canvas.services.canvas_atom_mutation_service.add_atom("N", 0.0, 0.0)

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertEqual(len(canvas.model.atoms), 1)
        self.assertEqual(set(atom_items_for(canvas)), {0})
        self.assertEqual(
            QGraphicsScene.items(scene), list(atom_items_for(canvas).values())
        )
        scene.canvas = None
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

    def test_port_capture_selection_poison_is_restored_pre_destructively(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        primary = RuntimeError("later port capture failed")

        class SelectionPoisonScene(QGraphicsScene):
            canvas = None

            @property
            def clear(self):
                selection_style_state_for(self.canvas).selected_items.clear()
                return lambda: QGraphicsScene.clear(self)

            @property
            def blockSignals(self):
                raise primary

        scene = SelectionPoisonScene()
        canvas = CanvasView()
        canvas.setScene(scene)
        scene.canvas = canvas
        item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        selection_style = selection_style_state_for(canvas)
        selected_items = selection_style.selected_items
        selected_items.append(item)
        selection_style.suspend_outline = True

        with self.assertRaises(RuntimeError) as raised:
            canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertIs(selection_style.selected_items, selected_items)
        self.assertEqual(selection_style.selected_items, [item])
        self.assertTrue(selection_style.suspend_outline)
        self.assertEqual(QGraphicsScene.items(scene), [item])
        scene.canvas = None
        QGraphicsScene.clear(scene)
        canvas.close()
        app.processEvents()

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

    def test_exact_fake_block_side_effect_restores_or_fails_closed(self) -> None:
        for reversible in (True, False):
            with self.subTest(reversible=reversible):
                primary = RuntimeError("blocking removed an exact fake item")

                class ExactScene:
                    def __init__(self) -> None:
                        self.item = object()
                        self._items = [self.item]
                        self.clear_calls = 0

                    def items(self):
                        return list(self._items)

                    def clearSelection(self) -> None:
                        return None

                    def clear(self) -> None:
                        self.clear_calls += 1
                        self._items.clear()

                    def signalsBlocked(self) -> bool:
                        return False

                    def blockSignals(
                        self,
                        _blocked: bool,
                        _primary: RuntimeError = primary,
                    ) -> bool:
                        self._items.clear()
                        raise _primary

                if reversible:

                    class Scene(ExactScene):
                        def addItem(self, item) -> None:
                            self._items.append(item)

                        def removeItem(self, item) -> None:
                            self._items.remove(item)

                else:
                    Scene = ExactScene

                scene = Scene()
                model = MoleculeModel()
                model.add_atom("C", 1.0, 2.0)
                marker = object()
                history_state = CanvasHistoryState(history=[marker])
                history_service = SimpleNamespace(
                    state=history_state,
                    notify_change=lambda: None,
                )
                canvas = SimpleNamespace(
                    scene=lambda scene=scene: scene,
                    model=model,
                    history_state=history_state,
                    history_service=history_service,
                    services=SimpleNamespace(history_service=history_service),
                    selection_style_state=SelectionStyleState(),
                    selection_info_state=SelectionInfoState(),
                )
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=SimpleNamespace(
                        mark_spatial_index_dirty=lambda: None,
                    ),
                )

                with self.assertRaises(RuntimeError) as raised:
                    service.clear_scene()

                self.assertIs(raised.exception, primary)
                # The built-in backing list is now the strongest recovery
                # port, so restoration does not depend on optional live
                # add/remove methods.
                self.assertEqual(scene.items(), [scene.item])
                self.assertIs(canvas.model, model)
                self.assertEqual(set(canvas.model.atoms), {0})
                self.assertEqual(history_state.history, [marker])
                self.assertEqual(scene.clear_calls, 0)

    def test_exact_fake_uses_raw_membership_without_calling_live_items(self) -> None:
        primary = RuntimeError("live items must not run during preflight")
        item = object()

        class Scene:
            def __init__(self) -> None:
                self._items = [item]
                self.items_calls = 0
                self.clear_calls = 0

            def items(self):
                self.items_calls += 1
                self._items.clear()
                raise primary

            def clearSelection(self) -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

        scene = Scene()
        model = MoleculeModel()
        model.add_atom("C", 1.0, 2.0)
        history_entry = object()
        history_state = CanvasHistoryState(history=[history_entry])
        history_service = SimpleNamespace(
            state=history_state,
            notify_change=lambda: None,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=model,
            history_state=history_state,
            history_service=history_service,
            services=SimpleNamespace(history_service=history_service),
            selection_style_state=SelectionStyleState(),
            selection_info_state=SelectionInfoState(),
        )
        _attach_minimal_runtime_state(canvas)
        service = CanvasSceneResetService(
            canvas,
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=lambda: None,
            ),
        )

        service.clear_scene()

        self.assertEqual(scene.items_calls, 0)
        self.assertEqual(scene._items, [])
        self.assertEqual(scene.clear_calls, 1)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history_state.history, [history_entry])

    def test_exact_fake_success_rejects_repopulated_membership_root(self) -> None:
        original_item = object()
        injected_item = object()

        class Scene:
            def __init__(self) -> None:
                self._items = [original_item]
                self.clear_calls = 0

            @staticmethod
            def items():
                raise AssertionError("live items must not run")

            @staticmethod
            def clearSelection() -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                captured_backing = self._items
                captured_backing.clear()
                self._items = [injected_item]

        scene = Scene()
        original_items_root = scene._items
        model = MoleculeModel()
        model.add_atom("C", 1.0, 2.0)
        history_entry = object()
        history_state = CanvasHistoryState(history=[history_entry])
        history_service = SimpleNamespace(
            state=history_state,
            notify_change=lambda: None,
        )
        selection_info = SelectionInfoState()
        callback = mock.Mock()
        selection_info.callback = callback
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=model,
            history_state=history_state,
            history_service=history_service,
            services=SimpleNamespace(history_service=history_service),
            selection_style_state=SelectionStyleState(),
            selection_info_state=selection_info,
        )
        _attach_minimal_runtime_state(canvas)
        service = CanvasSceneResetService(
            canvas,
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=lambda: None,
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "callback-free scene membership root",
        ):
            service.clear_scene()

        self.assertGreaterEqual(scene.clear_calls, 2)
        self.assertIs(scene._items, original_items_root)
        self.assertEqual(scene._items, [])
        self.assertNotIn(injected_item, scene._items)
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(history_state.history, [])
        self.assertIs(selection_info.callback, callback)
        callback.assert_not_called()

    def test_exact_fake_block_root_replacement_restores_membership_port(self) -> None:
        primary = RuntimeError("blocking replaced the exact membership root")

        class NamespaceScene:
            def __init__(self) -> None:
                self.item = object()
                self._items = [self.item]
                self.blocked = False
                self.clear_calls = 0

            def items(self):
                return list(self._items)

            def clearSelection(self) -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

            def signalsBlocked(self) -> bool:
                return self.blocked

            def blockSignals(self, blocked: bool) -> bool:
                if blocked:
                    self._items = []
                    raise primary
                previous = self.blocked
                self.blocked = blocked
                return previous

        class SlotScene:
            __slots__ = ("_items", "blocked", "clear_calls", "item")

            def __init__(self) -> None:
                self.item = object()
                self._items = [self.item]
                self.blocked = False
                self.clear_calls = 0

            def items(self):
                return list(self._items)

            def clearSelection(self) -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

            def signalsBlocked(self) -> bool:
                return self.blocked

            def blockSignals(self, blocked: bool) -> bool:
                if blocked:
                    self._items = []
                    raise primary
                previous = self.blocked
                self.blocked = blocked
                return previous

        for scene_type in (NamespaceScene, SlotScene):
            with self.subTest(scene_type=scene_type.__name__):
                scene = scene_type()
                original_items = scene._items
                model = MoleculeModel()
                model.add_atom("C", 1.0, 2.0)
                history_entry = object()
                history_state = CanvasHistoryState(history=[history_entry])
                history_service = SimpleNamespace(
                    state=history_state,
                    notify_change=lambda: None,
                )
                canvas = SimpleNamespace(
                    scene=lambda scene=scene: scene,
                    model=model,
                    history_state=history_state,
                    history_service=history_service,
                    services=SimpleNamespace(history_service=history_service),
                    selection_style_state=SelectionStyleState(),
                    selection_info_state=SelectionInfoState(),
                )
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=SimpleNamespace(
                        mark_spatial_index_dirty=lambda: None,
                    ),
                )

                with self.assertRaises(RuntimeError) as raised:
                    service.clear_scene()

                self.assertIs(raised.exception, primary)
                self.assertIs(scene._items, original_items)
                self.assertEqual(scene.items(), [scene.item])
                self.assertIs(canvas.model, model)
                self.assertEqual(set(canvas.model.atoms), {0})
                self.assertEqual(history_state.history, [history_entry])
                self.assertEqual(scene.clear_calls, 0)

    def test_non_qt_block_restores_namespace_and_slot_scene_roots(self) -> None:
        primary = RuntimeError("blocking replaced the canvas scene root")

        class Scene:
            def __init__(self) -> None:
                self._items: list[object] = []
                self.blocked = False
                self.canvas = None
                self.replacement = None
                self.poison = False
                self.clear_calls = 0

            def items(self):
                return list(self._items)

            def clearSelection(self) -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

            def signalsBlocked(self) -> bool:
                return self.blocked

            def blockSignals(self, blocked: bool) -> bool:
                if blocked and self.poison:
                    self.canvas._scene = self.replacement
                    raise primary
                previous = self.blocked
                self.blocked = blocked
                return previous

        class NamespaceCanvas:
            def scene(self):
                return self._scene

        class SlotCanvas:
            __slots__ = ("__dict__", "_scene")

            def scene(self):
                return self._scene

        for canvas_type in (NamespaceCanvas, SlotCanvas):
            with self.subTest(canvas_type=canvas_type.__name__):
                original = Scene()
                replacement = Scene()
                original_item = object()
                replacement_item = object()
                original._items.append(original_item)
                replacement._items.append(replacement_item)
                model = MoleculeModel()
                model.add_atom("C", 1.0, 2.0)
                history_entry = object()
                history_state = CanvasHistoryState(history=[history_entry])
                history_service = SimpleNamespace(
                    state=history_state,
                    notify_change=lambda: None,
                )
                canvas = canvas_type()
                canvas._scene = original
                canvas.model = model
                canvas.history_state = history_state
                canvas.history_service = history_service
                canvas.services = SimpleNamespace(history_service=history_service)
                canvas.selection_style_state = SelectionStyleState()
                canvas.selection_info_state = SelectionInfoState()
                original.canvas = canvas
                original.replacement = replacement
                original.poison = True
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=SimpleNamespace(
                        mark_spatial_index_dirty=lambda: None,
                    ),
                )

                with self.assertRaises(RuntimeError) as raised:
                    service.clear_scene()

                self.assertIs(raised.exception, primary)
                self.assertIs(canvas._scene, original)
                self.assertEqual(original.items(), [original_item])
                self.assertEqual(replacement.items(), [])
                self.assertIs(canvas.model, model)
                self.assertEqual(set(canvas.model.atoms), {0})
                self.assertEqual(history_state.history, [history_entry])
                self.assertEqual(original.clear_calls, 0)
                self.assertGreaterEqual(replacement.clear_calls, 1)

    def test_non_qt_block_restores_absent_or_none_scene_alias(self) -> None:
        primary = RuntimeError("blocking injected a second canvas scene root")

        class Scene:
            def __init__(self) -> None:
                self._items: list[object] = []
                self.blocked = False
                self.canvas = None
                self.replacement = None
                self.clear_calls = 0

            def items(self):
                return list(self._items)

            @staticmethod
            def clearSelection() -> None:
                return None

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

            def signalsBlocked(self) -> bool:
                return self.blocked

            def blockSignals(self, blocked: bool) -> bool:
                if blocked:
                    self.canvas.scene_obj = self.replacement
                    raise primary
                previous = self.blocked
                self.blocked = blocked
                return previous

        class Canvas:
            def scene(self):
                replacement = getattr(self, "scene_obj", None)
                return replacement if replacement is not None else self._scene

        for initial_alias in ("absent", "none"):
            with self.subTest(initial_alias=initial_alias):
                original = Scene()
                replacement = Scene()
                original_item = object()
                replacement_item = object()
                original._items.append(original_item)
                replacement._items.append(replacement_item)
                model = MoleculeModel()
                model.add_atom("C", 1.0, 2.0)
                history_entry = object()
                history_state = CanvasHistoryState(history=[history_entry])
                history_service = SimpleNamespace(
                    state=history_state,
                    notify_change=lambda: None,
                )
                canvas = Canvas()
                canvas._scene = original
                if initial_alias == "none":
                    canvas.scene_obj = None
                canvas.model = model
                canvas.history_state = history_state
                canvas.history_service = history_service
                canvas.services = SimpleNamespace(history_service=history_service)
                canvas.selection_style_state = SelectionStyleState()
                canvas.selection_info_state = SelectionInfoState()
                original.canvas = canvas
                original.replacement = replacement
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=SimpleNamespace(
                        mark_spatial_index_dirty=lambda: None,
                    ),
                )

                with self.assertRaises(RuntimeError) as raised:
                    service.clear_scene()

                self.assertIs(raised.exception, primary)
                self.assertIs(canvas._scene, original)
                if initial_alias == "absent":
                    self.assertNotIn("scene_obj", vars(canvas))
                else:
                    self.assertIsNone(canvas.scene_obj)
                self.assertIs(canvas.scene(), original)
                self.assertEqual(original.items(), [original_item])
                self.assertEqual(replacement.items(), [])
                self.assertGreaterEqual(replacement.clear_calls, 1)
                self.assertIs(canvas.model, model)
                self.assertEqual(set(canvas.model.atoms), {0})
                self.assertEqual(history_state.history, [history_entry])
                self.assertEqual(original.clear_calls, 0)

    def test_non_qt_ambiguous_raw_scene_roots_abort_before_clear(self) -> None:
        first = _FakeScene()
        second = _FakeScene()
        model = MoleculeModel()
        model.add_atom("C", 1.0, 2.0)
        history_entry = object()
        history_state = CanvasHistoryState(history=[history_entry])
        history_service = SimpleNamespace(
            state=history_state,
            notify_change=lambda: None,
        )

        class Canvas:
            def scene(self):
                return self._scene

        canvas = Canvas()
        canvas._scene = first
        canvas.scene_obj = second
        canvas.model = model
        canvas.history_state = history_state
        canvas.history_service = history_service
        canvas.services = SimpleNamespace(history_service=history_service)
        canvas.selection_style_state = SelectionStyleState()
        canvas.selection_info_state = SelectionInfoState()
        service = CanvasSceneResetService(
            canvas,
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=lambda: None,
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "ambiguous callback-free canvas scene roots",
        ):
            service.clear_scene()

        self.assertIs(canvas._scene, first)
        self.assertIs(canvas.scene_obj, second)
        self.assertIs(canvas.model, model)
        self.assertEqual(set(canvas.model.atoms), {0})
        self.assertEqual(history_state.history, [history_entry])
        self.assertEqual(first.clear_calls, 0)
        self.assertEqual(second.clear_calls, 0)

    def test_exact_fake_port_capture_failure_restores_membership(self) -> None:
        primary = RuntimeError("port capture removed an exact fake item")

        class Scene:
            def __init__(self) -> None:
                self.item = object()
                self._items = [self.item]
                self.clear_calls = 0

            def items(self):
                return list(self._items)

            def addItem(self, item) -> None:
                self._items.append(item)

            def removeItem(self, item) -> None:
                self._items.remove(item)

            @property
            def clearSelection(self):
                self._items.clear()
                raise primary

            def clear(self) -> None:
                self.clear_calls += 1
                self._items.clear()

            def blockSignals(self, _blocked: bool) -> bool:
                return False

            def signalsBlocked(self) -> bool:
                return False

        scene = Scene()
        model = MoleculeModel()
        model.add_atom("C", 1.0, 2.0)
        history_entry = object()
        history_state = CanvasHistoryState(history=[history_entry])
        history_service = SimpleNamespace(
            state=history_state,
            notify_change=lambda: None,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=model,
            history_state=history_state,
            history_service=history_service,
            services=SimpleNamespace(history_service=history_service),
            selection_style_state=SelectionStyleState(),
            selection_info_state=SelectionInfoState(),
        )
        service = CanvasSceneResetService(
            canvas,
            hit_testing_service=SimpleNamespace(
                mark_spatial_index_dirty=lambda: None,
            ),
        )

        with self.assertRaises(RuntimeError) as raised:
            service.clear_scene()

        self.assertIs(raised.exception, primary)
        self.assertEqual(scene.items(), [scene.item])
        self.assertIs(canvas.model, model)
        self.assertEqual(set(canvas.model.atoms), {0})
        self.assertEqual(history_state.history, [history_entry])
        self.assertEqual(scene.clear_calls, 0)

    def test_non_qt_scene_getter_cannot_redefine_raw_history_baseline(self) -> None:
        for raw_backing in (True, False):
            with self.subTest(raw_backing=raw_backing):
                original = object()
                poison = object()

                class Scene:
                    def __init__(self) -> None:
                        self._items: list[object] = []
                        self.clear_calls = 0

                    def clear(self) -> None:
                        self.clear_calls += 1
                        self._items.clear()

                class Canvas:
                    def __init__(
                        self,
                        *,
                        _raw_backing: bool = raw_backing,
                        _original: object = original,
                    ) -> None:
                        scene = Scene()
                        if _raw_backing:
                            self._scene = scene
                        else:
                            self._scene_target = scene
                        self.scene_reads = 0
                        self.armed = True
                        self.model = MoleculeModel()
                        self.model.add_atom("C", 1.0, 2.0)
                        self.history_state = CanvasHistoryState(history=[_original])
                        self.history_service = SimpleNamespace(
                            state=self.history_state,
                            notify_change=lambda: None,
                        )
                        self.services = SimpleNamespace(
                            history_service=self.history_service,
                        )
                        self.selection_style_state = SelectionStyleState()
                        self.selection_info_state = SelectionInfoState()

                    @property
                    def scene(
                        self,
                        _raw_backing: bool = raw_backing,
                        _poison: object = poison,
                    ):
                        self.scene_reads += 1
                        if self.armed:
                            self.armed = False
                            self.history_state.history.append(_poison)
                        target = self._scene if _raw_backing else self._scene_target
                        return lambda: target

                canvas = Canvas()
                _attach_minimal_runtime_state(canvas)
                original_model = canvas.model
                service = CanvasSceneResetService(
                    canvas,
                    hit_testing_service=SimpleNamespace(
                        mark_spatial_index_dirty=lambda: None,
                    ),
                )

                if raw_backing:
                    service.clear_scene()
                    self.assertEqual(canvas.scene_reads, 0)
                    self.assertEqual(canvas.model.atoms, {})
                    scene = canvas._scene
                    self.assertEqual(scene.clear_calls, 1)
                else:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "scene getter changed a preflight authority",
                    ):
                        service.clear_scene()
                    self.assertIs(canvas.model, original_model)
                    self.assertEqual(set(canvas.model.atoms), {0})
                    scene = canvas._scene_target
                    self.assertEqual(scene.clear_calls, 0)

                self.assertEqual(canvas.history_state.history, [original])

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
                        # Deliberately avoid the supported raw ``_scene`` /
                        # ``scene_obj`` backings so this test continues to
                        # exercise the genuinely live descriptor path.
                        self._scene_target = scene
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
                        self._scene = self._scene_target
                        return lambda: self._scene_target

                scene = FlakyScene(
                    fail_block_once=failure_root == "blockSignals",
                )
                canvas = FlakyCanvas(
                    scene,
                    fail_scene_once=failure_root == "scene",
                )
                _attach_minimal_runtime_state(canvas)
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

                self.assertEqual(
                    canvas.scene_port_reads,
                    2 if failure_root == "scene" else 1,
                )
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
        selection_callback = mock.Mock()
        selected_highlight = object()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(dummy=True),
            services=SimpleNamespace(
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
            hit_testing_service=canvas.services.hit_testing_service,
        ).clear_scene()

        self.assertEqual(scene.clear_calls, 2)
        self.assertEqual(hover_state_for(canvas).items, [])
        self.assertIsNone(hover_state_for(canvas).atom_id)
        self.assertIsNone(hover_state_for(canvas).bond_id)
        self.assertIsNone(hover_state_for(canvas).style)
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
        canvas.services.insert_controller.clear_smiles_preview.assert_called_once_with()
        apply_insert_session_state.assert_called_once_with(clear_insert_session())
