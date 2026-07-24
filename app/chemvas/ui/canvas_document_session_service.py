from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from chemvas.core.document_io import (
    atomic_write_text,
    atomic_write_via_temp,
    read_document,
    write_document,
)
from chemvas.core.molfile import MolfileError, MolfileLimitError, write_molfile
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.core.svg_roundtrip import (
    CHEMVAS_SVG_SCOPE_SELECTION,
    CHEMVAS_SVG_SCOPE_SHEET,
    create_editable_svg_payload,
    embed_chemvas_document_in_svg,
)
from chemvas.domain.document import (
    deserialize_model_state,
    selection_payload_to_canvas_state,
)
from chemvas.ui.canvas_document_export_access import export_canvas_scene_for
from chemvas.ui.canvas_document_state import (
    apply_document_settings,
    restore_document_groups,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    restore_document_projection_state,
    snapshot_canvas_document_state,
    snapshot_canvas_document_state_with_warnings,
)
from chemvas.ui.canvas_format_access import (
    clipboard_selection_version_for,
    file_format_version_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import bonds_for, set_model_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_scene_reset_access import clear_scene_for
from chemvas.ui.rdkit_adapter_access import (
    model_to_mol_block_for,
    model_to_xyz_block_for,
    preload_rdkit_for,
    rdkit_adapter_for,
    rdkit_is_loaded_for,
    rdkit_last_error_for,
)
from chemvas.ui.renderer_style_access import (
    bond_length_pt_for,
    bond_length_px_for,
    bond_line_width_for,
)
from chemvas.ui.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.selection_collection_access import (
    selected_ids_for,
    selection_items_for_copy_for,
)
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_style_access import set_selected_highlight_items_for
from chemvas.ui.structure_payload_access import (
    build_3d_conversion_payload_for,
    build_selected_3d_conversion_payload_for,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    ContainerGraphSnapshot as _ContainerGraphSnapshot,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    ObjectStateSnapshot as _ObjectStateSnapshot,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    SceneRectStateSnapshot,
    scene_rect_is_automatic,
    view_scene_rect_is_explicit,
)

_DOCUMENT_MUTATED_RUNTIME_FIELDS = (
    "sheet_setup_state",
    "selection_info_state",
    "graph_state",
    "group_state",
    "insert_state",
    "atom_coords_3d_state",
    "atom_graphics_state",
    "bond_graphics_state",
    "mark_registry",
    "spatial_index_state",
    "rotation_state",
    "handle_state",
    "selection_style_state",
    "selection_outline_state",
    "text_style_state",
    "tool_settings_state",
    "hover_preview_state",
    "scene_items_state",
    "smiles_input_state",
)


_MISSING_ATTRIBUTE = object()


def _capture_optional_attribute(
    target: object,
    name: str,
    *,
    default: object = None,
) -> object:
    """Read a capture root once, treating only a truly absent name as absent.

    A property that exists but raises AttributeError internally is a real
    bug; silently recording the root as missing would corrupt the document
    savepoint, so capture must abort instead.
    """

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        ):
            raise
        return default


def _add_scene_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    original_error.add_note(
        f"Document scene recovery also failed while {phase}: "
        f"{type(secondary_error).__name__}: {secondary_error}"
    )


def _collect_errors(operation, destination: list[BaseException]) -> None:
    try:
        result = operation()
    except BaseException as exc:
        destination.append(exc)
        return
    destination.extend(result)


