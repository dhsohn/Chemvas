import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.document_state import serialize_settings
from core.model import MoleculeModel
from core.svg_roundtrip import extract_chemvas_document_from_svg
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)
from ui.bond_graphics_access import add_bond_graphics_for
from ui.canvas_atom_graphics_state import atom_dots_for, atom_items_for
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_document_session_service import CanvasDocumentSessionService
from ui.canvas_history_service import CanvasHistoryService
from ui.canvas_history_state import CanvasHistoryState, history_state_for
from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
from ui.canvas_rotation_preview_state import (
    RotationPreviewItemSnapshot,
    rotation_preview_state_for,
)
from ui.canvas_runtime_state import attach_canvas_runtime_state
from ui.canvas_scene_reset_service import CanvasSceneResetService
from ui.canvas_view import CanvasView
from ui.history_commands import UpdateSceneItemCommand
from ui.selection_style_state import SelectionStyleState
from ui.structure_mutation_access import add_atom_for, add_bond_for


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
        canvas_graph_service=SimpleNamespace(rebuild_bond_adjacency=rebuild_bond_adjacency),
        structure_build_service=SimpleNamespace(
            render_model=render_model,
            ensure_ring_fills_for_model=mock.Mock(),
        ),
        hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mark_spatial_index_dirty),
    )


