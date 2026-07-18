import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import MoleculeModel, serialize_settings
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_document_session_service import (
    CanvasDocumentSessionService,
    _DetachedSceneSnapshot,
    _SceneItemTopologySnapshot,
    _snapshot_canvas_scene,
)
from chemvas.ui.canvas_history_service import CanvasHistoryService
from chemvas.ui.canvas_history_state import CanvasHistoryState, history_state_for
from chemvas.ui.canvas_rotation_preview_controller import (
    CanvasRotationPreviewController,
)
from chemvas.ui.canvas_rotation_preview_state import (
    RotationPreviewItemSnapshot,
    rotation_preview_state_for,
)
from chemvas.ui.canvas_runtime_state import attach_canvas_runtime_state
from chemvas.ui.canvas_scene_reset_service import CanvasSceneResetService
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.history_commands import UpdateSceneItemCommand
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_style_state import (
    SelectionStyleState,
    selection_style_state_for,
)
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
    set_explicit_scene_rect,
    set_explicit_view_scene_rect,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)


class _SceneItem:
    def __init__(self, kind: str = "arrow") -> None:
        self.kind = kind

    def data(self, index: int):
        if index == 0:
            return self.kind
        return None

    def childItems(self):
        return []


class _Scene:
    def __init__(self, selected_items=None) -> None:
        self._selected_items = list(selected_items or [])

    def selectedItems(self):
        return list(self._selected_items)


def _document_services(
    *,
    clear_scene,
    rebuild_bond_adjacency,
    render_model,
    mark_spatial_index_dirty,
):
    return SimpleNamespace(
        canvas_scene_reset_service=SimpleNamespace(clear_scene=clear_scene),
        canvas_graph_service=SimpleNamespace(
            rebuild_bond_adjacency=rebuild_bond_adjacency
        ),
        structure_build_service=SimpleNamespace(
            render_model=render_model,
            ensure_ring_fills_for_model=mock.Mock(),
        ),
        hit_testing_service=SimpleNamespace(
            mark_spatial_index_dirty=mark_spatial_index_dirty
        ),
    )


def _attach_history_service(canvas):
    service = CanvasHistoryService(canvas, history_state_for(canvas))
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    services.history_service = service
    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None and hasattr(runtime_state, "history_service"):
        runtime_state.history_service = service
    return canvas


def _session_service(canvas):
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    hit_testing_service = getattr(services, "hit_testing_service", None)
    if hit_testing_service is None:
        hit_testing_service = SimpleNamespace(mark_spatial_index_dirty=mock.Mock())
        services.hit_testing_service = hit_testing_service
    graph_service = getattr(services, "canvas_graph_service", None)
    if graph_service is None:
        graph_service = SimpleNamespace(rebuild_bond_adjacency=mock.Mock())
        services.canvas_graph_service = graph_service
    structure_build_service = getattr(services, "structure_build_service", None)
    if structure_build_service is None:
        structure_build_service = SimpleNamespace(
            render_model=mock.Mock(),
            ensure_ring_fills_for_model=mock.Mock(),
        )
        services.structure_build_service = structure_build_service
    return CanvasDocumentSessionService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=services.history_service,
    )


def _settings() -> dict:
    return serialize_settings(
        bond_length_px=18.0,
        arrow_line_width=1.5,
        arrow_head_scale=0.4,
        orbital_phase_enabled=True,
        text_font_size=13,
        text_font_weight=600,
        text_italic=False,
        sheet_size="A4",
        sheet_orientation="portrait",
    )


def _canvas_state() -> dict:
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [{"text": "editable", "x": 1.0, "y": 2.0}],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }


def _qt_canvas_with_scene_reset(scene: QGraphicsScene) -> QGraphicsView:
    canvas = QGraphicsView(scene)
    attach_canvas_runtime_state(canvas)
    canvas.model = MoleculeModel()
    hit_testing_service = SimpleNamespace(mark_spatial_index_dirty=mock.Mock())
    reset_service = CanvasSceneResetService(
        canvas,
        hit_testing_service=hit_testing_service,
    )
    canvas.services = _document_services(
        clear_scene=reset_service.clear_scene,
        rebuild_bond_adjacency=mock.Mock(),
        render_model=mock.Mock(),
        mark_spatial_index_dirty=hit_testing_service.mark_spatial_index_dirty,
    )
    _attach_history_service(canvas)
    return canvas


class CanvasDocumentSessionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Keep a strong application wrapper for every real-Qt rollback test.
        # A method-local wrapper can be collected before its widgets on some
        # PyQt/Python combinations, deleting the CanvasView underneath cleanup.
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_apply_state_restores_document_lifecycle_and_reenables_history(
        self,
    ) -> None:
        events = []
        selection_callback = object()
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            clear_scene=mock.Mock(side_effect=lambda: events.append("clear")),
            model="old-model",
            selection_style_state=SelectionStyleState(selected_items=[object()]),
            selection_info_state=SimpleNamespace(
                callback=selection_callback,
                signature=(frozenset({1}), frozenset()),
                pending_signature=(frozenset({1}), frozenset()),
                cache=("C", "12.01"),
                rdkit_warmup_pending=True,
            ),
        )
        canvas.services = _document_services(
            clear_scene=lambda: canvas.clear_scene(),
            rebuild_bond_adjacency=mock.Mock(
                side_effect=lambda: events.append("adjacency")
            ),
            render_model=mock.Mock(side_effect=lambda: events.append("render")),
            mark_spatial_index_dirty=mock.Mock(
                side_effect=lambda: events.append("dirty")
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        history_state_for(canvas).history.append(object())
        history_state_for(canvas).redo_stack.append(object())

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"atoms": []}},
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: events.append("settings"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda _model: events.append("deserialize") or "new-model",
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items",
                side_effect=lambda _canvas, _state: events.append("pre"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state",
                side_effect=lambda _canvas, _state: events.append("projection"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=lambda _canvas, _state: events.append("post"),
            ),
        ):
            service.apply_state({"model": {"atoms": []}})

        self.assertEqual(canvas.model, "new-model")
        self.assertTrue(history_state_for(canvas).enabled)
        self.assertEqual(history_state_for(canvas).history, [])
        self.assertEqual(history_state_for(canvas).redo_stack, [])
        self.assertEqual(canvas.selection_style_state.selected_items, [])
        self.assertIs(canvas.selection_info_state.callback, selection_callback)
        self.assertIsNone(canvas.selection_info_state.signature)
        self.assertIsNone(canvas.selection_info_state.pending_signature)
        self.assertEqual(canvas.selection_info_state.cache, ("", ""))
        self.assertFalse(canvas.selection_info_state.rdkit_warmup_pending)
        self.assertEqual(
            events,
            [
                "clear",
                "settings",
                "deserialize",
                "adjacency",
                "pre",
                "projection",
                "render",
                "post",
                "dirty",
            ],
        )
        canvas.services.structure_build_service.ensure_ring_fills_for_model.assert_not_called()

    def test_apply_state_reenables_history_when_restore_fails(self) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            clear_scene=mock.Mock(),
            model="old-model",
        )
        canvas.services = _document_services(
            clear_scene=lambda: canvas.clear_scene(),
            rebuild_bond_adjacency=mock.Mock(),
            render_model=mock.Mock(),
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"atoms": []}},
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value="new-model",
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                service.apply_state({"model": {"atoms": []}})

        self.assertTrue(history_state_for(canvas).enabled)

    def test_apply_state_failure_restores_previous_document_and_history_exactly(
        self,
    ) -> None:
        old_state = {
            "model": {"name": "old-model"},
            "settings": {"name": "old-settings"},
            "scene": ["old-model-item", "old-note"],
        }
        target_state = {
            "model": {"name": "target-model"},
            "settings": {"name": "target-settings"},
            "scene": ["target-model-item", "target-note"],
        }
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(enabled=False),
            model="old-model",
            settings="old-settings",
            scene_items=list(old_state["scene"]),
            sheet_size="Letter",
            sheet_orientation="landscape",
            selection_info_state=SimpleNamespace(
                callback=object(),
                signature=(frozenset({1}), frozenset({2})),
                pending_signature=(frozenset({1}), frozenset({2})),
                cache=("old", "selection"),
                rdkit_warmup_pending=True,
            ),
        )

        def clear_scene() -> None:
            canvas.model = "empty-model"
            canvas.scene_items.clear()

        def render_model() -> None:
            canvas.scene_items.append(f"{canvas.model}-item")

        canvas.services = _document_services(
            clear_scene=clear_scene,
            rebuild_bond_adjacency=mock.Mock(),
            render_model=render_model,
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        history_state = history_state_for(canvas)
        undo_command = object()
        redo_command = object()
        history_state.history.append(undo_command)
        history_state.redo_stack.append(redo_command)
        original_history = history_state.history
        original_redo = history_state.redo_stack
        original_selection_callback = canvas.selection_info_state.callback

        def restore_post_items(_canvas, state) -> None:
            if state is target_state:
                canvas.scene_items.append("partial-target-note")
                raise RuntimeError("target restore failed")
            canvas.scene_items.extend(state["scene"][1:])

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, state: (
                    setattr(canvas, "settings", state["settings"]["name"]),
                    setattr(canvas, "sheet_size", "A4"),
                    setattr(canvas, "sheet_orientation", "portrait"),
                ),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda model_state: model_state["name"],
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=restore_post_items,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state(target_state)

        self.assertEqual(canvas.model, "old-model")
        self.assertEqual(canvas.settings, "old-settings")
        self.assertEqual(canvas.scene_items, old_state["scene"])
        self.assertEqual(canvas.sheet_size, "Letter")
        self.assertEqual(canvas.sheet_orientation, "landscape")
        self.assertIs(canvas.selection_info_state.callback, original_selection_callback)
        self.assertEqual(
            canvas.selection_info_state.signature,
            (frozenset({1}), frozenset({2})),
        )
        self.assertEqual(canvas.selection_info_state.cache, ("old", "selection"))
        self.assertTrue(canvas.selection_info_state.rdkit_warmup_pending)
        self.assertIs(history_state.history, original_history)
        self.assertIs(history_state.redo_stack, original_redo)
        self.assertEqual(history_state.history, [undo_command])
        self.assertEqual(history_state.redo_stack, [redo_command])
        self.assertFalse(history_state.enabled)

    def test_apply_state_retries_fail_once_rollback_clear_restore_and_verification(
        self,
    ) -> None:
        import chemvas.ui.canvas_document_session_service as session_module

        old_state = {"model": "old-model", "scene": ["old-item"]}
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            model="old-model",
            settings="old-settings",
            scene_items=["old-item"],
        )
        clear_calls = 0

        def clear_scene() -> None:
            nonlocal clear_calls
            clear_calls += 1
            canvas.model = "empty-model"
            canvas.scene_items.clear()
            if clear_calls == 2:
                raise RuntimeError("rollback clear failed once")

        def render_model() -> None:
            canvas.scene_items.append("partial-target")
            raise RuntimeError("target render failed")

        canvas.services = _document_services(
            clear_scene=clear_scene,
            rebuild_bond_adjacency=mock.Mock(),
            render_model=render_model,
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        history_state = history_state_for(canvas)
        undo_command = object()
        redo_command = object()
        history_state.history.append(undo_command)
        history_state.redo_stack.append(redo_command)
        history_list = history_state.history
        redo_list = history_state.redo_stack
        snapshot_calls = 0

        def snapshot_state(_canvas) -> dict:
            nonlocal snapshot_calls
            snapshot_calls += 1
            if snapshot_calls == 2:
                raise RuntimeError("verification failed once")
            return old_state

        restore_calls = 0
        original_restore = session_module._CanvasRollbackSnapshot.restore_live_state

        def restore_live_state(snapshot, target_canvas) -> None:
            nonlocal restore_calls
            restore_calls += 1
            if restore_calls == 1:
                raise RuntimeError("scene reattach failed once")
            original_restore(snapshot, target_canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                side_effect=snapshot_state,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: setattr(
                    canvas, "settings", "target-settings"
                ),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value="target-model",
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
            mock.patch.object(
                session_module._CanvasRollbackSnapshot,
                "restore_live_state",
                new=restore_live_state,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "target render failed"):
                service.apply_state({"model": "target"})

        self.assertEqual(clear_calls, 3)
        self.assertEqual(restore_calls, 2)
        self.assertEqual(snapshot_calls, 3)
        self.assertEqual(canvas.model, "old-model")
        self.assertEqual(canvas.settings, "old-settings")
        self.assertEqual(canvas.scene_items, ["old-item"])
        self.assertIs(history_state.history, history_list)
        self.assertIs(history_state.redo_stack, redo_list)
        self.assertEqual(history_state.history, [undo_command])
        self.assertEqual(history_state.redo_stack, [redo_command])

    def test_apply_state_clears_history_only_when_previous_document_restore_also_fails(
        self,
    ) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(
                history=[object()], redo_stack=[object()], enabled=False
            ),
            model="old-model",
        )

        def clear_scene() -> None:
            canvas.model = "empty-model"

        canvas.services = _document_services(
            clear_scene=clear_scene,
            rebuild_bond_adjacency=mock.Mock(),
            render_model=mock.Mock(side_effect=RuntimeError("render failed")),
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"name": "old-model"}},
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda model_state: model_state["name"],
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service._CanvasRollbackSnapshot.restore_live_state",
                side_effect=RuntimeError("rollback failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                service.apply_state({"model": {"name": "target-model"}})

        self.assertEqual(canvas.model, "empty-model")
        self.assertEqual(history_state_for(canvas).history, [])
        self.assertEqual(history_state_for(canvas).redo_stack, [])
        self.assertFalse(history_state_for(canvas).enabled)

    def test_apply_state_rolls_back_failures_from_each_item_restore_phase(self) -> None:
        for failing_phase in ("pre", "post", "groups"):
            with self.subTest(failing_phase=failing_phase):
                canvas = SimpleNamespace(
                    history_state=CanvasHistoryState(),
                    model="old-model",
                    settings="old-settings",
                    scene_items=["old-item"],
                )

                def clear_scene(target_canvas=canvas) -> None:
                    target_canvas.model = "empty-model"
                    target_canvas.scene_items.clear()

                def phase(
                    name: str, *, target_canvas=canvas, target_failure=failing_phase
                ):
                    def restore(_canvas, _state) -> None:
                        target_canvas.scene_items.append(f"target-{name}")
                        if name == target_failure:
                            raise RuntimeError(f"{name} failed")

                    return restore

                canvas.services = _document_services(
                    clear_scene=clear_scene,
                    rebuild_bond_adjacency=mock.Mock(),
                    render_model=lambda target_canvas=canvas: (
                        target_canvas.scene_items.append("target-model-item")
                    ),
                    mark_spatial_index_dirty=mock.Mock(),
                )
                _attach_history_service(canvas)
                service = _session_service(canvas)
                command = object()
                history_state_for(canvas).history.append(command)
                old_state = {"model": "old", "scene": ["old-item"]}

                with (
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                        return_value=old_state,
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.apply_document_settings",
                        side_effect=lambda _canvas, _state, target_canvas=canvas: (
                            setattr(
                                target_canvas,
                                "settings",
                                "target-settings",
                            )
                        ),
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                        return_value="target-model",
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items",
                        side_effect=phase("pre"),
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                        side_effect=phase("post"),
                    ),
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.restore_document_groups",
                        side_effect=phase("groups"),
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, f"{failing_phase} failed"
                    ):
                        service.apply_state({"model": "target"})

                self.assertEqual(canvas.model, "old-model")
                self.assertEqual(canvas.settings, "old-settings")
                self.assertEqual(canvas.scene_items, ["old-item"])
                self.assertEqual(history_state_for(canvas).history, [command])
                self.assertEqual(history_state_for(canvas).redo_stack, [])
                self.assertTrue(history_state_for(canvas).enabled)

    def test_apply_state_detach_failure_restores_items_and_history_before_raising(
        self,
    ) -> None:
        class Item:
            def __init__(self) -> None:
                self.current_scene = None

            def parentItem(self):
                return None

            def scene(self):
                return self.current_scene

            def setSelected(self, _selected) -> None:
                return None

        class FailingScene:
            def __init__(self, items) -> None:
                self._items = list(items)
                self._blocked = False
                self.remove_calls = 0

            def items(self):
                return list(self._items)

            def removeItem(self, item) -> None:
                self.remove_calls += 1
                if self.remove_calls == 2:
                    raise RuntimeError("detach failed")
                self._items.remove(item)
                item.current_scene = None

            def addItem(self, item) -> None:
                if item not in self._items:
                    self._items.append(item)
                item.current_scene = self

            def blockSignals(self, blocked):
                previous = self._blocked
                self._blocked = blocked
                return previous

            def sceneRect(self):
                return "old-rect"

            def setSceneRect(self, _rect) -> None:
                return None

            def selectedItems(self):
                return []

            def focusItem(self):
                return None

            def setFocusItem(self, _item) -> None:
                return None

        first = Item()
        second = Item()
        scene = FailingScene([first, second])
        first.current_scene = scene
        second.current_scene = scene
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(history=[object()]),
            model="old-model",
            scene=lambda: scene,
        )
        clear_scene = mock.Mock()
        canvas.services = _document_services(
            clear_scene=clear_scene,
            rebuild_bond_adjacency=mock.Mock(),
            render_model=mock.Mock(),
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        original_command = history_state_for(canvas).history[0]

        with mock.patch(
            "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
            return_value={"model": "old"},
        ):
            with self.assertRaisesRegex(RuntimeError, "detach failed"):
                service.apply_state({"model": "target"})

        self.assertIs(first.scene(), scene)
        self.assertIs(second.scene(), scene)
        self.assertCountEqual(scene.items(), [first, second])
        self.assertEqual(history_state_for(canvas).history, [original_command])
        self.assertTrue(history_state_for(canvas).enabled)
        clear_scene.assert_not_called()

    def test_apply_state_rollback_preserves_live_parent_child_item_history_references(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        scene = QGraphicsScene()
        parent_item = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        parent_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        parent_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable, True)
        child_item = QGraphicsRectItem(1.0, 1.0, 5.0, 5.0, parent_item)
        child_item.setPos(8.0, 0.0)
        scene.addItem(parent_item)
        parent_item.setSelected(True)
        scene.setFocusItem(parent_item)
        scene_registry = [parent_item, child_item]
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            model="old-model",
            settings="old-settings",
            scene_items=scene_registry,
            selection_style_state=SelectionStyleState(selected_items=[parent_item]),
            scene=lambda: scene,
        )

        def clear_scene() -> None:
            scene.clear()
            canvas.model = "empty-model"
            canvas.scene_items.clear()

        def render_model() -> None:
            target_item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
            scene.addItem(target_item)
            canvas.scene_items.append(target_item)

        canvas.services = _document_services(
            clear_scene=clear_scene,
            rebuild_bond_adjacency=mock.Mock(),
            render_model=render_model,
            mark_spatial_index_dirty=mock.Mock(),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        command = UpdateSceneItemCommand(
            item=child_item,
            before_state={"x": 2.0},
            after_state={"x": 8.0},
        )
        history_state_for(canvas).history.append(command)
        old_state = {"model": {"name": "old-model"}, "scene": "old"}

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: setattr(
                    canvas, "settings", "target-settings"
                ),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value="target-model",
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("post-model failure"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
            mock.patch(
                "chemvas.ui.history_commands._apply_scene_item_state",
                side_effect=lambda _canvas, item, state: item.setPos(state["x"], 0.0),
            ),
            mock.patch(
                "chemvas.ui.history_commands.refresh_selection_outline_for_canvas"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "post-model failure"):
                service.apply_state({"model": {"name": "target-model"}})

            self.assertIs(child_item.parentItem(), parent_item)
            self.assertIs(parent_item.scene(), scene)
            self.assertIs(child_item.scene(), scene)
            self.assertIs(canvas.scene_items, scene_registry)
            self.assertEqual(canvas.scene_items, [parent_item, child_item])
            self.assertEqual(canvas.selection_style_state.selected_items, [parent_item])
            self.assertTrue(parent_item.isSelected())
            self.assertIs(scene.focusItem(), parent_item)
            canvas.services.history_service.undo()

        self.assertEqual(child_item.x(), 2.0)
        self.assertEqual(history_state_for(canvas).history, [])
        self.assertEqual(history_state_for(canvas).redo_stack, [command])

    def test_apply_state_rollback_restores_view_rect_and_rotation_preview(self) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        scene = QGraphicsScene()
        scene_rect = QRectF(-200.0, -100.0, 400.0, 200.0)
        view_rect = QRectF(-180.0, -80.0, 360.0, 160.0)
        target_view_rect = QRectF(-20.0, -30.0, 40.0, 60.0)
        set_explicit_scene_rect(scene, scene_rect)
        canvas = _qt_canvas_with_scene_reset(scene)
        set_explicit_view_scene_rect(canvas, view_rect)
        preview_item = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        scene.addItem(preview_item)
        preview_group = scene.createItemGroup([preview_item])
        preview_snapshot = RotationPreviewItemSnapshot(
            item=preview_item,
            state={"x": 0.0, "y": 0.0},
        )
        preview_state = rotation_preview_state_for(canvas)
        preview_state.group = preview_group
        preview_state.position_snapshots = [preview_snapshot]
        preview_state.center = QPointF(10.0, 10.0)
        original_snapshots = preview_state.position_snapshots
        service = _session_service(canvas)
        old_state = {"model": {"name": "old"}}

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda target, _state: set_explicit_view_scene_rect(
                    target,
                    target_view_rect,
                ),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("target restore failed"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state({"model": {"name": "target"}})

        self.assertEqual(canvas.sceneRect(), view_rect)
        self.assertEqual(scene.sceneRect(), scene_rect)
        self.assertIs(preview_state.group, preview_group)
        self.assertIs(preview_state.position_snapshots, original_snapshots)
        self.assertEqual(preview_state.position_snapshots, [preview_snapshot])
        self.assertEqual(preview_state.center, QPointF(10.0, 10.0))
        self.assertIs(preview_group.scene(), scene)
        self.assertIs(preview_item.scene(), scene)

    def test_apply_state_rollback_restores_clamped_viewport_pan_and_transform(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        app.setQuitOnLastWindowClosed(False)
        scene = QGraphicsScene()
        canvas = _qt_canvas_with_scene_reset(scene)
        canvas.resize(200, 200)
        canvas.show()

        original_rect = QRectF(-1000.0, -500.0, 2000.0, 1000.0)
        target_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
        set_explicit_scene_rect(scene, original_rect)
        set_explicit_view_scene_rect(canvas, original_rect)
        canvas.scale(1.25, 1.25)
        app.processEvents()
        horizontal = canvas.horizontalScrollBar()
        vertical = canvas.verticalScrollBar()
        horizontal.setValue(horizontal.maximum())
        vertical.setValue(vertical.maximum())
        app.processEvents()
        original_horizontal = horizontal.value()
        original_vertical = vertical.value()
        original_center = canvas.mapToScene(canvas.viewport().rect().center())
        original_transform = canvas.transform()
        service = _session_service(canvas)
        old_state = {"model": {"name": "old"}}

        def apply_target_view(target, _state) -> None:
            set_explicit_scene_rect(target.scene(), target_rect)
            set_explicit_view_scene_rect(target, target_rect)
            target.resetTransform()

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings",
                side_effect=apply_target_view,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("target restore failed"),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state({"model": {"name": "target"}})

        app.processEvents()
        self.assertEqual(canvas.sceneRect(), original_rect)
        self.assertEqual(scene.sceneRect(), original_rect)
        self.assertEqual(canvas.transform(), original_transform)
        self.assertEqual(horizontal.value(), original_horizontal)
        self.assertEqual(vertical.value(), original_vertical)
        self.assertEqual(
            canvas.mapToScene(canvas.viewport().rect().center()), original_center
        )
        canvas.close()

    def test_detached_scene_restore_uses_ports_bound_before_descriptor_exit(
        self,
    ) -> None:
        for failure_source in ("item_scene", "view_transform"):
            for error_type in (AttributeError, KeyboardInterrupt, SystemExit):
                with self.subTest(
                    failure_source=failure_source,
                    error_type=error_type.__name__,
                ):
                    injected = error_type(f"{failure_source} lookup terminated")

                    class FlakyItem(QGraphicsRectItem):
                        fail_once = False

                        def __init__(
                            self,
                            rect: QRectF,
                            source: str,
                            error: BaseException,
                        ) -> None:
                            super().__init__(rect)
                            self.failure_source = source
                            self.injected_error = error

                        @property
                        def scene(self):
                            if self.fail_once and self.failure_source == "item_scene":
                                self.fail_once = False
                                raise self.injected_error
                            return super().scene

                    class FlakyView(QGraphicsView):
                        fail_once = False

                        def __init__(
                            self,
                            scene: QGraphicsScene,
                            source: str,
                            error: BaseException,
                        ) -> None:
                            super().__init__(scene)
                            self.failure_source = source
                            self.injected_error = error

                        @property
                        def setTransform(self):
                            if (
                                self.fail_once
                                and self.failure_source == "view_transform"
                            ):
                                self.fail_once = False
                                raise self.injected_error
                            return super().setTransform

                    scene = QGraphicsScene()
                    canvas = FlakyView(scene, failure_source, injected)
                    self.addCleanup(canvas.close)
                    canvas.resize(200, 200)
                    canvas.show()
                    rect = QRectF(-1000.0, -500.0, 2000.0, 1000.0)
                    set_explicit_scene_rect(scene, rect)
                    set_explicit_view_scene_rect(canvas, rect)
                    canvas.scale(1.25, 1.25)
                    item = FlakyItem(
                        QRectF(0.0, 0.0, 20.0, 20.0),
                        failure_source,
                        injected,
                    )
                    item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                        True,
                    )
                    item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIsFocusable,
                        True,
                    )
                    scene.addItem(item)
                    item.setSelected(True)
                    scene.setFocusItem(item)
                    self.app.processEvents()
                    horizontal = canvas.horizontalScrollBar()
                    vertical = canvas.verticalScrollBar()
                    horizontal.setValue(horizontal.maximum())
                    vertical.setValue(vertical.maximum())
                    self.app.processEvents()
                    original_transform = canvas.transform()
                    original_horizontal = horizontal.value()
                    original_vertical = vertical.value()
                    # Showing successive offscreen views can transfer active
                    # focus during processEvents; make the saved focus explicit
                    # immediately before the transaction capture.
                    scene.setFocusItem(item)
                    self.assertIs(scene.focusItem(), item)
                    snapshot = _snapshot_canvas_scene(canvas)
                    self.assertIsNotNone(snapshot)
                    assert snapshot is not None

                    snapshot.detach()
                    QGraphicsView.resetTransform(canvas)
                    horizontal.setValue(horizontal.minimum())
                    vertical.setValue(vertical.minimum())
                    item.fail_once = True
                    canvas.fail_once = True

                    snapshot.restore()

                    self.assertIs(QGraphicsItem.scene(item), scene)
                    self.assertTrue(item.isSelected())
                    self.assertIs(scene.focusItem(), item)
                    self.assertEqual(canvas.transform(), original_transform)
                    self.assertEqual(horizontal.value(), original_horizontal)
                    self.assertEqual(vertical.value(), original_vertical)

    def test_detached_scene_restore_classifies_noop_transform_setter(self) -> None:
        for persistent in (False, True):
            with self.subTest(persistent=persistent):

                class NoOpView(QGraphicsView):
                    remaining_noops: int | None = 0

                    @property
                    def setTransform(self):
                        def apply_transform(transform) -> None:
                            if self.remaining_noops is None:
                                return
                            if self.remaining_noops > 0:
                                self.remaining_noops -= 1
                                return
                            QGraphicsView.setTransform(self, transform)

                        return apply_transform

                scene = QGraphicsScene()
                canvas = NoOpView(scene)
                self.addCleanup(canvas.close)
                rect = QRectF(-1000.0, -500.0, 2000.0, 1000.0)
                set_explicit_scene_rect(scene, rect)
                set_explicit_view_scene_rect(canvas, rect)
                canvas.scale(1.5, 1.5)
                item = QGraphicsRectItem(QRectF(0.0, 0.0, 20.0, 20.0))
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                    True,
                )
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsFocusable,
                    True,
                )
                scene.addItem(item)
                item.setSelected(True)
                scene.setFocusItem(item)
                original_transform = canvas.transform()
                snapshot = _snapshot_canvas_scene(canvas)
                self.assertIsNotNone(snapshot)
                assert snapshot is not None

                snapshot.detach()
                QGraphicsView.resetTransform(canvas)
                canvas.remaining_noops = None if persistent else 1

                with self.assertRaisesRegex(
                    RuntimeError,
                    "did not restore the view transform",
                ):
                    snapshot.restore()
                if persistent:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "did not restore the view transform",
                    ):
                        snapshot.restore()
                    self.assertNotEqual(canvas.transform(), original_transform)
                else:
                    snapshot.restore()
                    self.assertEqual(canvas.transform(), original_transform)
                    self.assertIs(item.scene(), scene)
                    self.assertTrue(item.isSelected())
                    self.assertIs(scene.focusItem(), item)

    def test_detached_auto_scene_restore_keeps_scene_and_view_inherited_growth(
        self,
    ) -> None:
        scene = QGraphicsScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = QGraphicsView(scene)
        snapshot = _snapshot_canvas_scene(canvas)
        self.assertIsNotNone(snapshot)

        snapshot.detach()
        snapshot.restore()

        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)
        self.assertGreater(canvas.sceneRect().right(), 10_000.0)
        scene.removeItem(far)
        canvas.close()

    def test_detached_auto_scene_restore_retries_partial_qt_rect_transition(
        self,
    ) -> None:
        class FailOnceRestoreScene(QGraphicsScene):
            fail_next_set = False

            def setSceneRect(self, rect) -> None:
                if self.fail_next_set:
                    self.fail_next_set = False
                    raise RuntimeError("inherited rect transition failed")
                QGraphicsScene.setSceneRect(self, rect)

        scene = FailOnceRestoreScene()
        original_item = scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = QGraphicsView(scene)
        snapshot = _snapshot_canvas_scene(canvas)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        rect_snapshot = snapshot.scene_rect_snapshot
        self.assertIsNotNone(rect_snapshot)
        assert rect_snapshot is not None
        snapshot.detach()
        scene.fail_next_set = True
        snapshot.restore()

        self.assertFalse(rect_snapshot.active)
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        self.assertIs(original_item.scene(), scene)
        far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)
        self.assertGreater(canvas.sceneRect().right(), 10_000.0)
        scene.removeItem(far)
        canvas.close()

    def test_actual_canvas_sequential_document_and_note_failures_keep_rect_baseline(
        self,
    ) -> None:
        canvas = CanvasView()
        scene = canvas.scene()
        service = canvas.services.canvas_document_session_service
        original_scene_rect = QRectF(scene.sceneRect())
        original_view_rect = QRectF(canvas.sceneRect())
        target_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
        old_state = {"model": {"name": "old"}}

        def replace_then_fail(_state) -> None:
            set_explicit_scene_rect(scene, target_rect)
            set_explicit_view_scene_rect(canvas, target_rect)
            scene.blockSignals(True)
            raise RuntimeError("target post-model failure")

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch.object(
                service,
                "_apply_state_contents",
                side_effect=replace_then_fail,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "target post-model failure"):
                service.apply_state({"model": {"name": "target"}})

        self.assertEqual(scene.sceneRect(), original_scene_rect)
        self.assertEqual(canvas.sceneRect(), original_view_rect)
        self.assertFalse(scene.signalsBlocked())
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))

        note_controller = canvas.services.note_controller
        with mock.patch.object(
            note_controller,
            "apply_note_style",
            side_effect=RuntimeError("note style failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "note style failure"):
                note_controller.create_text_note(QPointF(10_000.0, 0.0), "far")

        self.assertEqual(scene.sceneRect(), original_scene_rect)
        self.assertEqual(canvas.sceneRect(), original_view_rect)
        self.assertEqual(
            scene._chemvas_scene_rect_tracker.known_rect,
            original_scene_rect,
        )
        canvas.close()

    def test_history_disable_interruption_closes_document_scene_guard(self) -> None:
        scene = QGraphicsScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = _qt_canvas_with_scene_reset(scene)
        service = _session_service(canvas)
        old_state = {"model": {"name": "old"}}
        original_set_enabled = service.history.set_enabled
        calls = 0

        def disable_then_exit(enabled: bool) -> None:
            nonlocal calls
            calls += 1
            original_set_enabled(enabled)
            if calls == 1:
                raise SystemExit("history disable terminated")

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch.object(
                service.history,
                "set_enabled",
                side_effect=disable_then_exit,
            ),
            mock.patch.object(
                service,
                "_apply_state_contents",
                side_effect=RuntimeError(
                    "target failed after repaired history disable"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "target failed after repaired history disable",
            ):
                service.apply_state({"model": {"name": "target"}})

        self.assertTrue(history_state_for(canvas).enabled)
        self.assertGreaterEqual(calls, 3)
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)
        self.assertGreater(canvas.sceneRect().right(), 10_000.0)
        scene.removeItem(far)
        canvas.close()

    def test_live_property_attribute_error_aborts_before_document_scene_guard(
        self,
    ) -> None:
        class BrokenRenderer:
            @property
            def style(self):
                raise AttributeError("renderer style capture failed")

        scene = QGraphicsScene()
        original = scene.addRect(0.0, 0.0, 10.0, 10.0)
        canvas = _qt_canvas_with_scene_reset(scene)
        canvas.renderer = BrokenRenderer()
        service = _session_service(canvas)

        with self.assertRaisesRegex(AttributeError, "renderer style capture failed"):
            service.apply_state({"model": {"name": "target"}})

        self.assertIs(original.scene(), scene)
        self.assertTrue(history_state_for(canvas).enabled)
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)
        scene.removeItem(far)
        canvas.close()

    def test_history_enabled_transitions_are_verified_and_retried(self) -> None:
        for behavior in (
            "fail_after_once",
            "no_op_once",
            "persistent_no_op",
        ):
            with self.subTest(behavior=behavior):
                canvas = CanvasView()
                service = canvas.services.canvas_document_session_service
                history_state = service.history.state
                original_set_enabled = service.history.set_enabled
                restore_attempts = 0
                primary = KeyboardInterrupt(
                    f"target failed before {behavior} history restore"
                )

                def set_enabled(
                    enabled: bool,
                    _behavior=behavior,
                    _setter=original_set_enabled,
                ) -> None:
                    nonlocal restore_attempts
                    if enabled:
                        restore_attempts += 1
                        if _behavior == "persistent_no_op":
                            return
                        if _behavior == "no_op_once" and restore_attempts == 1:
                            return
                    _setter(enabled)
                    if (
                        enabled
                        and _behavior == "fail_after_once"
                        and restore_attempts == 1
                    ):
                        raise SystemExit("history enable restore failed after mutation")

                with (
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                        return_value={"model": {"name": "old"}},
                    ),
                    mock.patch.object(
                        service,
                        "_apply_state_contents",
                        side_effect=primary,
                    ),
                    mock.patch.object(
                        service.history,
                        "set_enabled",
                        side_effect=set_enabled,
                    ),
                ):
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        service.apply_state({"model": {"name": "target"}})

                self.assertIs(caught.exception, primary)
                self.assertGreaterEqual(restore_attempts, 2)
                if behavior == "persistent_no_op":
                    self.assertFalse(history_state.enabled)
                    self.assertTrue(
                        any(
                            "history enabled setter did not apply" in note
                            for note in getattr(primary, "__notes__", [])
                        )
                    )
                    original_set_enabled(True)
                else:
                    self.assertTrue(history_state.enabled)
                canvas.close()

    def test_persistent_noop_history_disable_aborts_before_document_mutation(
        self,
    ) -> None:
        canvas = CanvasView()
        service = canvas.services.canvas_document_session_service
        original_model = canvas.model
        original_items = tuple(canvas.scene().items())
        apply_contents = mock.Mock()
        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"name": "old"}},
            ),
            mock.patch.object(
                service,
                "_apply_state_contents",
                apply_contents,
            ),
            mock.patch.object(
                service.history,
                "set_enabled",
                side_effect=lambda _enabled: None,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "history enabled setter did not apply",
            ):
                service.apply_state({"model": {"name": "target"}})

        apply_contents.assert_not_called()
        self.assertTrue(service.history.state.enabled)
        self.assertIs(canvas.model, original_model)
        self.assertEqual(tuple(canvas.scene().items()), original_items)
        canvas.close()

    def test_scene_property_attribute_error_aborts_document_scene_snapshot(
        self,
    ) -> None:
        from chemvas.ui.canvas_document_session_service import _snapshot_canvas_scene

        scene = QGraphicsScene()
        original = scene.addRect(0.0, 0.0, 10.0, 10.0)

        class FlakyCanvas:
            calls = 0

            @property
            def scene(self):
                self.calls += 1
                if self.calls == 1:
                    raise AttributeError("document scene property failed internally")
                return lambda: scene

        canvas = FlakyCanvas()
        with self.assertRaisesRegex(
            AttributeError,
            "document scene property failed internally",
        ):
            _snapshot_canvas_scene(canvas)

        self.assertIs(original.scene(), scene)
        # Capture failure restores the lightweight canvas's raw pre-getter
        # namespace, including removal of the one-shot instance counter.
        self.assertEqual(canvas.calls, 0)
        canvas.calls = 1
        self.assertIs(canvas.scene(), scene)
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)

    def test_non_qt_items_capture_failure_restores_pre_items_raw_graph(
        self,
    ) -> None:
        primary = SystemExit("later non-Qt scene port capture terminated")

        class Item:
            def __init__(self) -> None:
                self.value = "clean"

        item = Item()

        class Scene:
            def __init__(self) -> None:
                self.scene_items = [item]
                self.state = ["clean"]

            def items(self):
                self.state[:] = ["poisoned"]
                item.value = "poisoned"
                canvas.backing[:] = ["poisoned"]
                return list(self.scene_items)

            @property
            def removeItem(self):
                raise primary

        scene = Scene()
        scene_items = scene.scene_items
        scene_state = scene.state
        canvas = SimpleNamespace(
            scene=lambda: scene,
            backing=["clean"],
        )
        canvas_backing = canvas.backing

        with self.assertRaises(SystemExit) as caught:
            _snapshot_canvas_scene(canvas)

        self.assertIs(caught.exception, primary)
        self.assertIs(scene.scene_items, scene_items)
        self.assertEqual(scene.scene_items, [item])
        self.assertIs(scene.state, scene_state)
        self.assertEqual(scene.state, ["clean"])
        self.assertEqual(item.value, "clean")
        self.assertIs(canvas.backing, canvas_backing)
        self.assertEqual(canvas.backing, ["clean"])

    def test_failed_document_scene_guard_capture_unwinds_qt_state(self) -> None:
        primary = SystemExit("guard capture failed after rect mutation")

        class FailingGuardScene(QGraphicsScene):
            def __init__(self) -> None:
                super().__init__()
                self.setter_calls = 0

            def setSceneRect(self, *args) -> None:
                self.setter_calls += 1
                QGraphicsScene.setSceneRect(self, *args)
                if self.setter_calls == 1:
                    raise primary
                if self.setter_calls <= 3:
                    raise RuntimeError("guard cleanup setter failed")

        scene = FailingGuardScene()
        scene.addRect(0.0, 0.0, 10.0, 10.0)
        original_rect = QRectF(scene.sceneRect())
        view = QGraphicsView(scene)
        self.addCleanup(view.close)

        with self.assertRaises(SystemExit) as caught:
            _snapshot_canvas_scene(view)

        self.assertIs(caught.exception, primary)
        self.assertEqual(scene.sceneRect(), original_rect)
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_automatic"))
        scene.addRect(10_000.0, 0.0, 10.0, 10.0)
        self.assertGreater(scene.sceneRect().right(), 10_000.0)

    def test_selection_slot_getter_failure_closes_document_scene_guard(self) -> None:
        for error_type in (AttributeError, SystemExit):
            with self.subTest(error_type=error_type.__name__):
                scene = QGraphicsScene()
                scene.addRect(0.0, 0.0, 10.0, 10.0)
                original_rect = QRectF(scene.sceneRect())
                primary = error_type("selection slot getter failed after rect mutation")

                class FailingSlotView(QGraphicsView):
                    slot_reads = 0
                    failed_scene = scene
                    failure = primary

                    @property
                    def handle_scene_selection_group_changed(self):
                        self.slot_reads += 1
                        QGraphicsScene.setSceneRect(
                            self.failed_scene,
                            QRectF(5_000.0, 6_000.0, 70.0, 80.0),
                        )
                        raise self.failure

                view = FailingSlotView(scene)
                self.addCleanup(view.close)

                with self.assertRaises(error_type) as caught:
                    _snapshot_canvas_scene(view)

                if error_type is SystemExit:
                    self.assertIs(caught.exception, primary)
                self.assertEqual(view.slot_reads, 1)
                self.assertEqual(scene.sceneRect(), original_rect)
                self.assertTrue(scene_rect_is_automatic(scene))
                tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
                self.assertTrue(tracker is None or tracker.depth == 0)
                far = scene.addRect(10_000.0, 0.0, 10.0, 10.0)
                self.assertGreater(scene.sceneRect().right(), 10_000.0)
                scene.removeItem(far)

    def test_document_scene_capture_propagates_present_descriptor_errors(self) -> None:
        sources = (
            "scene.items",
            "scene.removeItem",
            "scene.addItem",
            "scene.sceneRect",
            "scene.setSceneRect",
            "scene.selectedItems",
            "scene.focusItem",
            "scene.setFocusItem",
            "scene.blockSignals",
            "scene.signalsBlocked",
            "canvas.sceneRect",
            "canvas.setSceneRect",
            "canvas.transform",
            "canvas.setTransform",
            "canvas.horizontalScrollBar",
            "canvas.verticalScrollBar",
            "horizontal.value",
            "horizontal.setValue",
            "vertical.value",
            "vertical.setValue",
        )

        for source in sources:
            with self.subTest(source=source):

                class ScrollBar:
                    def __init__(
                        self,
                        scope: str,
                        broken_source: str,
                    ) -> None:
                        self.scope = scope
                        self.broken_source = broken_source

                    def __getattribute__(self, name: str):
                        scope = object.__getattribute__(self, "scope")
                        broken_source = object.__getattribute__(
                            self,
                            "broken_source",
                        )
                        if broken_source == f"{scope}.{name}":
                            raise AttributeError(f"{broken_source} failed internally")
                        return object.__getattribute__(self, name)

                    def value(self) -> int:
                        return 0

                    def setValue(self, _value: int) -> None:
                        return None

                class Scene:
                    def __init__(self, broken_source: str) -> None:
                        self.broken_source = broken_source
                        self.rect = QRectF(0.0, 0.0, 10.0, 10.0)

                    def __getattribute__(self, name: str):
                        broken_source = object.__getattribute__(
                            self,
                            "broken_source",
                        )
                        if broken_source == f"scene.{name}":
                            raise AttributeError(f"{broken_source} failed internally")
                        return object.__getattribute__(self, name)

                    def items(self) -> list:
                        return []

                    def removeItem(self, _item) -> None:
                        return None

                    def addItem(self, _item) -> None:
                        return None

                    def sceneRect(self) -> QRectF:
                        return QRectF(self.rect)

                    def setSceneRect(self, rect: QRectF) -> None:
                        self.rect = QRectF(rect)

                    def selectedItems(self) -> list:
                        return []

                    def focusItem(self):
                        return None

                    def setFocusItem(self, _item) -> None:
                        return None

                    def blockSignals(self, _blocked: bool) -> bool:
                        return False

                    def signalsBlocked(self) -> bool:
                        return False

                scene = Scene(source)

                class Canvas:
                    def __init__(self, scene_object, broken_source: str) -> None:
                        self.scene_object = scene_object
                        self.broken_source = broken_source
                        self.horizontal = ScrollBar("horizontal", broken_source)
                        self.vertical = ScrollBar("vertical", broken_source)

                    def __getattribute__(self, name: str):
                        broken_source = object.__getattribute__(
                            self,
                            "broken_source",
                        )
                        if broken_source == f"canvas.{name}":
                            raise AttributeError(f"{broken_source} failed internally")
                        return object.__getattribute__(self, name)

                    def scene(self):
                        return self.scene_object

                    def sceneRect(self) -> QRectF:
                        return QRectF(0.0, 0.0, 10.0, 10.0)

                    def setSceneRect(self, _rect: QRectF) -> None:
                        return None

                    def transform(self):
                        return object()

                    def setTransform(self, _transform) -> None:
                        return None

                    def horizontalScrollBar(self):
                        return self.horizontal

                    def verticalScrollBar(self):
                        return self.vertical

                with self.assertRaisesRegex(
                    AttributeError,
                    f"{source} failed internally",
                ):
                    _snapshot_canvas_scene(Canvas(scene, source))

                self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))

    def test_document_scene_snapshot_fails_closed_for_live_incomplete_ports(
        self,
    ) -> None:
        class SparseEmptyScene:
            def items(self) -> list:
                return []

        sparse = SimpleNamespace(scene=lambda: SparseEmptyScene())
        self.assertIsNone(_snapshot_canvas_scene(sparse))

        class Item:
            def __init__(self) -> None:
                self.current_scene = None

            def parentItem(self):
                return None

            def scene(self):
                return self.current_scene

        item = Item()

        class IncompleteLiveScene:
            def items(self) -> list:
                return [item]

        live_scene = IncompleteLiveScene()
        item.current_scene = live_scene
        with self.assertRaisesRegex(
            RuntimeError,
            "incomplete transaction ports",
        ):
            _snapshot_canvas_scene(SimpleNamespace(scene=lambda: live_scene))
        self.assertIs(item.current_scene, live_scene)

        for failure_mode in ("missing", "descriptor"):
            with self.subTest(actual_qt=failure_mode):
                injected = SystemExit("removeItem descriptor terminated")

                class IncompleteQtScene(QGraphicsScene):
                    def __init__(
                        self,
                        mode: str,
                        error: BaseException,
                    ) -> None:
                        super().__init__()
                        self.failure_mode = mode
                        self.injected_error = error
                        self.remove_item_lookups = 0
                        self.victim = None

                    @property
                    def removeItem(self):
                        self.remove_item_lookups += 1
                        if self.victim is not None:
                            QGraphicsScene.removeItem(self, self.victim)
                        if self.failure_mode == "descriptor":
                            raise self.injected_error
                        return None

                scene = IncompleteQtScene(failure_mode, injected)
                qt_item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
                QGraphicsScene.addItem(scene, qt_item)
                scene.victim = qt_item
                canvas = QGraphicsView(scene)
                self.addCleanup(canvas.close)
                snapshot = _snapshot_canvas_scene(canvas)
                self.assertIsNotNone(snapshot)
                assert snapshot is not None
                self.assertEqual(scene.remove_item_lookups, 0)
                self.assertIs(qt_item.scene(), scene)
                snapshot.detach()
                snapshot.restore()
                self.assertIs(qt_item.scene(), scene)
                self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))

    def test_non_qt_scene_port_capture_failure_restores_raw_scene_graph(self) -> None:
        primary = SystemExit("late non-Qt scene port capture terminated")

        class Item:
            def __init__(self) -> None:
                self.current_scene = None
                self.selected = False
                self.parent = None
                self.z = 0.0

            def parentItem(self):
                return self.parent

            def setParentItem(self, parent) -> None:
                self.parent = parent

            def zValue(self) -> float:
                return self.z

            def setZValue(self, value: float) -> None:
                self.z = value

            def scene(self):
                return self.current_scene

            def isSelected(self) -> bool:
                return self.selected

            def setSelected(self, selected: bool) -> None:
                self.selected = selected

        parent = Item()
        child = Item()
        child.parent = parent
        child.z = 7.0
        child.selected = True

        class Scene:
            def __init__(self) -> None:
                self.scene_items = [child, parent]
                self.selected_items = [child]
                self.focus_item = child
                self.rect = QRectF(0.0, 0.0, 10.0, 10.0)

            def items(self):
                return list(self.scene_items)

            @property
            def removeItem(self):
                self.scene_items.clear()
                self.selected_items.clear()
                self.focus_item = None
                child.current_scene = None
                child.selected = False
                child.parent = None
                child.z = -9.0
                return lambda _item: None

            @property
            def addItem(self):
                raise primary

        scene = Scene()
        parent.current_scene = scene
        child.current_scene = scene
        scene_items = scene.scene_items
        selected_items = scene.selected_items

        with self.assertRaises(SystemExit) as caught:
            _snapshot_canvas_scene(SimpleNamespace(scene=lambda: scene))

        self.assertIs(caught.exception, primary)
        self.assertIs(scene.scene_items, scene_items)
        self.assertEqual(scene.scene_items, [child, parent])
        self.assertIs(scene.selected_items, selected_items)
        self.assertEqual(scene.selected_items, [child])
        self.assertIs(scene.focus_item, child)
        self.assertIs(parent.current_scene, scene)
        self.assertIs(child.current_scene, scene)
        self.assertTrue(child.selected)
        self.assertIs(child.parent, parent)
        self.assertEqual(child.z, 7.0)

    def test_detached_scene_uses_each_captured_port_exactly_once(self) -> None:
        class Item:
            def __init__(self) -> None:
                self.current_scene = None
                self.scene_lookup_count = 0

            def parentItem(self):
                return None

            @property
            def scene(self):
                self.scene_lookup_count += 1
                if self.scene_lookup_count > 1:
                    raise SystemExit("item.scene was looked up twice")
                return lambda: self.current_scene

        item = Item()

        class SingleReadScene:
            def __init__(self) -> None:
                self.current_items = [item]
                self.blocked = False
                self.rect = "sentinel-rect"
                self.focus = None
                self.lookup_counts: dict[str, int] = {}

            def _port(self, name: str, operation):
                self.lookup_counts[name] = self.lookup_counts.get(name, 0) + 1
                if self.lookup_counts[name] > 1:
                    raise SystemExit(f"{name} was looked up twice")
                return operation

            def _items(self):
                return list(self.current_items)

            def _remove_item(self, target) -> None:
                self.current_items.remove(target)
                target.current_scene = None

            def _add_item(self, target) -> None:
                if target not in self.current_items:
                    self.current_items.append(target)
                target.current_scene = self

            def _scene_rect(self):
                return self.rect

            def _set_scene_rect(self, rect) -> None:
                self.rect = rect

            def _selected_items(self) -> list:
                return []

            def _focus_item(self):
                return self.focus

            def _set_focus_item(self, target) -> None:
                self.focus = target

            def _block_signals(self, blocked: bool) -> bool:
                previous = self.blocked
                self.blocked = blocked
                return previous

            @property
            def items(self):
                return self._port("items", self._items)

            @property
            def removeItem(self):
                return self._port("removeItem", self._remove_item)

            @property
            def addItem(self):
                return self._port("addItem", self._add_item)

            @property
            def sceneRect(self):
                return self._port("sceneRect", self._scene_rect)

            @property
            def setSceneRect(self):
                return self._port("setSceneRect", self._set_scene_rect)

            @property
            def selectedItems(self):
                return self._port("selectedItems", self._selected_items)

            @property
            def focusItem(self):
                return self._port("focusItem", self._focus_item)

            @property
            def setFocusItem(self):
                return self._port("setFocusItem", self._set_focus_item)

            @property
            def blockSignals(self):
                return self._port("blockSignals", self._block_signals)

            @property
            def signalsBlocked(self):
                return self._port(
                    "signalsBlocked",
                    lambda: self.blocked,
                )

        scene = SingleReadScene()
        item.current_scene = scene
        snapshot = _snapshot_canvas_scene(SimpleNamespace(scene=lambda: scene))
        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        snapshot.detach()
        self.assertIsNone(item.current_scene)
        snapshot.restore()

        self.assertIs(item.current_scene, scene)
        self.assertEqual(item.scene_lookup_count, 1)
        self.assertTrue(scene.lookup_counts)
        self.assertTrue(all(count == 1 for count in scene.lookup_counts.values()))

    def test_detach_membership_verification_rolls_back_noop_and_reentrant_qt_removal(
        self,
    ) -> None:
        class NoOpScene(QGraphicsScene):
            def removeItem(self, _item) -> None:
                return None

        no_op_scene = NoOpScene()
        no_op_item = no_op_scene.addRect(0.0, 0.0, 10.0, 10.0)
        no_op_view = QGraphicsView(no_op_scene)
        self.addCleanup(no_op_view.close)
        no_op_snapshot = _snapshot_canvas_scene(no_op_view)
        self.assertIsNotNone(no_op_snapshot)
        assert no_op_snapshot is not None

        with self.assertRaisesRegex(
            RuntimeError,
            "detach did not remove",
        ):
            no_op_snapshot.detach()
        self.assertIs(no_op_item.scene(), no_op_scene)

        primary = KeyboardInterrupt("reentrant Qt removal interrupted")

        class ReentrantScene(QGraphicsScene):
            fail_once = True

            def removeItem(self, item) -> None:
                if self.fail_once:
                    self.fail_once = False
                    for candidate in list(QGraphicsScene.items(self)):
                        if candidate.parentItem() is None:
                            QGraphicsScene.removeItem(self, candidate)
                    raise primary
                QGraphicsScene.removeItem(self, item)

        scene = ReentrantScene()
        first = scene.addRect(0.0, 0.0, 10.0, 10.0)
        second = scene.addRect(20.0, 0.0, 10.0, 10.0)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        snapshot = _snapshot_canvas_scene(view)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        with self.assertRaises(KeyboardInterrupt) as caught:
            snapshot.detach()
        self.assertIs(caught.exception, primary)
        self.assertIs(first.scene(), scene)
        self.assertIs(second.scene(), scene)

        snapshot.detach()
        self.assertIsNone(first.scene())
        self.assertIsNone(second.scene())
        snapshot.restore()
        self.assertIs(first.scene(), scene)
        self.assertIs(second.scene(), scene)

    def test_detached_scene_restores_exact_parent_child_order_and_rejects_ghosts(
        self,
    ) -> None:
        scene = QGraphicsScene()
        lower_root = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        parent = QGraphicsRectItem(20.0, 0.0, 10.0, 10.0)
        child = QGraphicsRectItem(1.0, 1.0, 3.0, 3.0, parent)
        scene.addItem(lower_root)
        scene.addItem(parent)
        set_explicit_scene_rect(
            scene,
            QRectF(-500.0, -500.0, 1000.0, 1000.0),
        )
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        expected_items = tuple(scene.items())
        snapshot = _snapshot_canvas_scene(view)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(len(snapshot.all_scene_items), len(expected_items))
        self.assertTrue(
            all(
                captured is expected
                for captured, expected in zip(
                    snapshot.all_scene_items,
                    expected_items,
                    strict=True,
                )
            )
        )

        snapshot.detach()
        snapshot.restore()

        restored_items = tuple(scene.items())
        self.assertTrue(
            all(
                restored is expected
                for restored, expected in zip(
                    restored_items,
                    expected_items,
                    strict=True,
                )
            )
        )
        self.assertIs(child.parentItem(), parent)
        self.assertIs(child.scene(), scene)

        second_snapshot = _snapshot_canvas_scene(view)
        assert second_snapshot is not None
        second_snapshot.detach()
        ghost_root = QGraphicsRectItem(100.0, 0.0, 10.0, 10.0)
        ghost_child = QGraphicsRectItem(1.0, 1.0, 2.0, 2.0, ghost_root)
        scene.addItem(ghost_root)

        second_snapshot.restore()

        self.assertIs(ghost_child.parentItem(), ghost_root)
        self.assertIsNone(ghost_child.scene())
        self.assertIsNone(ghost_root.scene())
        self.assertIs(parent.scene(), scene)
        self.assertIs(child.scene(), scene)
        self.assertTrue(
            all(
                current is expected
                for current, expected in zip(
                    tuple(scene.items()),
                    expected_items,
                    strict=True,
                )
            )
        )

        class ToggleRemovalScene(QGraphicsScene):
            removal_is_no_op = False

            def removeItem(self, item) -> None:
                if self.removal_is_no_op:
                    return
                QGraphicsScene.removeItem(self, item)

        retry_scene = ToggleRemovalScene()
        retry_old = retry_scene.addRect(0.0, 0.0, 10.0, 10.0)
        retry_view = QGraphicsView(retry_scene)
        self.addCleanup(retry_view.close)
        retry_snapshot = _snapshot_canvas_scene(retry_view)
        assert retry_snapshot is not None
        retry_snapshot.detach()
        retry_ghost = retry_scene.addRect(100.0, 0.0, 10.0, 10.0)
        retry_scene.removal_is_no_op = True

        with self.assertRaisesRegex(
            RuntimeError,
            "could not remove replacement scene items",
        ):
            retry_snapshot.restore()

        retry_scene.removal_is_no_op = False
        retry_snapshot.restore()
        self.assertIsNone(retry_ghost.scene())
        self.assertIs(retry_old.scene(), retry_scene)

    def test_document_apply_rejects_and_restores_reentrant_scene_root_swap(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        service = canvas.services.canvas_document_session_service
        original_scene = canvas.scene()
        replacement_scene = QGraphicsScene(canvas)
        target = service.snapshot_state()
        selection_signal = QGraphicsScene.selectionChanged.__get__(
            original_scene,
            type(original_scene),
        )
        receivers_before = original_scene.receivers(selection_signal)

        class SceneSwappingItem(QGraphicsRectItem):
            armed = False

            def itemChange(self, change, value):
                if (
                    self.armed
                    and change == self.GraphicsItemChange.ItemSceneChange
                    and value is None
                ):
                    self.armed = False
                    canvas.setScene(replacement_scene)
                return QGraphicsRectItem.itemChange(self, change, value)

        item = SceneSwappingItem(0.0, 0.0, 10.0, 10.0)
        original_scene.addItem(item)
        item.armed = True

        with self.assertRaisesRegex(RuntimeError, "scene root"):
            service.apply_state(target)

        self.assertIs(canvas.scene(), original_scene)
        self.assertIs(item.scene(), original_scene)
        self.assertEqual(
            original_scene.receivers(selection_signal),
            receivers_before,
        )

    def test_document_apply_rejects_reentrant_history_owner_swap(self) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        service = canvas.services.canvas_document_session_service
        original_history = service.history
        original_command = object()
        original_history.state.history[:] = [original_command]
        replacement = CanvasHistoryService(canvas, CanvasHistoryState())
        replacement_command = object()
        replacement.state.history[:] = [replacement_command]
        target = service.snapshot_state()

        class HistorySwappingItem(QGraphicsRectItem):
            armed = False

            def itemChange(self, change, value):
                if (
                    self.armed
                    and change == self.GraphicsItemChange.ItemSceneChange
                    and value is None
                ):
                    self.armed = False
                    service.history = replacement
                return QGraphicsRectItem.itemChange(self, change, value)

        item = HistorySwappingItem(0.0, 0.0, 10.0, 10.0)
        canvas.scene().addItem(item)
        item.armed = True

        with self.assertRaisesRegex(RuntimeError, "history service identity"):
            service.apply_state(target)

        self.assertIs(service.history, original_history)
        self.assertIs(canvas.services.history_service, original_history)
        self.assertEqual(original_history.state.history, [original_command])
        self.assertEqual(replacement.state.history, [replacement_command])
        self.assertIs(item.scene(), canvas.scene())

    def test_document_apply_restores_canonical_history_alias_swaps(self) -> None:
        for alias_name in ("runtime_state", "services"):
            with self.subTest(alias_name=alias_name):
                canvas = CanvasView()
                self.addCleanup(canvas.close)
                service = canvas.services.canvas_document_session_service
                original_history = service.history
                original_command = object()
                original_history.state.history[:] = [original_command]
                replacement = CanvasHistoryService(canvas, CanvasHistoryState())
                replacement_command = object()
                replacement.state.history[:] = [replacement_command]
                target = service.snapshot_state()
                alias_owner = getattr(canvas, alias_name)

                class AliasSwappingItem(QGraphicsRectItem):
                    armed = False

                    def itemChange(
                        self,
                        change,
                        value,
                        _alias_owner=alias_owner,
                        _replacement=replacement,
                    ):
                        if (
                            self.armed
                            and change == self.GraphicsItemChange.ItemSceneChange
                            and value is None
                        ):
                            self.armed = False
                            _alias_owner.history_service = _replacement
                        return QGraphicsRectItem.itemChange(self, change, value)

                item = AliasSwappingItem(0.0, 0.0, 10.0, 10.0)
                canvas.scene().addItem(item)
                item.armed = True

                with self.assertRaisesRegex(
                    RuntimeError,
                    rf"{alias_name} history service identity",
                ):
                    service.apply_state(target)

                self.assertIs(service.history, original_history)
                self.assertIs(
                    canvas.runtime_state.history_service,
                    original_history,
                )
                self.assertIs(canvas.services.history_service, original_history)
                self.assertEqual(
                    original_history.state.history,
                    [original_command],
                )
                self.assertEqual(
                    replacement.state.history,
                    [replacement_command],
                )
                self.assertIs(item.scene(), canvas.scene())

    def test_detached_scene_restores_stacking_flags_after_callback(self) -> None:
        scene = QGraphicsScene()
        parent = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        child = QGraphicsRectItem(1.0, 1.0, 5.0, 5.0, parent)

        class CorruptingRoot(QGraphicsRectItem):
            armed = False

            def itemChange(self, change, value):
                if (
                    self.armed
                    and change == self.GraphicsItemChange.ItemSceneChange
                    and value is None
                ):
                    self.armed = False
                    child.setFlag(
                        child.GraphicsItemFlag.ItemStacksBehindParent,
                        True,
                    )
                return QGraphicsRectItem.itemChange(self, change, value)

        corrupting = CorruptingRoot(30.0, 0.0, 10.0, 10.0)
        scene.addItem(parent)
        scene.addItem(corrupting)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        expected_flags = child.flags()
        expected_order = tuple(scene.items())
        snapshot = _snapshot_canvas_scene(view)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        corrupting.armed = True

        snapshot.detach()
        snapshot.restore()

        self.assertEqual(child.flags(), expected_flags)
        self.assertEqual(tuple(scene.items()), expected_order)

    def test_document_qt_parent_getter_override_is_not_capture_authority(
        self,
    ) -> None:
        scene = QGraphicsScene()
        peer = scene.addRect(0.0, 0.0, 10.0, 10.0)
        peer.setPos(QPointF(1.0, 2.0))

        class SideEffectParentItem(QGraphicsRectItem):
            reads = 0

            def parentItem(self):
                self.reads += 1
                peer.setPos(QPointF(51.0, -3.0))
                raise SystemExit("custom parent getter ran")

        item = SideEffectParentItem(20.0, 0.0, 10.0, 10.0)
        scene.addItem(item)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)

        snapshot = _snapshot_canvas_scene(view)

        self.assertIsNotNone(snapshot)
        self.assertEqual(item.reads, 0)
        self.assertEqual(peer.pos(), QPointF(1.0, 2.0))

    def test_failed_document_snapshot_unwinds_already_captured_model_state(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        service = canvas.services.canvas_document_session_service
        atom_id = canvas.model.add_atom("C", 1.0, 2.0)
        original_atoms = canvas.model.atoms
        primary = SystemExit("document serialization failed after mutation")

        def mutate_then_fail():
            canvas.model.atoms = {}
            raise primary

        with (
            mock.patch.object(service, "snapshot_state", side_effect=mutate_then_fail),
            self.assertRaises(SystemExit) as caught,
        ):
            service._snapshot_live_canvas_state()

        self.assertIs(caught.exception, primary)
        self.assertIs(canvas.model.atoms, original_atoms)
        self.assertIn(atom_id, original_atoms)

    def test_object_snapshot_unwinds_mutation_from_later_field_getter(self) -> None:
        from chemvas.ui.canvas_document_session_service import _snapshot_object_state

        primary = SystemExit("later document field capture terminated")

        class Target:
            def __init__(self) -> None:
                self.first = ["captured"]

            @property
            def second(self):
                self.first[:] = ["poisoned"]
                raise primary

        target = Target()
        first = target.first

        with self.assertRaises(SystemExit) as caught:
            _snapshot_object_state(target, names=("first", "second"))

        self.assertIs(caught.exception, primary)
        self.assertIs(target.first, first)
        self.assertEqual(first, ["captured"])

    def test_topology_depths_support_deep_chain_and_detect_cycle(self) -> None:
        items = [object() for _ in range(1_200)]

        def topology(item, parent):
            return _SceneItemTopologySnapshot(
                item=item,
                parent=parent,
                parent_getter=lambda: None,
                parent_setter=lambda _parent: None,
                z_value=0.0,
                z_getter=lambda: 0.0,
                z_setter=lambda _value: None,
                stack_before=None,
                stacking_flags=None,
                flags_getter=None,
                flags_setter=None,
            )

        chain = tuple(
            topology(
                item,
                items[index - 1] if index else None,
            )
            for index, item in enumerate(items)
        )
        depths = _DetachedSceneSnapshot._topology_depths(tuple(reversed(chain)))
        self.assertEqual(depths[id(items[0])], 0)
        self.assertEqual(depths[id(items[-1])], 1_199)

        first = object()
        second = object()
        cycle = (topology(first, second), topology(second, first))
        with self.assertRaisesRegex(RuntimeError, "parent cycle"):
            _DetachedSceneSnapshot._topology_depths(cycle)

    def test_detached_scene_restores_false_selection_poisoned_during_reattach(
        self,
    ) -> None:
        scene = QGraphicsScene()
        peer = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        peer.setFlag(peer.GraphicsItemFlag.ItemIsSelectable, True)
        peer.setZValue(0.0)

        class SelectingOnReattach(QGraphicsRectItem):
            armed = False

            def itemChange(self, change, value):
                result = QGraphicsRectItem.itemChange(self, change, value)
                if (
                    self.armed
                    and change == self.GraphicsItemChange.ItemSceneHasChanged
                    and value is scene
                ):
                    self.armed = False
                    peer.setSelected(True)
                return result

        selected = SelectingOnReattach(20.0, 0.0, 10.0, 10.0)
        selected.setFlag(selected.GraphicsItemFlag.ItemIsSelectable, True)
        selected.setZValue(1.0)
        scene.addItem(peer)
        scene.addItem(selected)
        selected.setSelected(True)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        snapshot = _snapshot_canvas_scene(view)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        snapshot.detach()
        selected.armed = True
        snapshot.restore()

        self.assertTrue(selected.isSelected())
        self.assertFalse(peer.isSelected())
        self.assertEqual(scene.selectedItems(), [selected])

    def test_detached_scene_restores_parent_topology_and_z_authority(self) -> None:
        scene = QGraphicsScene()
        parent = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        child = QGraphicsRectItem(1.0, 1.0, 5.0, 5.0, parent)
        sibling = QGraphicsRectItem(30.0, 0.0, 10.0, 10.0)
        scene.addItem(parent)
        scene.addItem(sibling)
        child.setZValue(4.0)
        sibling.setZValue(2.0)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        expected_items = tuple(scene.items())
        snapshot = _snapshot_canvas_scene(view)
        assert snapshot is not None

        child.setParentItem(None)
        child.setZValue(99.0)
        sibling.setParentItem(parent)
        sibling.setZValue(-10.0)

        snapshot.restore()
        snapshot._verify_restored_state()

        self.assertIs(child.parentItem(), parent)
        self.assertIsNone(sibling.parentItem())
        self.assertEqual(child.zValue(), 4.0)
        self.assertEqual(sibling.zValue(), 2.0)
        self.assertTrue(
            all(
                actual is expected
                for actual, expected in zip(
                    tuple(scene.items()),
                    expected_items,
                    strict=True,
                )
            )
        )

    def test_detached_scene_selection_callback_cannot_repollute_z_value(self) -> None:
        class CrossMutatingItem(QGraphicsRectItem):
            armed = False

            def setSelected(self, selected: bool) -> None:
                QGraphicsItem.setSelected(self, selected)
                if self.armed:
                    QGraphicsItem.setZValue(self, 99.0)

        scene = QGraphicsScene()
        item = CrossMutatingItem(0.0, 0.0, 10.0, 10.0)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        scene.addItem(item)
        QGraphicsItem.setZValue(item, 3.0)
        QGraphicsItem.setSelected(item, True)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        snapshot = _snapshot_canvas_scene(view)
        assert snapshot is not None

        QGraphicsItem.setSelected(item, False)
        QGraphicsItem.setZValue(item, -4.0)
        item.armed = True
        snapshot.restore()

        self.assertTrue(item.isSelected())
        self.assertEqual(item.zValue(), 3.0)
        snapshot._verify_restored_state()

    def test_detached_scene_uses_captured_selection_ports_with_retry(self) -> None:
        class SelectionPortItem(QGraphicsRectItem):
            def __init__(self) -> None:
                super().__init__(0.0, 0.0, 10.0, 10.0)
                self.getter_lookups = 0
                self.setter_lookups = 0
                self.getter_calls = 0
                self.setter_calls = 0
                self.behavior = "normal"

            @property
            def isSelected(self):
                self.getter_lookups += 1

                def read_selected() -> bool:
                    self.getter_calls += 1
                    if self.behavior == "fail_once_getter" and self.getter_calls == 2:
                        raise KeyboardInterrupt("selection getter failed once")
                    return QGraphicsItem.isSelected(self)

                return read_selected

            @property
            def setSelected(self):
                self.setter_lookups += 1

                def write_selected(selected: bool) -> None:
                    self.setter_calls += 1
                    if self.behavior == "fail_once_setter" and self.setter_calls == 1:
                        raise SystemExit("selection setter failed once")
                    if self.behavior == "no_op":
                        return
                    QGraphicsItem.setSelected(self, selected)

                return write_selected

        for behavior in (
            "fail_once_setter",
            "fail_once_getter",
            "no_op",
        ):
            with self.subTest(behavior=behavior):
                scene = QGraphicsScene()
                item = SelectionPortItem()
                item.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                    True,
                )
                scene.addItem(item)
                QGraphicsItem.setSelected(item, True)
                view = QGraphicsView(scene)
                self.addCleanup(view.close)
                snapshot = _snapshot_canvas_scene(view)
                self.assertIsNotNone(snapshot)
                assert snapshot is not None
                self.assertEqual(item.getter_lookups, 1)
                self.assertEqual(item.setter_lookups, 1)

                snapshot.detach()
                QGraphicsItem.setSelected(item, False)
                item.behavior = behavior
                if behavior == "no_op":
                    with self.assertRaisesRegex(
                        BaseExceptionGroup,
                        "could not restore item selection",
                    ):
                        snapshot.restore()
                    self.assertFalse(QGraphicsItem.isSelected(item))
                else:
                    snapshot.restore()
                    self.assertTrue(QGraphicsItem.isSelected(item))
                    self.assertEqual(
                        item.setter_calls,
                        1 if behavior == "fail_once_getter" else 2,
                    )
                self.assertEqual(item.getter_lookups, 1)
                self.assertEqual(item.setter_lookups, 1)

    def test_document_commit_uses_precaptured_items_bounding_rect_port(self) -> None:
        class DescriptorScene(QGraphicsScene):
            def __init__(self) -> None:
                super().__init__()
                self.bounding_port_lookups = 0
                self.fail_bounding_port_lookup = False

            @property
            def itemsBoundingRect(self):
                self.bounding_port_lookups += 1
                if self.fail_bounding_port_lookup:
                    raise AttributeError(
                        "itemsBoundingRect descriptor failed after target apply"
                    )
                return lambda: QGraphicsScene.itemsBoundingRect(self)

        scene = DescriptorScene()
        old_item = QGraphicsRectItem(0.0, 0.0, 10.0, 10.0)
        scene.addItem(old_item)
        view = QGraphicsView(scene)
        self.addCleanup(view.close)
        snapshot = _snapshot_canvas_scene(view)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(scene.bounding_port_lookups, 0)

        snapshot.detach()
        target_item = QGraphicsRectItem(10_000.0, 0.0, 20.0, 20.0)
        scene.addItem(target_item)
        scene._chemvas_scene_rect_automatic = True
        scene.fail_bounding_port_lookup = True

        snapshot.commit_replacement()

        self.assertEqual(scene.bounding_port_lookups, 0)
        self.assertFalse(snapshot.scene_rect_snapshot.active)
        self.assertEqual(snapshot.scene_rect_snapshot.tracker.depth, 0)
        self.assertTrue(scene._chemvas_scene_rect_automatic)
        self.assertTrue(
            scene.sceneRect().contains(QGraphicsScene.itemsBoundingRect(scene))
        )

    def test_document_commit_verification_fully_rearms_old_rect_savepoint(
        self,
    ) -> None:
        for nested, failure_mode in (
            (False, "no_op"),
            (False, "corrupt_after_commit"),
            (True, "corrupt_after_commit"),
        ):
            with self.subTest(nested=nested, failure=failure_mode):
                scene = QGraphicsScene()
                old_item = scene.addRect(0.0, 0.0, 10.0, 10.0)
                old_rect = QRectF(scene.sceneRect())
                outer_snapshot = SceneRectSnapshot.capture(scene) if nested else None
                view = QGraphicsView(scene)
                self.addCleanup(view.close)
                document_snapshot = _snapshot_canvas_scene(view)
                assert document_snapshot is not None
                rect_snapshot = document_snapshot.scene_rect_snapshot
                assert rect_snapshot is not None
                document_snapshot.detach()
                target_item = scene.addRect(
                    10_000.0,
                    0.0,
                    20.0,
                    20.0,
                )
                target_rect = QRectF(-200.0, -100.0, 400.0, 200.0)
                set_explicit_scene_rect(scene, target_rect)
                tracker = rect_snapshot.tracker
                before_commit = {
                    "known_rect": tracker.known_rect,
                    "baseline_rect": tracker.baseline_rect,
                    "pending_rect": tracker.pending_rect,
                    "pending_expansions": tracker.pending_expansions,
                    "pending_expansion_items": tuple(
                        tracker.pending_expansions.items()
                    ),
                    "pending_journal": tracker.pending_journal,
                    "pending_journal_items": tuple(tracker.pending_journal),
                    "depth": tracker.depth,
                    "internal_change": tracker.internal_change,
                    "accept_internal_rect": tracker.accept_internal_rect,
                    "observed_internal_rect": tracker.observed_internal_rect,
                }
                original_commit = SceneRectSnapshot.commit_replacement

                def broken_commit(
                    active_snapshot,
                    expanded_rect=None,
                    *,
                    _failure_mode=failure_mode,
                    _original_commit=original_commit,
                    _scene=scene,
                ) -> None:
                    if _failure_mode == "no_op":
                        return
                    _original_commit(active_snapshot, expanded_rect)
                    _scene._chemvas_scene_rect_automatic = True

                with mock.patch.object(
                    SceneRectSnapshot,
                    "commit_replacement",
                    new=broken_commit,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "scene-rect mode|scene-rect guard",
                    ):
                        document_snapshot.commit_replacement()

                self.assertTrue(rect_snapshot.active)
                for name in (
                    "known_rect",
                    "baseline_rect",
                    "pending_rect",
                    "pending_expansions",
                    "pending_journal",
                ):
                    self.assertIs(
                        getattr(tracker, name),
                        before_commit[name],
                    )
                self.assertEqual(
                    tuple(tracker.pending_expansions.items()),
                    before_commit["pending_expansion_items"],
                )
                self.assertEqual(
                    tuple(tracker.pending_journal),
                    before_commit["pending_journal_items"],
                )
                for name in (
                    "depth",
                    "internal_change",
                    "accept_internal_rect",
                    "observed_internal_rect",
                ):
                    self.assertEqual(
                        getattr(tracker, name),
                        before_commit[name],
                    )

                document_snapshot.restore()
                self.assertIs(old_item.scene(), scene)
                self.assertIsNone(target_item.scene())
                self.assertTrue(
                    getattr(
                        scene,
                        "_chemvas_scene_rect_automatic",
                        True,
                    )
                )
                if outer_snapshot is None:
                    self.assertEqual(scene.sceneRect(), old_rect)
                else:
                    self.assertTrue(outer_snapshot.active)
                    self.assertEqual(outer_snapshot.tracker.depth, 1)
                    outer_snapshot.restore()
                    self.assertEqual(scene.sceneRect(), old_rect)
                    self.assertEqual(outer_snapshot.tracker.depth, 0)

    def test_document_live_root_descriptor_errors_precede_detach(self) -> None:
        sources = (
            "canvas.runtime_state",
            "runtime.graph_state",
            "canvas.renderer",
            "renderer.style",
            "canvas.selection_style_state",
            "canvas.selection_info_state",
            "canvas.model",
        )

        for source in sources:
            with self.subTest(source=source):

                class RuntimeState:
                    def __init__(self, broken_source: str) -> None:
                        self.broken_source = broken_source
                        self.graph_state = SimpleNamespace(value="before")

                    def __getattribute__(self, name: str):
                        broken_source = object.__getattribute__(
                            self,
                            "broken_source",
                        )
                        if broken_source == f"runtime.{name}":
                            raise AttributeError(f"{broken_source} failed internally")
                        return object.__getattribute__(self, name)

                class Renderer:
                    def __init__(self, broken_source: str) -> None:
                        self.broken_source = broken_source

                    @property
                    def style(self):
                        if self.broken_source == "renderer.style":
                            raise AttributeError(
                                f"{self.broken_source} failed internally"
                            )
                        return object()

                class Canvas:
                    def __init__(self, broken_source: str) -> None:
                        self.broken_source = broken_source
                        self.runtime_state = RuntimeState(broken_source)
                        self.renderer = Renderer(broken_source)
                        self.selection_style_state = SimpleNamespace(selected_items=[])
                        self.selection_info_state = SimpleNamespace(signature=None)
                        self.model = object()

                    def __getattribute__(self, name: str):
                        broken_source = object.__getattribute__(
                            self,
                            "broken_source",
                        )
                        if broken_source == f"canvas.{name}":
                            raise AttributeError(f"{broken_source} failed internally")
                        return object.__getattribute__(self, name)

                canvas = Canvas(source)
                service = CanvasDocumentSessionService(
                    canvas,
                    hit_testing_service=object(),
                    graph_service=object(),
                )
                with (
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                        return_value={},
                    ),
                    self.assertRaisesRegex(
                        AttributeError,
                        f"{source} failed internally",
                    ),
                ):
                    service._snapshot_live_canvas_state()

    def test_post_apply_history_failures_restore_old_document_and_history_exactly(
        self,
    ) -> None:
        for failure_mode in ("clear", "enable"):
            with self.subTest(failure_mode=failure_mode):
                canvas = CanvasView()
                scene = canvas.scene()
                service = canvas.services.canvas_document_session_service
                history_state = service.history.state
                old_history = history_state.history
                old_redo = history_state.redo_stack
                history_command = object()
                redo_command = object()
                old_history.append(history_command)
                old_redo.append(redo_command)
                old_model = canvas.model
                old_scene_rect = QRectF(scene.sceneRect())
                old_view_rect = QRectF(canvas.sceneRect())
                target_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
                old_state = {"model": {"name": "old"}}
                original_clear = service.history.clear
                original_set_enabled = service.history.set_enabled
                enabled_calls = [0]

                def apply_target(
                    _state,
                    *,
                    target_canvas=canvas,
                    target_scene=scene,
                    rect=target_rect,
                ) -> None:
                    target_canvas.model = object()
                    set_explicit_scene_rect(target_scene, rect)
                    set_explicit_view_scene_rect(target_canvas, rect)

                def clear_history(
                    *,
                    mode=failure_mode,
                    state=history_state,
                    redo=old_redo,
                    clear=original_clear,
                ) -> None:
                    if mode == "clear":
                        state.history = []
                        redo.clear()
                        raise SystemExit("history clear terminated")
                    clear()

                def set_enabled(
                    enabled: bool,
                    *,
                    mode=failure_mode,
                    calls=enabled_calls,
                    set_value=original_set_enabled,
                ) -> None:
                    calls[0] += 1
                    set_value(enabled)
                    if mode == "enable" and calls[0] >= 2:
                        raise SystemExit("history enable restore terminated")

                with (
                    mock.patch(
                        "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                        return_value=old_state,
                    ),
                    mock.patch.object(
                        service,
                        "_apply_state_contents",
                        side_effect=apply_target,
                    ),
                    mock.patch.object(
                        service.history,
                        "clear",
                        side_effect=clear_history,
                    ),
                    mock.patch.object(
                        service.history,
                        "set_enabled",
                        side_effect=set_enabled,
                    ),
                ):
                    expected = (
                        "history clear terminated"
                        if failure_mode == "clear"
                        else "history enable restore terminated"
                    )
                    with self.assertRaisesRegex(SystemExit, expected):
                        service.apply_state({"model": {"name": "target"}})

                self.assertIs(canvas.model, old_model)
                self.assertEqual(scene.sceneRect(), old_scene_rect)
                self.assertEqual(canvas.sceneRect(), old_view_rect)
                self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
                self.assertIs(history_state.history, old_history)
                self.assertIs(history_state.redo_stack, old_redo)
                self.assertEqual(old_history, [history_command])
                self.assertEqual(old_redo, [redo_command])
                self.assertTrue(history_state.enabled)
                canvas.close()

    def test_signal_block_interruption_restores_signal_state_and_scene_guard(
        self,
    ) -> None:
        class Item:
            current_scene = None

            def parentItem(self):
                return None

            def scene(self):
                return self.current_scene

            def setSelected(self, _selected) -> None:
                return None

        class InterruptingScene:
            def __init__(
                self,
                item,
                *,
                interrupt_call: int,
                remove_error: BaseException | None = None,
            ) -> None:
                self._items = [item]
                self._blocked = False
                self._rect = QRectF(-0.5, -0.5, 11.0, 11.0)
                self._block_calls = 0
                self._interrupt_call = interrupt_call
                self._remove_error = remove_error
                self._chemvas_scene_rect_automatic = False

            def items(self):
                return list(self._items)

            def removeItem(self, item) -> None:
                if self._remove_error is not None:
                    raise self._remove_error
                self._items.remove(item)
                item.current_scene = None

            def addItem(self, item) -> None:
                if item not in self._items:
                    self._items.append(item)
                item.current_scene = self

            def signalsBlocked(self) -> bool:
                return self._blocked

            def blockSignals(self, blocked: bool) -> bool:
                self._block_calls += 1
                previous = self._blocked
                self._blocked = blocked
                if self._block_calls == self._interrupt_call:
                    raise SystemExit("signal state restore terminated")
                return previous

            def sceneRect(self):
                return QRectF(self._rect)

            def setSceneRect(self, rect) -> None:
                self._rect = QRectF(rect)

            def selectedItems(self):
                return []

            def focusItem(self):
                return None

            def setFocusItem(self, _item) -> None:
                return None

        item = Item()
        scene = InterruptingScene(item, interrupt_call=1)
        item.current_scene = scene
        canvas = SimpleNamespace(scene=lambda: scene)
        snapshot = _snapshot_canvas_scene(canvas)
        self.assertIsNotNone(snapshot)

        snapshot.detach()

        self.assertFalse(scene.signalsBlocked())
        self.assertEqual(scene.items(), [])
        snapshot.restore()
        self.assertEqual(scene.items(), [item])
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))

        primary = KeyboardInterrupt("scene removal interrupted")
        item = Item()
        scene = InterruptingScene(
            item,
            interrupt_call=2,
            remove_error=primary,
        )
        item.current_scene = scene
        snapshot = _snapshot_canvas_scene(SimpleNamespace(scene=lambda: scene))
        self.assertIsNotNone(snapshot)

        with self.assertRaises(KeyboardInterrupt) as caught:
            snapshot.detach()

        self.assertIs(caught.exception, primary)
        self.assertFalse(scene.signalsBlocked())
        self.assertFalse(hasattr(scene, "_chemvas_scene_rect_tracker"))
        self.assertTrue(
            any(
                "SystemExit: signal state restore terminated" in note
                for note in getattr(primary, "__notes__", [])
            )
        )

    def test_scene_signal_block_transitions_are_verified_before_mutation(self) -> None:
        class Item:
            def __init__(self) -> None:
                self.current_scene = None

            def parentItem(self):
                return None

            def scene(self):
                return self.current_scene

        class VerifiedSignalScene:
            def __init__(self, item) -> None:
                self._items = [item]
                self.blocked = False
                self.behavior = "normal"
                self.entry_noops = 0
                self.remove_calls = 0

            def items(self):
                return list(self._items)

            def removeItem(self, item) -> None:
                self.remove_calls += 1
                self._items.remove(item)
                item.current_scene = None

            def addItem(self, item) -> None:
                if item not in self._items:
                    self._items.append(item)
                item.current_scene = self

            def sceneRect(self):
                return "sentinel-rect"

            def setSceneRect(self, _rect) -> None:
                return None

            def selectedItems(self):
                return []

            def focusItem(self):
                return None

            def setFocusItem(self, _item) -> None:
                return None

            def signalsBlocked(self) -> bool:
                return self.blocked

            def blockSignals(self, blocked: bool) -> bool:
                previous = self.blocked
                if self.behavior == "no_op_entry" and blocked:
                    return previous
                if (
                    self.behavior == "fail_once_entry"
                    and blocked
                    and self.entry_noops == 0
                ):
                    self.entry_noops += 1
                    return previous
                if self.behavior == "no_op_exit" and not blocked:
                    return previous
                self.blocked = blocked
                return previous

        item = Item()
        scene = VerifiedSignalScene(item)
        item.current_scene = scene
        snapshot = _snapshot_canvas_scene(SimpleNamespace(scene=lambda: scene))
        assert snapshot is not None
        scene.behavior = "no_op_entry"

        with self.assertRaisesRegex(
            RuntimeError,
            "did not apply the requested state",
        ):
            snapshot.detach()

        self.assertFalse(scene.blocked)
        self.assertEqual(scene.remove_calls, 0)
        self.assertIs(item.current_scene, scene)

        scene.behavior = "fail_once_entry"
        snapshot.detach()
        self.assertFalse(scene.blocked)
        self.assertIsNone(item.current_scene)
        snapshot.restore()
        self.assertFalse(scene.blocked)
        self.assertIs(item.current_scene, scene)

        exit_snapshot = _snapshot_canvas_scene(SimpleNamespace(scene=lambda: scene))
        assert exit_snapshot is not None
        scene.behavior = "no_op_exit"
        with self.assertRaisesRegex(
            RuntimeError,
            "did not apply the requested state",
        ):
            exit_snapshot.detach()
        self.assertTrue(scene.blocked)
        self.assertIs(item.current_scene, scene)

        scene.behavior = "normal"
        exit_snapshot.restore()
        self.assertFalse(scene.blocked)
        self.assertIs(item.current_scene, scene)

    def test_apply_state_success_clears_rotation_preview_and_allows_new_preview(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        scene = QGraphicsScene()
        canvas = _qt_canvas_with_scene_reset(scene)
        old_item = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        scene.addItem(old_item)
        old_group = scene.createItemGroup([old_item])
        preview_state = rotation_preview_state_for(canvas)
        preview_state.group = old_group
        preview_state.position_snapshots = [
            RotationPreviewItemSnapshot(item=old_item, state={"x": 0.0, "y": 0.0})
        ]
        preview_state.center = QPointF(10.0, 10.0)
        service = _session_service(canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"name": "old"}},
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.apply_document_settings"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_pre_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_projection_state"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_post_model_items"
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.restore_document_groups"
            ),
        ):
            service.apply_state({"model": {"name": "target"}})

        self.assertIsNone(preview_state.group)
        self.assertEqual(preview_state.position_snapshots, [])
        self.assertIsNone(preview_state.center)
        self.assertIsNone(old_group.scene())

        new_item = QGraphicsRectItem(30.0, 0.0, 20.0, 20.0)
        scene.addItem(new_item)
        scene_transform = SimpleNamespace(
            rotation_selection_preview=mock.Mock(
                return_value=SimpleNamespace(
                    items=[new_item],
                    position_items=[],
                    center=QPointF(40.0, 10.0),
                )
            ),
            rotation_position_preview_snapshots=mock.Mock(),
        )
        controller = CanvasRotationPreviewController(
            canvas,
            scene_transform_controller=scene_transform,
        )

        self.assertTrue(controller.begin_selection_rotation())
        self.assertIsNotNone(preview_state.group)
        preview_state.reset()
        scene.clear()

    def test_rolled_back_selected_document_can_be_cleared_without_stale_item_callbacks(
        self,
    ) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        self.addCleanup(canvas.services.canvas_scene_reset_service.clear_scene)
        label_atom_id = add_atom_for(canvas, "N", 0.0, 0.0)
        dot_atom_id = add_atom_for(canvas, "C", 20.0, 0.0)
        bond_id = add_bond_for(canvas, label_atom_id, dot_atom_id)
        add_bond_graphics_for(canvas, bond_id)
        selected_items = [
            atom_items_for(canvas)[label_atom_id],
            atom_dots_for(canvas)[dot_atom_id],
            bond_items_for_id(canvas, bond_id)[0],
        ]
        for item in selected_items:
            item.setSelected(True)

        selection_style = selection_style_state_for(canvas)
        original_highlights = list(selected_items)
        selection_style.selected_items = original_highlights
        selection_style.suspend_outline = True
        selection_info = selection_info_state_for(canvas)
        selection_callback = mock.Mock()
        selection_info.callback = selection_callback
        selection_info.signature = (frozenset({label_atom_id}), frozenset({bond_id}))
        selection_info.pending_signature = (
            frozenset({label_atom_id}),
            frozenset({bond_id}),
        )
        selection_info.cache = ("NH", "15.01")
        selection_info.rdkit_warmup_pending = True

        service = canvas.services.canvas_document_session_service
        target_state = deepcopy(service.snapshot_state())
        target_state["settings"]["bond_length_px"] = 31.0
        with mock.patch(
            "chemvas.ui.canvas_document_session_service.restore_document_post_model_items",
            side_effect=RuntimeError("target restore failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state(target_state)

        self.assertTrue(all(item.scene() is canvas.scene() for item in selected_items))
        self.assertTrue(all(item.isSelected() for item in selected_items))
        self.assertIs(selection_style.selected_items, original_highlights)
        self.assertEqual(selection_style.selected_items, selected_items)
        self.assertTrue(selection_style.suspend_outline)
        self.assertIs(selection_info.callback, selection_callback)
        self.assertEqual(
            selection_info.signature,
            (frozenset({label_atom_id}), frozenset({bond_id})),
        )
        self.assertEqual(
            selection_info.pending_signature,
            (frozenset({label_atom_id}), frozenset({bond_id})),
        )
        self.assertEqual(selection_info.cache, ("NH", "15.01"))
        self.assertTrue(selection_info.rdkit_warmup_pending)

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(canvas.scene().items(), [])
        self.assertEqual(canvas.model.atoms, {})
        self.assertEqual(selection_style.selected_items, [])
        self.assertFalse(selection_style.suspend_outline)
        self.assertIsNone(selection_info.signature)
        self.assertIsNone(selection_info.pending_signature)
        self.assertEqual(selection_info.cache, ("", ""))
        self.assertFalse(selection_info.rdkit_warmup_pending)
        self.assertEqual(selection_callback.call_args, mock.call("", ""))

    def test_rollback_status_publication_cannot_corrupt_document_authorities(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        self.addCleanup(canvas.services.canvas_scene_reset_service.clear_scene)
        scene = canvas.scene()
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom = canvas.model.atoms[atom_id]
        atom_item = atom_dots_for(canvas)[atom_id]
        atom_item.setSelected(True)
        model = canvas.model
        atoms = model.atoms
        scene_before = list(scene.items())
        history = canvas.services.history_service.state.history
        history_entry = object()
        history.append(history_entry)
        selection_info = selection_info_state_for(canvas)
        selection_info.cache = ("C", "12.01")
        published: list[tuple[str, str]] = []
        ghosts: list[QGraphicsRectItem] = []

        def corrupt_restored_status(formula: str, mass: str) -> None:
            value = (formula, mass)
            published.append(value)
            if value != ("C", "12.01"):
                return
            atoms.clear()
            history.append(object())
            scene.removeItem(atom_item)
            ghosts.append(scene.addRect(100.0, 100.0, 5.0, 5.0))

        selection_info.callback = corrupt_restored_status
        primary = RuntimeError("target document failed after clear")

        def clear_then_fail(_state: dict) -> None:
            canvas.services.canvas_scene_reset_service.clear_scene()
            raise primary

        with mock.patch.object(
            canvas.services.canvas_document_session_service,
            "_apply_state_contents",
            side_effect=clear_then_fail,
        ):
            with self.assertRaises(RuntimeError) as caught:
                canvas.services.canvas_document_session_service.apply_state(
                    deepcopy(
                        canvas.services.canvas_document_session_service.snapshot_state()
                    )
                )

        self.assertIs(caught.exception, primary)
        self.assertEqual(published.count(("C", "12.01")), 1)
        self.assertIs(canvas.model, model)
        self.assertIs(canvas.model.atoms, atoms)
        self.assertIs(canvas.model.atoms[atom_id], atom)
        self.assertEqual(list(scene.items()), scene_before)
        self.assertIs(atom_item.scene(), scene)
        self.assertTrue(atom_item.isSelected())
        self.assertEqual(history, [history_entry])
        self.assertEqual(selection_info.cache, ("C", "12.01"))
        self.assertIs(selection_info.callback, corrupt_restored_status)
        self.assertEqual(len(ghosts), 1)
        self.assertIsNone(ghosts[0].scene())

    def test_empty_selection_callback_exit_rolls_back_exact_scene_and_retries(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(canvas.close)
        self.addCleanup(canvas.services.canvas_scene_reset_service.clear_scene)
        scene = canvas.scene()
        old_item = QGraphicsRectItem(0.0, 0.0, 20.0, 20.0)
        old_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            True,
        )
        scene.addItem(old_item)
        old_item.setSelected(True)

        service = canvas.services.canvas_document_session_service
        target_state = deepcopy(service.snapshot_state())
        target_state["settings"]["bond_length_px"] = 31.0
        selection_style = selection_style_state_for(canvas)
        original_highlights = [old_item]
        selection_style.selected_items = original_highlights
        selection_style.suspend_outline = True
        selection_info = selection_info_state_for(canvas)
        selection_info.signature = (frozenset({1}), frozenset({2}))
        selection_info.pending_signature = (frozenset({1}), frozenset({2}))
        selection_info.cache = ("OLD", "123.45")
        selection_info.rdkit_warmup_pending = True
        primary_error = KeyboardInterrupt("empty selection callback interrupted")
        callback_calls = 0

        def fail_once_callback(_formula: str, _weight: str) -> None:
            nonlocal callback_calls
            callback_calls += 1
            if callback_calls == 1:
                raise primary_error

        selection_info.callback = fail_once_callback

        with self.assertRaises(KeyboardInterrupt) as caught:
            service.apply_state(target_state)

        self.assertIs(caught.exception, primary_error)
        self.assertIs(old_item.scene(), scene)
        self.assertTrue(old_item.isSelected())
        self.assertFalse(scene.signalsBlocked())
        self.assertIs(selection_style.selected_items, original_highlights)
        self.assertEqual(selection_style.selected_items, [old_item])
        self.assertTrue(selection_style.suspend_outline)
        self.assertIs(selection_info.callback, fail_once_callback)
        self.assertEqual(
            selection_info.signature,
            (frozenset({1}), frozenset({2})),
        )
        self.assertEqual(
            selection_info.pending_signature,
            (frozenset({1}), frozenset({2})),
        )
        self.assertEqual(selection_info.cache, ("OLD", "123.45"))
        self.assertTrue(selection_info.rdkit_warmup_pending)

        service.apply_state(target_state)

        self.assertIsNone(old_item.scene())
        self.assertEqual(selection_style.selected_items, [])
        self.assertFalse(selection_style.suspend_outline)
        self.assertIsNone(selection_info.signature)
        self.assertIsNone(selection_info.pending_signature)
        self.assertEqual(selection_info.cache, ("", ""))
        self.assertFalse(selection_info.rdkit_warmup_pending)
        self.assertGreaterEqual(callback_calls, 3)

    def test_restore_save_and_load_delegate_through_session_methods(self) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(),
            FILE_FORMAT_VERSION=7,
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with mock.patch.object(service, "apply_state") as apply_state:
            service.restore_state({"model": {}})

        apply_state.assert_called_once_with({"model": {}})

        with (
            mock.patch.object(
                service,
                "snapshot_state_with_warnings",
                return_value=({"state": 1}, ["adjusted"]),
            ) as snapshot_state,
            mock.patch(
                "chemvas.ui.canvas_document_session_service.write_document"
            ) as write_document,
        ):
            warnings = service.save_to_file("/tmp/example.chemvas")

        snapshot_state.assert_called_once_with()
        write_document.assert_called_once_with("/tmp/example.chemvas", {"state": 1}, 7)
        self.assertEqual(warnings, ["adjusted"])

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.read_document",
                return_value=SimpleNamespace(state={"loaded": 1}),
            ) as read_document,
            mock.patch.object(service, "restore_state") as restore_state,
        ):
            service.load_from_file("/tmp/example.chemvas")

        read_document.assert_called_once_with("/tmp/example.chemvas")
        restore_state.assert_called_once_with({"loaded": 1})

    def test_export_figure_selection_scope_uses_selected_scene_items(self) -> None:
        selected_item = _SceneItem()
        scene = _Scene([selected_item])
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.5,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
            scene=mock.Mock(return_value=scene),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "out.svg"
            with (
                mock.patch(
                    "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
                    side_effect=lambda _canvas, path, **_kwargs: Path(path).write_text(
                        "<svg />", encoding="utf-8"
                    ),
                ) as export_canvas_scene,
                mock.patch.object(
                    service, "_embed_editable_svg_payload"
                ) as embed_editable_svg,
            ):
                service.export_figure(
                    str(path),
                    fmt="svg",
                    scope="selection",
                    dpi=144,
                    background="white",
                    sizing="bond",
                    editable_svg=True,
                )

            export_canvas_scene.assert_called_once()
            export_args, export_kwargs = export_canvas_scene.call_args
            self.assertIs(export_args[0], canvas)
            tmp_path = Path(export_args[1])
            self.assertEqual(tmp_path.parent, path.parent)
            self.assertTrue(tmp_path.name.startswith(f".{path.name}."))
            self.assertTrue(tmp_path.name.endswith(".tmp"))
            self.assertEqual(
                export_kwargs,
                {
                    "fmt": "svg",
                    "items": [selected_item],
                    "margin": 3.0,
                    "dpi": 144,
                    "background": "white",
                    "title": "Chemvas drawing",
                    "unit_scale": 0.5,
                    "target_width_pt": None,
                },
            )
            embed_editable_svg.assert_called_once_with(
                str(tmp_path), fmt="svg", scope="selection"
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "<svg />")
            self.assertFalse(tmp_path.exists())
        self.assertEqual(canvas.scene.call_count, 2)

    def test_export_mol_writes_molfile_from_payload(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", 0.0, 0.0)
        b = model.add_atom("O", 30.0, 0.0)
        model.add_bond(a, b, 1)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "out.mol")
            with mock.patch.object(
                service, "_build_xyz_payload", return_value=(model, {})
            ):
                service.export_mol(path)
            content = Path(path).read_text()
        self.assertIn("V2000", content)
        self.assertIn("M  END", content)
        self.assertTrue(content.splitlines()[3].startswith("  2  1"))

    def test_export_mol_forwards_selected_only_flag(self) -> None:
        model = MoleculeModel()
        model.add_atom("C", 0.0, 0.0)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "out.mol")
            with mock.patch.object(
                service, "_build_xyz_payload", return_value=(model, {})
            ) as build_payload:
                service.export_mol(path, selected_only=True)
        build_payload.assert_called_once_with(selected_only=True)

    def test_export_mol_raises_when_there_is_no_structure(self) -> None:
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with mock.patch.object(
            service, "_build_xyz_payload", return_value=(MoleculeModel(), {})
        ):
            with self.assertRaises(ValueError):
                service.export_mol("/tmp/should-not-be-written.mol")

    def test_export_mol_falls_back_to_rdkit_for_abbreviation_labels(self) -> None:
        model = MoleculeModel()
        carbon = model.add_atom("C", 0.0, 0.0)
        ph = model.add_atom("Ph", 40.0, 0.0)  # abbreviation -> pure writer rejects
        model.add_bond(carbon, ph, 1)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "out.mol")
            with (
                mock.patch.object(
                    service, "_build_xyz_payload", return_value=(model, {})
                ),
                mock.patch(
                    "chemvas.ui.canvas_document_session_service.model_to_mol_block_for",
                    return_value="expanded\n\n\n  0  0  0  0  0  0  0  0999 V2000\nM  END\n",
                ) as fallback,
            ):
                service.export_mol(path)
            content = Path(path).read_text()
        fallback.assert_called_once()
        self.assertIn("M  END", content)

    def test_export_mol_surfaces_v2000_limit_without_rdkit_fallback(self) -> None:
        # Hard V2000 limits hold for any writer: the RDKit abbreviation
        # fallback must not swallow them or blame missing RDKit.
        model = MoleculeModel()
        for index in range(1000):
            model.add_atom("C", float(index), 0.0)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with (
            mock.patch.object(service, "_build_xyz_payload", return_value=(model, {})),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.model_to_mol_block_for",
                return_value="should-not-be-used",
            ) as fallback,
        ):
            with self.assertRaises(ValueError) as ctx:
                service.export_mol("/tmp/should-not-be-written.mol")
        fallback.assert_not_called()
        self.assertIn("999 atoms", str(ctx.exception))

    def test_export_mol_reports_install_rdkit_when_abbreviation_cannot_expand(
        self,
    ) -> None:
        model = MoleculeModel()
        model.add_atom("Ph", 0.0, 0.0)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with (
            mock.patch.object(service, "_build_xyz_payload", return_value=(model, {})),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.model_to_mol_block_for",
                return_value=None,
            ),
            mock.patch(
                "chemvas.ui.canvas_document_session_service.rdkit_last_error_for",
                return_value="RDKit is not available in this environment.",
            ),
        ):
            with self.assertRaises(ValueError) as ctx:
                service.export_mol("/tmp/should-not-be-written.mol")
        self.assertIn("Install RDKit", str(ctx.exception))

    def test_export_figure_selection_scope_requires_selected_items(self) -> None:
        scene = _Scene()
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
            scene=mock.Mock(return_value=scene),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.export_canvas_scene_for"
            ) as export_canvas_scene,
            self.assertRaisesRegex(ValueError, "Select something to export"),
        ):
            service.export_figure("/tmp/out.svg", scope="selection")

        export_canvas_scene.assert_not_called()

    def test_export_figure_column_sizing_sets_target_width(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "out.png"
            with mock.patch(
                "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
                side_effect=lambda _canvas, path, **_kwargs: Path(path).write_text(
                    "PNG", encoding="utf-8"
                ),
            ) as export_canvas_scene:
                service.export_figure(str(path), fmt="png", sizing="col1")

        self.assertIsNone(export_canvas_scene.call_args.kwargs["items"])
        self.assertEqual(export_canvas_scene.call_args.kwargs["unit_scale"], 1.0)
        self.assertAlmostEqual(
            export_canvas_scene.call_args.kwargs["target_width_pt"], 84.0 / 25.4 * 72.0
        )

    def test_export_figure_plain_svg_does_not_embed_sheet_payload_by_default(
        self,
    ) -> None:
        canvas = SimpleNamespace(
            FILE_FORMAT_VERSION=1,
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        service.snapshot_state = mock.Mock(return_value=_canvas_state())

        def write_svg(_canvas, path, **_kwargs) -> None:
            Path(path).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" />',
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "figure.svg")
            with mock.patch(
                "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
                side_effect=write_svg,
            ):
                service.export_figure(path, fmt="svg", scope="sheet")

            with self.assertRaises(ValueError):
                extract_chemvas_document_from_svg(path)
            service.snapshot_state.assert_not_called()

    def test_export_figure_embeds_sheet_payload_in_editable_svg_file(self) -> None:
        canvas = SimpleNamespace(
            FILE_FORMAT_VERSION=1,
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        state = _canvas_state()
        service.snapshot_state = mock.Mock(return_value=state)

        def write_svg(_canvas, path, **_kwargs) -> None:
            Path(path).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" />',
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "figure.svg")
            with mock.patch(
                "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
                side_effect=write_svg,
            ):
                service.export_figure(path, fmt="svg", scope="sheet", editable_svg=True)

            self.assertEqual(extract_chemvas_document_from_svg(path).state, state)

    def test_export_figure_keeps_existing_svg_when_metadata_embedding_fails(
        self,
    ) -> None:
        canvas = SimpleNamespace(
            FILE_FORMAT_VERSION=1,
            renderer=SimpleNamespace(
                style=SimpleNamespace(
                    bond_line_width=1.0,
                    bond_length_px=30.0,
                    bond_length_pt=15.0,
                )
            ),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)

        def write_svg(_canvas, path, **_kwargs) -> None:
            Path(path).write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" />',
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "figure.svg"
            path.write_text("ORIGINAL", encoding="utf-8")
            with (
                mock.patch(
                    "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
                    side_effect=write_svg,
                ) as export_canvas_scene,
                mock.patch.object(
                    service,
                    "_embed_editable_svg_payload",
                    side_effect=RuntimeError("metadata"),
                ),
                self.assertRaisesRegex(RuntimeError, "metadata"),
            ):
                service.export_figure(
                    str(path), fmt="svg", scope="sheet", editable_svg=True
                )

            export_canvas_scene.assert_called_once()
            export_args, _export_kwargs = export_canvas_scene.call_args
            tmp_path = Path(export_args[1])
            self.assertEqual(tmp_path.parent, path.parent)
            self.assertTrue(tmp_path.name.startswith(f".{path.name}."))
            self.assertTrue(tmp_path.name.endswith(".tmp"))
            self.assertEqual(path.read_text(encoding="utf-8"), "ORIGINAL")
            self.assertFalse(tmp_path.exists())

    def test_embed_editable_svg_payload_uses_sheet_state_for_svg_only(self) -> None:
        state = {
            "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
            "ring_fills": [],
            "notes": [],
            "marks": [],
            "arrows": [],
            "ts_brackets": [],
            "orbitals": [],
            "settings": {},
            "last_smiles_input": None,
        }
        canvas = SimpleNamespace(FILE_FORMAT_VERSION=7)
        _attach_history_service(canvas)
        service = _session_service(canvas)
        service.snapshot_state = mock.Mock(return_value=state)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.create_editable_svg_payload",
                return_value={"payload": 1},
            ) as create_payload,
            mock.patch(
                "chemvas.ui.canvas_document_session_service.embed_chemvas_document_in_svg"
            ) as embed_svg,
        ):
            service._embed_editable_svg_payload(
                "/tmp/out.svg", fmt="svg", scope="sheet"
            )
            service._embed_editable_svg_payload(
                "/tmp/out.png", fmt="png", scope="sheet"
            )

        create_payload.assert_called_once_with(state, document_version=7, scope="sheet")
        embed_svg.assert_called_once_with("/tmp/out.svg", {"payload": 1})
        service.snapshot_state.assert_called_once_with()

    def test_embed_editable_svg_payload_uses_selection_state_for_selection_scope(
        self,
    ) -> None:
        state = {"selection": "state"}
        canvas = SimpleNamespace(FILE_FORMAT_VERSION=7)
        _attach_history_service(canvas)
        service = _session_service(canvas)
        service._selection_document_state = mock.Mock(return_value=state)

        with (
            mock.patch(
                "chemvas.ui.canvas_document_session_service.create_editable_svg_payload",
                return_value={"payload": 1},
            ) as create_payload,
            mock.patch(
                "chemvas.ui.canvas_document_session_service.embed_chemvas_document_in_svg"
            ) as embed_svg,
        ):
            service._embed_editable_svg_payload(
                "/tmp/out.svg", fmt="svg", scope="selection"
            )

        create_payload.assert_called_once_with(
            state, document_version=7, scope="selection"
        )
        embed_svg.assert_called_once_with("/tmp/out.svg", {"payload": 1})
        service._selection_document_state.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