@dataclass(slots=True)
class _DetachedSceneSnapshot:
    """The previous document's live scene contents, kept alive detached.

    Top-level items are removed from the scene (children stay attached to
    their parents), so a failed document open can reattach the exact same
    item objects instead of rebuilding them. Qt scenes get exact scene-rect
    savepoints; supported duck scenes fall back to their raw rect value.
    """

    canvas: Any
    scene: Any
    is_qt_scene: bool
    all_scene_items: tuple[Any, ...]
    top_level_items: tuple[Any, ...]
    scene_rect_snapshot: SceneRectSnapshot | None
    scene_rect_state_snapshot: SceneRectStateSnapshot | None
    raw_scene_rect: Any
    view: Any | None
    view_scene_rect: Any | None
    view_scene_rect_explicit: bool
    view_transform: Any | None
    horizontal_scroll_value: int | None
    vertical_scroll_value: int | None
    selected_items: tuple[Any, ...]
    focus_item: Any | None
    scene_signals_blocked: bool | None

    @classmethod
    def capture(cls, canvas) -> _DetachedSceneSnapshot | None:
        if isinstance(canvas, QGraphicsView):
            scene = QGraphicsView.scene(canvas)
        else:
            scene_method = _capture_optional_attribute(canvas, "scene")
            scene = scene_method() if callable(scene_method) else None
        if scene is None:
            return None
        is_qt_scene = isinstance(scene, QGraphicsScene)
        if is_qt_scene:
            all_items = tuple(QGraphicsScene.items(scene))
        else:
            items_method = getattr(scene, "items", None)
            if not callable(items_method):
                return None
            all_items = tuple(items_method())
        top_level_items = tuple(item for item in all_items if item.parentItem() is None)

        scene_rect_snapshot: SceneRectSnapshot | None = None
        scene_rect_state_snapshot: SceneRectStateSnapshot | None = None
        raw_scene_rect = scene.sceneRect()
        try:
            QRectF(raw_scene_rect)
        except (TypeError, ValueError):
            # A duck scene with a non-rect sceneRect value keeps raw
            # save/restore semantics instead of the exact rect savepoints.
            pass
        else:
            scene_rect_state_snapshot = SceneRectStateSnapshot.capture(scene)
            scene_rect_snapshot = SceneRectSnapshot.capture(
                scene,
                scene_items_bounding_rect_getter=(
                    scene.itemsBoundingRect
                    if callable(getattr(scene, "itemsBoundingRect", None))
                    else None
                ),
            )

        view: Any | None = None
        view_scene_rect = None
        view_scene_rect_explicit = False
        view_transform = None
        horizontal_scroll_value = None
        vertical_scroll_value = None
        if isinstance(canvas, QGraphicsView):
            view = canvas
            view_scene_rect = QRectF(canvas.sceneRect())
            view_scene_rect_explicit = view_scene_rect_is_explicit(canvas)
            view_transform = canvas.transform()
            horizontal_bar = canvas.horizontalScrollBar()
            if horizontal_bar is not None:
                horizontal_scroll_value = int(horizontal_bar.value())
            vertical_bar = canvas.verticalScrollBar()
            if vertical_bar is not None:
                vertical_scroll_value = int(vertical_bar.value())

        selected_items_method = getattr(scene, "selectedItems", None)
        selected_items = (
            tuple(selected_items_method()) if callable(selected_items_method) else ()
        )
        focus_item_method = getattr(scene, "focusItem", None)
        focus_item = focus_item_method() if callable(focus_item_method) else None
        signals_blocked_method = getattr(scene, "signalsBlocked", None)
        scene_signals_blocked = (
            bool(signals_blocked_method()) if callable(signals_blocked_method) else None
        )

        return cls(
            canvas=canvas,
            scene=scene,
            is_qt_scene=is_qt_scene,
            all_scene_items=all_items,
            top_level_items=top_level_items,
            scene_rect_snapshot=scene_rect_snapshot,
            scene_rect_state_snapshot=scene_rect_state_snapshot,
            raw_scene_rect=raw_scene_rect,
            view=view,
            view_scene_rect=view_scene_rect,
            view_scene_rect_explicit=view_scene_rect_explicit,
            view_transform=view_transform,
            horizontal_scroll_value=horizontal_scroll_value,
            vertical_scroll_value=vertical_scroll_value,
            selected_items=selected_items,
            focus_item=focus_item,
            scene_signals_blocked=scene_signals_blocked,
        )

    def _blocked_signals(self):
        if callable(getattr(self.scene, "blockSignals", None)):
            return blocked_scene_signals(self.scene)
        from contextlib import nullcontext

        return nullcontext()

    def _current_items(self) -> tuple[Any, ...]:
        if self.is_qt_scene:
            return tuple(QGraphicsScene.items(self.scene))
        return tuple(self.scene.items())

    def detach(self) -> None:
        with self._blocked_signals():
            for item in self.top_level_items:
                self.scene.removeItem(item)

    def restore(self) -> None:
        with self._blocked_signals():
            saved_item_ids = {id(item) for item in self.all_scene_items}
            current_items = self._current_items()
            replacement_ids = {
                id(item) for item in current_items if id(item) not in saved_item_ids
            }
            for item in current_items:
                if id(item) not in replacement_ids:
                    continue
                parent = item.parentItem()
                if parent is None or id(parent) not in replacement_ids:
                    self.scene.removeItem(item)
            # Detach every saved root first, then re-add. Qt scenes report
            # items() topmost-first, so re-add bottommost-first there;
            # insertion order is what keeps equal-z sibling stacking stable.
            for item in self.top_level_items:
                if item.scene() is self.scene:
                    self.scene.removeItem(item)
            reattach_items = (
                reversed(self.top_level_items)
                if self.is_qt_scene
                else iter(self.top_level_items)
            )
            for item in reattach_items:
                self.scene.addItem(item)
            if self.scene_rect_snapshot is not None:
                if self.scene_rect_snapshot.active:
                    self.scene_rect_snapshot.restore()
                else:
                    self.scene_rect_snapshot.reassert()
                if self.scene_rect_state_snapshot is not None:
                    self.scene_rect_state_snapshot.restore()
            else:
                self.scene.setSceneRect(self.raw_scene_rect)
            if self.view is not None:
                if self.view_scene_rect_explicit and self.view_scene_rect is not None:
                    self.view.setSceneRect(QRectF(self.view_scene_rect))
                    self.view._chemvas_view_scene_rect_explicit = True
                else:
                    self.view.setSceneRect(QRectF())
                    self.view._chemvas_view_scene_rect_explicit = False
                if self.view_transform is not None:
                    self.view.setTransform(self.view_transform)
            selected_ids = {id(item) for item in self.selected_items}
            for item in self.all_scene_items:
                item.setSelected(id(item) in selected_ids)
            set_focus_item = getattr(self.scene, "setFocusItem", None)
            if callable(set_focus_item):
                set_focus_item(self.focus_item)
            # Selection and focus restoration can ask the view to reveal an
            # item; restore the exact pan last.
            if self.view is not None:
                horizontal_bar = self.view.horizontalScrollBar()
                if self.horizontal_scroll_value is not None and (
                    horizontal_bar is not None
                ):
                    horizontal_bar.setValue(self.horizontal_scroll_value)
                vertical_bar = self.view.verticalScrollBar()
                if self.vertical_scroll_value is not None and (
                    vertical_bar is not None
                ):
                    vertical_bar.setValue(self.vertical_scroll_value)
        # A failure inside a signal-blocked production section leaves the
        # scene blocked; rollback restores the captured baseline state.
        if self.scene_signals_blocked is not None:
            self.scene.blockSignals(self.scene_signals_blocked)

    def verify_restored(self) -> None:
        current_items = self._current_items()
        if set(map(id, current_items)) != set(map(id, self.all_scene_items)) or (
            self.is_qt_scene
            and any(
                current is not expected
                for current, expected in zip(
                    current_items,
                    self.all_scene_items,
                    strict=False,
                )
            )
        ):
            raise RuntimeError(
                "document rollback did not restore the exact scene-item set"
            )
        selected_items_method = getattr(self.scene, "selectedItems", None)
        if callable(selected_items_method):
            actual_selected = {id(item) for item in selected_items_method()}
            if actual_selected != {id(item) for item in self.selected_items}:
                raise RuntimeError(
                    "document rollback did not restore the selected-item set"
                )
        focus_item_method = getattr(self.scene, "focusItem", None)
        if callable(focus_item_method) and focus_item_method() is not self.focus_item:
            raise RuntimeError("document rollback did not restore scene focus")

    def commit_replacement(self) -> None:
        # The scene-rect commit is deliberately the last fallible step of a
        # successful replacement: after it there is nothing left that could
        # fail while exposing the new document as half-committed.
        if self.scene_rect_snapshot is None:
            return
        expanded_rect = None
        if scene_rect_is_automatic(self.scene) and callable(
            getattr(self.scene, "itemsBoundingRect", None)
        ):
            expanded_rect = QRectF(self.scene.itemsBoundingRect())
        self.scene_rect_snapshot.commit_replacement(expanded_rect)
        if self.scene_rect_state_snapshot is not None:
            self.scene_rect_state_snapshot.release()