def _attach_history_service(canvas):
    service = CanvasHistoryService(canvas, history_state_for(canvas))
    services = getattr(canvas, "services", None)
    if services is None:
        services = SimpleNamespace()
        canvas.services = services
    services.history_service = service
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

    def test_apply_state_restores_document_lifecycle_and_reenables_history(self) -> None:
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
            rebuild_bond_adjacency=mock.Mock(side_effect=lambda: events.append("adjacency")),
            render_model=mock.Mock(side_effect=lambda: events.append("render")),
            mark_spatial_index_dirty=mock.Mock(side_effect=lambda: events.append("dirty")),
        )
        _attach_history_service(canvas)
        service = _session_service(canvas)
        history_state_for(canvas).history.append(object())
        history_state_for(canvas).redo_stack.append(object())

        with (
            mock.patch(
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"atoms": []}},
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: events.append("settings"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda _model: events.append("deserialize") or "new-model",
            ),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_pre_model_items",
                side_effect=lambda _canvas, _state: events.append("pre"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_projection_state",
                side_effect=lambda _canvas, _state: events.append("projection"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
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
            ["clear", "settings", "deserialize", "adjacency", "pre", "projection", "render", "post", "dirty"],
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"atoms": []}},
            ),
            mock.patch("ui.canvas_document_session_service.apply_document_settings"),
            mock.patch("ui.canvas_document_session_service.deserialize_model_state", return_value="new-model"),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                service.apply_state({"model": {"atoms": []}})

        self.assertTrue(history_state_for(canvas).enabled)

    def test_apply_state_failure_restores_previous_document_and_history_exactly(self) -> None:
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, state: (
                    setattr(canvas, "settings", state["settings"]["name"]),
                    setattr(canvas, "sheet_size", "A4"),
                    setattr(canvas, "sheet_orientation", "portrait"),
                ),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda model_state: model_state["name"],
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=restore_post_items,
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
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

    def test_apply_state_retries_fail_once_rollback_clear_restore_and_verification(self) -> None:
        import ui.canvas_document_session_service as session_module

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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                side_effect=snapshot_state,
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: setattr(canvas, "settings", "target-settings"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                return_value="target-model",
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch("ui.canvas_document_session_service.restore_document_post_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
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

    def test_apply_state_clears_history_only_when_previous_document_restore_also_fails(self) -> None:
        canvas = SimpleNamespace(
            history_state=CanvasHistoryState(history=[object()], redo_stack=[object()], enabled=False),
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"name": "old-model"}},
            ),
            mock.patch("ui.canvas_document_session_service.apply_document_settings"),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                side_effect=lambda model_state: model_state["name"],
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch(
                "ui.canvas_document_session_service._CanvasRollbackSnapshot.restore_live_state",
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

                def phase(name: str, *, target_canvas=canvas, target_failure=failing_phase):
                    def restore(_canvas, _state) -> None:
                        target_canvas.scene_items.append(f"target-{name}")
                        if name == target_failure:
                            raise RuntimeError(f"{name} failed")

                    return restore

                canvas.services = _document_services(
                    clear_scene=clear_scene,
                    rebuild_bond_adjacency=mock.Mock(),
                    render_model=lambda target_canvas=canvas: target_canvas.scene_items.append(
                        "target-model-item"
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
                        "ui.canvas_document_session_service.snapshot_canvas_document_state",
                        return_value=old_state,
                    ),
                    mock.patch(
                        "ui.canvas_document_session_service.apply_document_settings",
                        side_effect=lambda _canvas, _state, target_canvas=canvas: setattr(
                            target_canvas,
                            "settings",
                            "target-settings",
                        ),
                    ),
                    mock.patch(
                        "ui.canvas_document_session_service.deserialize_model_state",
                        return_value="target-model",
                    ),
                    mock.patch(
                        "ui.canvas_document_session_service.restore_document_pre_model_items",
                        side_effect=phase("pre"),
                    ),
                    mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
                    mock.patch(
                        "ui.canvas_document_session_service.restore_document_post_model_items",
                        side_effect=phase("post"),
                    ),
                    mock.patch(
                        "ui.canvas_document_session_service.restore_document_groups",
                        side_effect=phase("groups"),
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, f"{failing_phase} failed"):
                        service.apply_state({"model": "target"})

                self.assertEqual(canvas.model, "old-model")
                self.assertEqual(canvas.settings, "old-settings")
                self.assertEqual(canvas.scene_items, ["old-item"])
                self.assertEqual(history_state_for(canvas).history, [command])
                self.assertEqual(history_state_for(canvas).redo_stack, [])
                self.assertTrue(history_state_for(canvas).enabled)

    def test_apply_state_detach_failure_restores_items_and_history_before_raising(self) -> None:
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
            "ui.canvas_document_session_service.snapshot_canvas_document_state",
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

    def test_apply_state_rollback_preserves_live_parent_child_item_history_references(self) -> None:
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda _canvas, _state: setattr(canvas, "settings", "target-settings"),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                return_value="target-model",
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("post-model failure"),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
            mock.patch(
                "ui.history_commands._apply_scene_item_state",
                side_effect=lambda _canvas, item, state: item.setPos(state["x"], 0.0),
            ),
            mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
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
        scene.setSceneRect(scene_rect)
        canvas = _qt_canvas_with_scene_reset(scene)
        canvas.setSceneRect(view_rect)
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=lambda target, _state: target.setSceneRect(target_view_rect),
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("target restore failed"),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
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

    def test_apply_state_rollback_restores_clamped_viewport_pan_and_transform(self) -> None:
        app = QApplication.instance() or QApplication([])
        self.assertIsNotNone(app)
        app.setQuitOnLastWindowClosed(False)
        scene = QGraphicsScene()
        canvas = _qt_canvas_with_scene_reset(scene)
        canvas.resize(200, 200)
        canvas.show()

        original_rect = QRectF(-1000.0, -500.0, 2000.0, 1000.0)
        target_rect = QRectF(-100.0, -100.0, 200.0, 200.0)
        scene.setSceneRect(original_rect)
        canvas.setSceneRect(original_rect)
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
            target.scene().setSceneRect(target_rect)
            target.setSceneRect(target_rect)
            target.resetTransform()

        with (
            mock.patch(
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value=old_state,
            ),
            mock.patch(
                "ui.canvas_document_session_service.apply_document_settings",
                side_effect=apply_target_view,
            ),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch(
                "ui.canvas_document_session_service.restore_document_post_model_items",
                side_effect=RuntimeError("target restore failed"),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state({"model": {"name": "target"}})

        app.processEvents()
        self.assertEqual(canvas.sceneRect(), original_rect)
        self.assertEqual(scene.sceneRect(), original_rect)
        self.assertEqual(canvas.transform(), original_transform)
        self.assertEqual(horizontal.value(), original_horizontal)
        self.assertEqual(vertical.value(), original_vertical)
        self.assertEqual(canvas.mapToScene(canvas.viewport().rect().center()), original_center)
        canvas.close()

    def test_apply_state_success_clears_rotation_preview_and_allows_new_preview(self) -> None:
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
                "ui.canvas_document_session_service.snapshot_canvas_document_state",
                return_value={"model": {"name": "old"}},
            ),
            mock.patch("ui.canvas_document_session_service.apply_document_settings"),
            mock.patch(
                "ui.canvas_document_session_service.deserialize_model_state",
                return_value=MoleculeModel(),
            ),
            mock.patch("ui.canvas_document_session_service.restore_document_pre_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_projection_state"),
            mock.patch("ui.canvas_document_session_service.restore_document_post_model_items"),
            mock.patch("ui.canvas_document_session_service.restore_document_groups"),
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

    def test_rolled_back_selected_document_can_be_cleared_without_stale_item_callbacks(self) -> None:
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

        service = canvas.services.canvas_document_session_service
        target_state = deepcopy(service.snapshot_state())
        target_state["settings"]["bond_length_px"] = 31.0
        with mock.patch(
            "ui.canvas_document_session_service.restore_document_post_model_items",
            side_effect=RuntimeError("target restore failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "target restore failed"):
                service.apply_state(target_state)

        self.assertTrue(all(item.scene() is canvas.scene() for item in selected_items))
        self.assertTrue(all(item.isSelected() for item in selected_items))

        canvas.services.canvas_scene_reset_service.clear_scene()

        self.assertEqual(canvas.scene().items(), [])
        self.assertEqual(canvas.model.atoms, {})

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
            mock.patch("ui.canvas_document_session_service.write_document") as write_document,
        ):
            warnings = service.save_to_file("/tmp/example.chemvas")

        snapshot_state.assert_called_once_with()
        write_document.assert_called_once_with("/tmp/example.chemvas", {"state": 1}, 7)
        self.assertEqual(warnings, ["adjusted"])

        with (
            mock.patch("ui.canvas_document_session_service.read_document", return_value=SimpleNamespace(state={"loaded": 1})) as read_document,
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
                    "ui.canvas_document_session_service.export_canvas_scene_for",
                    side_effect=lambda _canvas, path, **_kwargs: Path(path).write_text("<svg />", encoding="utf-8"),
                ) as export_canvas_scene,
                mock.patch.object(service, "_embed_editable_svg_payload") as embed_editable_svg,
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
            embed_editable_svg.assert_called_once_with(str(tmp_path), fmt="svg", scope="selection")
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
            with mock.patch.object(service, "_build_xyz_payload", return_value=(model, {})):
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
        with mock.patch.object(service, "_build_xyz_payload", return_value=(MoleculeModel(), {})):
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
                mock.patch.object(service, "_build_xyz_payload", return_value=(model, {})),
                mock.patch(
                    "ui.canvas_document_session_service.model_to_mol_block_for",
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
                "ui.canvas_document_session_service.model_to_mol_block_for",
                return_value="should-not-be-used",
            ) as fallback,
        ):
            with self.assertRaises(ValueError) as ctx:
                service.export_mol("/tmp/should-not-be-written.mol")
        fallback.assert_not_called()
        self.assertIn("999 atoms", str(ctx.exception))

    def test_export_mol_reports_install_rdkit_when_abbreviation_cannot_expand(self) -> None:
        model = MoleculeModel()
        model.add_atom("Ph", 0.0, 0.0)
        service = _session_service(_attach_history_service(SimpleNamespace()))
        with (
            mock.patch.object(service, "_build_xyz_payload", return_value=(model, {})),
            mock.patch("ui.canvas_document_session_service.model_to_mol_block_for", return_value=None),
            mock.patch(
                "ui.canvas_document_session_service.rdkit_last_error_for",
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
            mock.patch("ui.canvas_document_session_service.export_canvas_scene_for") as export_canvas_scene,
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
                "ui.canvas_document_session_service.export_canvas_scene_for",
                side_effect=lambda _canvas, path, **_kwargs: Path(path).write_text("PNG", encoding="utf-8"),
            ) as export_canvas_scene:
                service.export_figure(str(path), fmt="png", sizing="col1")

        self.assertIsNone(export_canvas_scene.call_args.kwargs["items"])
        self.assertEqual(export_canvas_scene.call_args.kwargs["unit_scale"], 1.0)
        self.assertAlmostEqual(export_canvas_scene.call_args.kwargs["target_width_pt"], 84.0 / 25.4 * 72.0)

    def test_export_figure_plain_svg_does_not_embed_sheet_payload_by_default(self) -> None:
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
            with mock.patch("ui.canvas_document_session_service.export_canvas_scene_for", side_effect=write_svg):
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
            with mock.patch("ui.canvas_document_session_service.export_canvas_scene_for", side_effect=write_svg):
                service.export_figure(path, fmt="svg", scope="sheet", editable_svg=True)

            self.assertEqual(extract_chemvas_document_from_svg(path).state, state)

    def test_export_figure_keeps_existing_svg_when_metadata_embedding_fails(self) -> None:
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
                mock.patch("ui.canvas_document_session_service.export_canvas_scene_for", side_effect=write_svg) as export_canvas_scene,
                mock.patch.object(service, "_embed_editable_svg_payload", side_effect=RuntimeError("metadata")),
                self.assertRaisesRegex(RuntimeError, "metadata"),
            ):
                service.export_figure(str(path), fmt="svg", scope="sheet", editable_svg=True)

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
                "ui.canvas_document_session_service.create_editable_svg_payload",
                return_value={"payload": 1},
            ) as create_payload,
            mock.patch("ui.canvas_document_session_service.embed_chemvas_document_in_svg") as embed_svg,
        ):
            service._embed_editable_svg_payload("/tmp/out.svg", fmt="svg", scope="sheet")
            service._embed_editable_svg_payload("/tmp/out.png", fmt="png", scope="sheet")

        create_payload.assert_called_once_with(state, document_version=7, scope="sheet")
        embed_svg.assert_called_once_with("/tmp/out.svg", {"payload": 1})
        service.snapshot_state.assert_called_once_with()

    def test_embed_editable_svg_payload_uses_selection_state_for_selection_scope(self) -> None:
        state = {"selection": "state"}
        canvas = SimpleNamespace(FILE_FORMAT_VERSION=7)
        _attach_history_service(canvas)
        service = _session_service(canvas)
        service._selection_document_state = mock.Mock(return_value=state)

        with (
            mock.patch(
                "ui.canvas_document_session_service.create_editable_svg_payload",
                return_value={"payload": 1},
            ) as create_payload,
            mock.patch("ui.canvas_document_session_service.embed_chemvas_document_in_svg") as embed_svg,
        ):
            service._embed_editable_svg_payload("/tmp/out.svg", fmt="svg", scope="selection")

        create_payload.assert_called_once_with(state, document_version=7, scope="selection")
        embed_svg.assert_called_once_with("/tmp/out.svg", {"payload": 1})
        service._selection_document_state.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