def _snapshot_canvas_scene(canvas) -> _DetachedSceneSnapshot | None:
    return _DetachedSceneSnapshot.capture(canvas)


@dataclass(slots=True)
class _DocumentStatusPublication:
    callback: Callable[[str, str], object] | None
    cache: tuple[str, str] | None
    published: bool = False

    def publish(self, original_error: BaseException) -> None:
        if self.published:
            return
        self.published = True
        if self.callback is None or self.cache is None:
            return
        try:
            self.callback(*self.cache)
        except BaseException as publication_error:
            _add_scene_recovery_note(
                original_error,
                publication_error,
                phase="republishing the restored document selection status",
            )


@dataclass(slots=True)
class _HistoryStateSnapshot:
    service: Any
    state: Any
    history: list
    history_items: tuple
    redo_stack: list
    redo_items: tuple
    enabled: bool


@dataclass(frozen=True, slots=True)
class _CanvasRollbackSnapshot:
    document_state: dict
    model: Any
    containers: _ContainerGraphSnapshot
    object_states: tuple[_ObjectStateSnapshot, ...]
    scene: _DetachedSceneSnapshot | None
    status_publication: _DocumentStatusPublication

    def detach_scene_items(self) -> None:
        if self.scene is not None:
            self.scene.detach()

    def restore_live_state(self, canvas) -> list[BaseException]:
        errors: list[BaseException] = []
        try:
            canvas.model = self.model
        except BaseException as exc:
            errors.append(exc)
        _collect_errors(self.containers.restore, errors)
        for snapshot in self.object_states:
            _collect_errors(snapshot.restore, errors)
        if self.scene is not None:
            try:
                self.scene.restore()
            except BaseException as exc:
                errors.append(exc)
        # Reattaching and reselecting Qt items can refresh derived runtime
        # registries even while scene signals are blocked. Those registries
        # are rollback authority too, so make the captured object state the
        # final silent writer after every scene-side operation.
        _collect_errors(self.containers.restore, errors)
        for snapshot in self.object_states:
            _collect_errors(snapshot.restore, errors)
        return errors

    def commit_replacement(self) -> None:
        if self.scene is not None:
            self.scene.commit_replacement()


class CanvasDocumentSessionService:
    def __init__(
        self,
        canvas,
        *,
        hit_testing_service,
        graph_service,
        structure_build_service=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service
        self.structure_build_service = structure_build_service

    def snapshot_state(self) -> dict:
        return snapshot_canvas_document_state(self.canvas)

    def apply_state(self, state: dict) -> None:
        """Replace the current document, all-or-nothing.

        The previous document is preserved as a savepoint — live Qt items are
        detached, not copied — and history recording is disabled while the
        replacement is built. On failure the previous document is restored
        exactly (same item objects, selection, focus, view, history); if that
        restore itself fails the canvas converges on a blank document with
        history cleared, so no half-applied state is ever left behind. On
        success the previous history is discarded and the savepoint committed.
        """

        if self.structure_build_service is None:
            raise RuntimeError(
                "structure_build_service is required to apply document state"
            )
        history_snapshot = self._snapshot_history_state()
        rollback_snapshot = self._snapshot_live_canvas_state()
        try:
            # The rollback snapshot holds the scene-rect guard open from here
            # on; any pre-detach failure must run the rollback path so the
            # guard is closed rather than left pinning automatic growth.
            self._set_history_enabled(history_snapshot, False)
            rollback_snapshot.detach_scene_items()
            self._clear_detached_selection_state()
        except BaseException as original_error:
            # The scene still holds the previous document (possibly with a
            # partially detached suffix of roots); clearing it here would
            # destroy the savepoint, so restore without a target clear.
            self._rollback_or_converge(
                rollback_snapshot,
                history_snapshot,
                original_error=original_error,
                clear_target=False,
            )
            raise
        try:
            self._apply_state_contents(state)
            if history_snapshot is not None:
                history_snapshot.service.clear()
            self._restore_history_enabled(history_snapshot)
            rollback_snapshot.commit_replacement()
        except BaseException as original_error:
            # The previous document's items are detached and safe; clear the
            # partially built replacement out of the scene before reattaching.
            self._rollback_or_converge(
                rollback_snapshot,
                history_snapshot,
                original_error=original_error,
                clear_target=True,
            )
            raise

    def _rollback_or_converge(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot | None,
        *,
        original_error: BaseException,
        clear_target: bool,
    ) -> None:
        try:
            if clear_target:
                self._clear_target_for_rollback()
            self._restore_previous_document(
                rollback_snapshot,
                history_snapshot,
                original_error=original_error,
            )
        except BaseException as rollback_error:
            # The previous document could not be reconstructed. Keep the
            # canvas internally consistent and discard commands that no
            # longer describe it rather than exposing a partially applied
            # target or rollback state.
            _add_scene_recovery_note(
                original_error,
                rollback_error,
                phase="restoring the previous document",
            )
            try:
                clear_scene_for(self.canvas)
            except BaseException as cleanup_error:
                _add_scene_recovery_note(
                    original_error,
                    cleanup_error,
                    phase="clearing an unrecoverable document scene",
                )
            try:
                self._force_clear_history(history_snapshot)
            except BaseException as cleanup_error:
                _add_scene_recovery_note(
                    original_error,
                    cleanup_error,
                    phase="clearing unrecoverable document history",
                )
        finally:
            try:
                self._restore_history_enabled(history_snapshot)
            except BaseException as secondary_error:
                _add_scene_recovery_note(
                    original_error,
                    secondary_error,
                    phase="restoring the history enabled state",
                )

    def _snapshot_history_state(self) -> _HistoryStateSnapshot | None:
        if self.history is None:
            return None
        state = self.history.state
        history = state.history
        redo_stack = state.redo_stack
        if not isinstance(history, list) or not isinstance(redo_stack, list):
            raise RuntimeError("document history stacks must be mutable lists")
        return _HistoryStateSnapshot(
            service=self.history,
            state=state,
            history=history,
            history_items=tuple(history),
            redo_stack=redo_stack,
            redo_items=tuple(redo_stack),
            enabled=bool(state.enabled),
        )

    @staticmethod
    def _set_history_enabled(
        snapshot: _HistoryStateSnapshot | None,
        enabled: bool,
    ) -> None:
        if snapshot is None:
            return
        if bool(snapshot.state.enabled) is not enabled:
            snapshot.service.set_enabled(enabled)

    def _restore_history_enabled(
        self,
        snapshot: _HistoryStateSnapshot | None,
    ) -> None:
        if snapshot is not None:
            self._set_history_enabled(snapshot, snapshot.enabled)

    @staticmethod
    def _restore_history_state(snapshot: _HistoryStateSnapshot | None) -> None:
        if snapshot is None:
            return
        snapshot.history[:] = snapshot.history_items
        snapshot.redo_stack[:] = snapshot.redo_items
        # A history clear that failed midway can have replaced the stack
        # attributes; point them back at the captured list objects so every
        # alias holder keeps observing the same stacks.
        if snapshot.state.history is not snapshot.history:
            snapshot.state.history = snapshot.history
        if snapshot.state.redo_stack is not snapshot.redo_stack:
            snapshot.state.redo_stack = snapshot.redo_stack

    @staticmethod
    def _force_clear_history(snapshot: _HistoryStateSnapshot | None) -> None:
        if snapshot is None:
            return
        snapshot.history[:] = []
        snapshot.redo_stack[:] = []

    def _clear_target_for_rollback(self) -> None:
        try:
            clear_scene_for(self.canvas)
        except BaseException:
            # Scene reset is designed to be idempotent. A step may fail after
            # clearing only one registry; retry once before declaring the
            # preserved previous document unrecoverable.
            clear_scene_for(self.canvas)

    def _restore_previous_document(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot | None,
        *,
        original_error: BaseException,
    ) -> None:
        restore_errors = rollback_snapshot.restore_live_state(self.canvas)
        for restore_error in restore_errors:
            _add_scene_recovery_note(
                original_error,
                restore_error,
                phase="restoring the previous document scene",
            )
        self._restore_history_state(history_snapshot)
        self._restore_history_enabled(history_snapshot)
        rollback_snapshot.status_publication.publish(original_error)
        self._verify_previous_document(rollback_snapshot, restore_errors)

    def _verify_previous_document(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        restore_errors: list[BaseException],
    ) -> None:
        if restore_errors:
            raise RuntimeError("Failed to restore the previous canvas document state.")
        if self.canvas.model is not rollback_snapshot.model:
            raise RuntimeError("document rollback changed model identity")
        if rollback_snapshot.scene is not None:
            rollback_snapshot.scene.verify_restored()
        restored_state = self.snapshot_state()
        if restored_state != rollback_snapshot.document_state:
            raise RuntimeError("Failed to restore the previous canvas document state.")

    def _apply_state_contents(self, state: dict) -> None:
        clear_scene_for(self.canvas)
        apply_document_settings(self.canvas, state)
        set_model_for(self.canvas, deserialize_model_state(state["model"]))
        self.graph_service.rebuild_bond_adjacency()
        restore_document_pre_model_items(self.canvas, state)
        restore_document_projection_state(self.canvas, state)
        self.structure_build_service.render_model()
        restore_document_post_model_items(self.canvas, state)
        restore_document_groups(self.canvas, state)
        self.hit_testing_service.mark_spatial_index_dirty()

    def _snapshot_live_canvas_state(self) -> _CanvasRollbackSnapshot:
        containers = _ContainerGraphSnapshot()
        object_states: list[_ObjectStateSnapshot] = []
        seen_objects: set[int] = set()

        def append_snapshot(
            target: Any,
            *,
            names: tuple[str, ...] | None = None,
        ) -> _ObjectStateSnapshot | None:
            if target is None or id(target) in seen_objects:
                return None
            snapshot = _ObjectStateSnapshot.capture(
                target,
                containers,
                names=names,
            )
            if snapshot is None:
                return None
            seen_objects.add(id(target))
            object_states.append(snapshot)
            return snapshot

        runtime_state = _capture_optional_attribute(self.canvas, "runtime_state")
        if runtime_state is not None:
            for name in _DOCUMENT_MUTATED_RUNTIME_FIELDS:
                append_snapshot(_capture_optional_attribute(runtime_state, name))

        append_snapshot(
            _capture_optional_attribute(self.canvas, "renderer"),
            names=("style",),
        )
        append_snapshot(
            _capture_optional_attribute(self.canvas, "selection_style_state")
        )
        append_snapshot(
            _capture_optional_attribute(self.canvas, "selection_info_state")
        )
        append_snapshot(
            self.canvas,
            names=(
                "settings",
                "scene_items",
                "sheet_size",
                "sheet_orientation",
            ),
        )

        model = _capture_optional_attribute(self.canvas, "model")
        append_snapshot(
            model,
            names=("atoms", "bonds", "next_atom_id", "atom_annotations"),
        )
        atoms = _capture_optional_attribute(model, "atoms")
        if isinstance(atoms, dict):
            for atom in tuple(atoms.values()):
                append_snapshot(atom)
        bonds = _capture_optional_attribute(model, "bonds")
        if isinstance(bonds, (list, tuple)):
            for bond in tuple(bonds):
                if bond is not None:
                    append_snapshot(bond)

        selection_info = selection_info_state_for(self.canvas)
        status_callback = _capture_optional_attribute(selection_info, "callback")
        status_cache = _capture_optional_attribute(selection_info, "cache")
        status_publication = _DocumentStatusPublication(
            callback=status_callback if callable(status_callback) else None,
            cache=(
                (str(status_cache[0]), str(status_cache[1]))
                if isinstance(status_cache, tuple) and len(status_cache) == 2
                else None
            ),
        )

        document_state = self.snapshot_state()
        scene_snapshot = _DetachedSceneSnapshot.capture(self.canvas)
        return _CanvasRollbackSnapshot(
            document_state=document_state,
            model=model,
            containers=containers,
            object_states=tuple(object_states),
            scene=scene_snapshot,
            status_publication=status_publication,
        )

    def _clear_detached_selection_state(self) -> None:
        set_selected_highlight_items_for(self.canvas, [])
        runtime_state = getattr(self.canvas, "runtime_state", None)
        selection_info_state = (
            getattr(runtime_state, "selection_info_state", None)
            if runtime_state is not None
            else getattr(self.canvas, "selection_info_state", None)
        )
        if selection_info_state is None:
            return
        selection_info_state.signature = None
        selection_info_state.pending_signature = None
        selection_info_state.cache = ("", "")
        selection_info_state.rdkit_warmup_pending = False

    def restore_state(self, state: dict) -> None:
        self.apply_state(state)

    def snapshot_state_with_warnings(self) -> tuple[dict, list[str]]:
        return snapshot_canvas_document_state_with_warnings(self.canvas)

    def save_to_file(self, path: str) -> list[str]:
        state, warnings = self.snapshot_state_with_warnings()
        write_document(path, state, file_format_version_for(self.canvas))
        return warnings

    def load_from_file(self, path: str) -> None:
        document = read_document(path)
        self.restore_state(document.state)

    def _build_xyz_payload(self, *, selected_only: bool = False):
        if selected_only:
            return build_selected_3d_conversion_payload_for(self.canvas)
        return build_3d_conversion_payload_for(self.canvas)

    def export_xyz(self, path: str, *, selected_only: bool = False) -> None:
        export_model, atom_annotations = self._build_xyz_payload(
            selected_only=selected_only
        )
        xyz_block = model_to_xyz_block_for(
            self.canvas, export_model, atom_annotations=atom_annotations
        )
        if xyz_block is None:
            message = rdkit_last_error_for(self.canvas) or "Failed to export 3D XYZ."
            raise ValueError(message)
        atomic_write_text(path, xyz_block)

    def export_mol(self, path: str, *, selected_only: bool = False) -> None:
        export_model, atom_annotations = self._build_xyz_payload(
            selected_only=selected_only
        )
        if not export_model.atoms:
            raise ValueError("There is no molecular structure to export.")
        try:
            block = write_molfile(export_model, atom_annotations=atom_annotations)
        except MolfileLimitError:
            # Hard V2000 capacity/range limits hold for any writer; falling
            # back to RDKit would either mask them or blame missing RDKit.
            raise
        except MolfileError as exc:
            # The structure uses abbreviation labels (Ph, CF3, ...) that are not
            # single elements. Fall back to RDKit, which expands them into explicit
            # atoms; without RDKit there is no way to expand them.
            block = model_to_mol_block_for(
                self.canvas, export_model, atom_annotations=atom_annotations
            )
            if block is None:
                reason = rdkit_last_error_for(self.canvas)
                if not reason or "not available" in reason.lower():
                    raise ValueError(
                        f"{exc} Install RDKit to expand these abbreviations automatically."
                    ) from exc
                raise ValueError(reason) from exc
        atomic_write_text(path, block)

    def export_xyz_async(
        self, path: str, *, on_success, on_error, selected_only: bool = False
    ) -> None:
        try:
            export_model, atom_annotations = self._build_xyz_payload(
                selected_only=selected_only
            )
        except Exception as exc:
            on_error(str(exc) or "Failed to export 3D XYZ.")
            return
        if not rdkit_is_loaded_for(self.canvas) and not preload_rdkit_for(self.canvas):
            on_error(
                rdkit_last_error_for(self.canvas)
                or "RDKit is not available in this environment."
            )
            return

        from chemvas.ui.rdkit_async_jobs import export_xyz_in_thread

        export_xyz_in_thread(
            self.canvas,
            rdkit_adapter=rdkit_adapter_for(self.canvas),
            model=export_model,
            atom_annotations=atom_annotations,
            path=path,
            on_success=on_success,
            on_error=on_error,
            rdkit_adapter_factory=RDKitAdapter,
        )

    def export_figure(
        self,
        path: str,
        *,
        fmt: str = "svg",
        scope: str = "sheet",
        dpi: int = 300,
        background: str = "transparent",
        sizing: str = "bond",
        editable_svg: bool = False,
    ) -> None:
        from chemvas.features.export import points_for_mm

        pad = max(2.0, bond_line_width_for(self.canvas) * 2.0)
        items = None
        if scope == "selection":
            items = selection_items_for_copy_for(self.canvas)
            if not items:
                raise ValueError("Select something to export, or choose Whole canvas.")

        unit_scale = 1.0
        target_width_pt = None
        if sizing == "bond":
            bond_length_px = bond_length_px_for(self.canvas)
            if bond_length_px > 0:
                unit_scale = bond_length_pt_for(self.canvas) / bond_length_px
        elif sizing == "col1":
            target_width_pt = points_for_mm(84.0)
        elif sizing == "col2":
            target_width_pt = points_for_mm(174.0)

        fmt = fmt.lower()
        target = Path(path)

        def render_to_temp(tmp: Path) -> None:
            export_canvas_scene_for(
                self.canvas,
                str(tmp),
                fmt=fmt,
                items=items,
                margin=pad,
                dpi=dpi,
                background=background,
                title="Chemvas drawing",
                unit_scale=unit_scale,
                target_width_pt=target_width_pt,
            )
            if fmt == "svg" and editable_svg:
                self._embed_editable_svg_payload(str(tmp), fmt=fmt, scope=scope)

        atomic_write_via_temp(target, render_to_temp)

    def _embed_editable_svg_payload(self, path: str, *, fmt: str, scope: str) -> None:
        if fmt.lower() != "svg":
            return
        if scope == "selection":
            state = self._selection_document_state()
            svg_scope = CHEMVAS_SVG_SCOPE_SELECTION
        else:
            state = self.snapshot_state()
            svg_scope = CHEMVAS_SVG_SCOPE_SHEET
        payload = create_editable_svg_payload(
            state,
            document_version=file_format_version_for(self.canvas),
            scope=svg_scope,
        )
        embed_chemvas_document_in_svg(path, payload)

    def _selection_document_state(self) -> dict:
        selected_items = selection_items_for_copy_for(self.canvas)
        explicit_atom_ids, bond_ids = selected_ids_for(self.canvas)
        selection_payload = build_selection_clipboard_payload_for_canvas(
            self.canvas,
            selected_items=selected_items,
            explicit_atom_ids=explicit_atom_ids,
            selected_bond_ids=bond_ids,
            bonds=bonds_for(self.canvas),
            ring_items=ring_items_for(self.canvas),
            marks_by_atom=mark_registry_for(self.canvas).by_atom,
            atom_state_getter=lambda atom_id: atom_state_dict_for(self.canvas, atom_id),
            bond_state_getter=bond_state_dict,
            scene_item_state_getter=lambda item: scene_item_state_for(
                self.canvas, item
            ),
            version=clipboard_selection_version_for(self.canvas),
        )
        if selection_payload is None:
            raise ValueError("Select something to export, or choose Whole canvas.")
        return selection_payload_to_canvas_state(
            selection_payload,
            self.snapshot_state()["settings"],
        )


__all__ = ["CanvasDocumentSessionService"]
