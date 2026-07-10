from __future__ import annotations

import contextlib
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

from core.document_io import (
    atomic_write_text,
    atomic_write_via_temp,
    read_document,
    write_document,
)
from core.document_state import (
    deserialize_model_state,
    selection_payload_to_canvas_state,
)
from core.molfile import MolfileError, MolfileLimitError, write_molfile
from core.svg_roundtrip import (
    CHEMVAS_SVG_SCOPE_SELECTION,
    CHEMVAS_SVG_SCOPE_SHEET,
    create_editable_svg_payload,
    embed_chemvas_document_in_svg,
)

from ui.canvas_document_export_access import export_canvas_scene_for
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_groups,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    restore_document_projection_state,
    snapshot_canvas_document_state,
    snapshot_canvas_document_state_with_warnings,
)
from ui.canvas_format_access import (
    clipboard_selection_version_for,
    file_format_version_for,
)
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import bonds_for, set_model_for
from ui.canvas_scene_items_state import ring_items_for
from ui.canvas_scene_reset_access import clear_scene_for
from ui.rdkit_adapter_access import (
    model_to_mol_block_for,
    model_to_xyz_block_for,
    new_rdkit_adapter,
    preload_rdkit_for,
    rdkit_adapter_for,
    rdkit_is_loaded_for,
    rdkit_last_error_for,
)
from ui.renderer_style_access import (
    bond_length_pt_for,
    bond_length_px_for,
    bond_line_width_for,
)
from ui.scene_clipboard_access import build_selection_clipboard_payload_for_canvas
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from ui.selection_collection_access import (
    selected_ids_for,
    selection_items_for_copy_for,
)
from ui.selection_style_access import set_selected_highlight_items_for
from ui.structure_payload_access import (
    build_3d_conversion_payload_for,
    build_selected_3d_conversion_payload_for,
)


@dataclass(frozen=True, slots=True)
class _HistoryStateSnapshot:
    history: list
    history_items: tuple[Any, ...]
    redo_stack: list
    redo_items: tuple[Any, ...]
    enabled: bool


_NO_CONTAINER_CONTENTS = object()

# CanvasSceneResetService and the document-state restore helpers mutate only
# these runtime records. Keep this explicit so lifecycle-owning QObject fields
# (the RDKit idle timer/bridge) are never snapshotted or assigned reflectively.
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
    "rotation_preview_state",
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


@dataclass(frozen=True, slots=True)
class _AttributeSnapshot:
    value: Any
    contents: Any = _NO_CONTAINER_CONTENTS

    @classmethod
    def capture(cls, value: Any) -> _AttributeSnapshot:
        if isinstance(value, dict):
            return cls(value, dict(value))
        if isinstance(value, list):
            return cls(value, list(value))
        if isinstance(value, set):
            return cls(value, set(value))
        return cls(value)

    def restored_value(self) -> Any:
        if self.contents is _NO_CONTAINER_CONTENTS:
            return self.value
        if isinstance(self.value, dict):
            self.value.clear()
            self.value.update(self.contents)
        elif isinstance(self.value, list):
            self.value[:] = self.contents
        elif isinstance(self.value, set):
            self.value.clear()
            self.value.update(self.contents)
        return self.value


@dataclass(frozen=True, slots=True)
class _ObjectStateSnapshot:
    target: Any
    attributes: dict[str, _AttributeSnapshot]

    def restore(self) -> None:
        for name, snapshot in self.attributes.items():
            setattr(self.target, name, snapshot.restored_value())


@dataclass(frozen=True, slots=True)
class _DetachedSceneSnapshot:
    scene: Any
    top_level_items: tuple[Any, ...]
    scene_rect: Any
    view: Any | None
    view_scene_rect: Any | None
    view_transform: Any | None
    horizontal_scroll_bar: Any | None
    horizontal_scroll_value: int | None
    vertical_scroll_bar: Any | None
    vertical_scroll_value: int | None
    selected_items: tuple[Any, ...]
    focus_item: Any | None

    def detach(self) -> None:
        previous_blocked = self.scene.blockSignals(True)
        try:
            for item in self.top_level_items:
                self.scene.removeItem(item)
        except BaseException:
            with contextlib.suppress(Exception):
                self.restore()
            raise
        finally:
            self.scene.blockSignals(previous_blocked)

    def restore(self) -> None:
        previous_blocked = self.scene.blockSignals(True)
        try:
            # QGraphicsScene.items() is topmost-first. Re-add bottommost-first
            # so equal-z stacking and parent/child history references survive.
            for item in reversed(self.top_level_items):
                scene_method = getattr(item, "scene", None)
                if callable(scene_method) and scene_method() is self.scene:
                    continue
                self.scene.addItem(item)
            self.scene.setSceneRect(self.scene_rect)
            if self.view is not None:
                self.view.setSceneRect(self.view_scene_rect)
                if self.view_transform is not None:
                    set_transform = getattr(self.view, "setTransform", None)
                    if callable(set_transform):
                        set_transform(self.view_transform)
            for item in self.selected_items:
                item.setSelected(True)
            if self.focus_item is not None:
                self.scene.setFocusItem(self.focus_item)
            # Selection/focus restoration can ask a view to reveal an item.
            # Restore the exact pan last, after every operation that may scroll.
            if self.horizontal_scroll_bar is not None and self.horizontal_scroll_value is not None:
                self.horizontal_scroll_bar.setValue(self.horizontal_scroll_value)
            if self.vertical_scroll_bar is not None and self.vertical_scroll_value is not None:
                self.vertical_scroll_bar.setValue(self.vertical_scroll_value)
        finally:
            self.scene.blockSignals(previous_blocked)


@dataclass(frozen=True, slots=True)
class _CanvasRollbackSnapshot:
    document_state: dict
    model: Any
    object_states: tuple[_ObjectStateSnapshot, ...]
    scene: _DetachedSceneSnapshot | None

    def detach_scene_items(self) -> None:
        if self.scene is not None:
            self.scene.detach()

    def restore_live_state(self, canvas) -> None:
        canvas.model = self.model
        for snapshot in self.object_states:
            snapshot.restore()
        if self.scene is not None:
            self.scene.restore()


def _snapshot_object_state(
    target: Any,
    *,
    names: tuple[str, ...] | None = None,
) -> _ObjectStateSnapshot | None:
    if names is None:
        if is_dataclass(target) and not isinstance(target, type):
            names = tuple(field.name for field in fields(target))
        else:
            namespace = getattr(target, "__dict__", None)
            if not isinstance(namespace, dict):
                return None
            names = tuple(namespace)
    attributes = {
        name: _AttributeSnapshot.capture(getattr(target, name))
        for name in names
        if hasattr(target, name)
    }
    if not attributes:
        return None
    return _ObjectStateSnapshot(target=target, attributes=attributes)


def _snapshot_canvas_scene(canvas) -> _DetachedSceneSnapshot | None:
    scene_method = getattr(canvas, "scene", None)
    if not callable(scene_method):
        return None
    scene = scene_method()
    if scene is None or not all(
        callable(getattr(scene, method, None))
        for method in (
            "items",
            "removeItem",
            "addItem",
            "sceneRect",
            "setSceneRect",
            "selectedItems",
            "focusItem",
            "setFocusItem",
            "blockSignals",
        )
    ):
        return None
    top_level_items = tuple(
        item
        for item in scene.items()
        if not callable(getattr(item, "parentItem", None)) or item.parentItem() is None
    )
    view = None
    view_scene_rect = None
    view_transform = None
    horizontal_scroll_bar = None
    horizontal_scroll_value = None
    vertical_scroll_bar = None
    vertical_scroll_value = None
    view_scene_rect_method = getattr(canvas, "sceneRect", None)
    view_set_scene_rect = getattr(canvas, "setSceneRect", None)
    if callable(view_scene_rect_method) and callable(view_set_scene_rect):
        view = canvas
        view_scene_rect = view_scene_rect_method()
        view_transform_method = getattr(canvas, "transform", None)
        view_set_transform = getattr(canvas, "setTransform", None)
        if callable(view_transform_method) and callable(view_set_transform):
            view_transform = view_transform_method()
        horizontal_scroll_bar_method = getattr(canvas, "horizontalScrollBar", None)
        if callable(horizontal_scroll_bar_method):
            candidate = horizontal_scroll_bar_method()
            if callable(getattr(candidate, "value", None)) and callable(
                getattr(candidate, "setValue", None)
            ):
                horizontal_scroll_bar = candidate
                horizontal_scroll_value = int(candidate.value())
        vertical_scroll_bar_method = getattr(canvas, "verticalScrollBar", None)
        if callable(vertical_scroll_bar_method):
            candidate = vertical_scroll_bar_method()
            if callable(getattr(candidate, "value", None)) and callable(
                getattr(candidate, "setValue", None)
            ):
                vertical_scroll_bar = candidate
                vertical_scroll_value = int(candidate.value())
    return _DetachedSceneSnapshot(
        scene=scene,
        top_level_items=top_level_items,
        scene_rect=scene.sceneRect(),
        view=view,
        view_scene_rect=view_scene_rect,
        view_transform=view_transform,
        horizontal_scroll_bar=horizontal_scroll_bar,
        horizontal_scroll_value=horizontal_scroll_value,
        vertical_scroll_bar=vertical_scroll_bar,
        vertical_scroll_value=vertical_scroll_value,
        selected_items=tuple(scene.selectedItems()),
        focus_item=scene.focusItem(),
    )


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
        if self.structure_build_service is None:
            raise RuntimeError("structure_build_service is required to apply document state")
        rollback_snapshot = self._snapshot_live_canvas_state()
        history_snapshot = self._snapshot_history_state()
        self.history.set_enabled(False)
        try:
            rollback_snapshot.detach_scene_items()
            self._clear_detached_selection_state()
        except BaseException:
            try:
                self._restore_previous_document(
                    rollback_snapshot,
                    history_snapshot,
                )
            except BaseException:
                with contextlib.suppress(Exception):
                    clear_scene_for(self.canvas)
                self.history.clear()
            finally:
                self.history.set_enabled(history_snapshot.enabled)
            raise
        try:
            self._apply_state_contents(state)
        except BaseException:
            try:
                self._clear_target_for_rollback()
                self._restore_previous_document(
                    rollback_snapshot,
                    history_snapshot,
                )
            except BaseException:
                # The previous document could not be reconstructed. Keep the
                # canvas internally consistent and discard commands that no
                # longer describe it rather than exposing a partially applied
                # target or rollback state.
                with contextlib.suppress(Exception):
                    clear_scene_for(self.canvas)
                self.history.clear()
            raise
        else:
            # A successfully replaced document invalidates every command that
            # refers to the detached old scene. Clear it before those items can
            # leave this transaction's strong ownership.
            self.history.clear()
        finally:
            self.history.set_enabled(history_snapshot.enabled)

    def _clear_target_for_rollback(self) -> None:
        try:
            clear_scene_for(self.canvas)
        except BaseException:
            # Scene reset is designed to be idempotent. A callback may fail
            # after clearing only one registry; retry once before declaring the
            # preserved previous document unrecoverable.
            clear_scene_for(self.canvas)

    def _restore_previous_document(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot,
    ) -> None:
        try:
            rollback_snapshot.restore_live_state(self.canvas)
        except BaseException:
            # Re-attachment skips items already restored, so a fail-once scene
            # add or view setter can safely resume from the partial attempt.
            rollback_snapshot.restore_live_state(self.canvas)

        try:
            restored_state = self.snapshot_state()
        except BaseException:
            # Serialization itself can fail transiently (for example while a
            # Qt wrapper finishes a selection callback). Do not discard an
            # otherwise exact live rollback on the first verification error.
            restored_state = self.snapshot_state()
        if restored_state != rollback_snapshot.document_state:
            raise RuntimeError("Failed to restore the previous canvas document state.")

        try:
            self._restore_history_state(history_snapshot)
        except BaseException:
            self._restore_history_state(history_snapshot)

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
        object_states: list[_ObjectStateSnapshot] = []
        seen_objects: set[int] = set()

        def append_snapshot(target: Any, *, names: tuple[str, ...] | None = None) -> None:
            if target is None or id(target) in seen_objects:
                return
            snapshot = _snapshot_object_state(target, names=names)
            if snapshot is None:
                return
            seen_objects.add(id(target))
            object_states.append(snapshot)

        runtime_state = getattr(self.canvas, "runtime_state", None)
        if runtime_state is not None:
            for name in _DOCUMENT_MUTATED_RUNTIME_FIELDS:
                append_snapshot(getattr(runtime_state, name))

        renderer = getattr(self.canvas, "renderer", None)
        append_snapshot(renderer, names=("style",))
        append_snapshot(getattr(self.canvas, "selection_style_state", None))
        append_snapshot(getattr(self.canvas, "selection_info_state", None))
        append_snapshot(
            self.canvas,
            names=(
                "settings",
                "scene_items",
                "sheet_size",
                "sheet_orientation",
            ),
        )

        return _CanvasRollbackSnapshot(
            document_state=self.snapshot_state(),
            model=getattr(self.canvas, "model", None),
            object_states=tuple(object_states),
            scene=_snapshot_canvas_scene(self.canvas),
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

    def _snapshot_history_state(self) -> _HistoryStateSnapshot:
        history_state = self.history.state
        return _HistoryStateSnapshot(
            history=history_state.history,
            history_items=tuple(history_state.history),
            redo_stack=history_state.redo_stack,
            redo_items=tuple(history_state.redo_stack),
            enabled=bool(history_state.enabled),
        )

    def _restore_history_state(self, snapshot: _HistoryStateSnapshot) -> None:
        snapshot.history[:] = snapshot.history_items
        snapshot.redo_stack[:] = snapshot.redo_items
        history_state = self.history.state
        history_state.history = snapshot.history
        history_state.redo_stack = snapshot.redo_stack

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
        export_model, atom_annotations = self._build_xyz_payload(selected_only=selected_only)
        xyz_block = model_to_xyz_block_for(self.canvas, export_model, atom_annotations=atom_annotations)
        if xyz_block is None:
            message = rdkit_last_error_for(self.canvas) or "Failed to export 3D XYZ."
            raise ValueError(message)
        atomic_write_text(path, xyz_block)

    def export_mol(self, path: str, *, selected_only: bool = False) -> None:
        export_model, atom_annotations = self._build_xyz_payload(selected_only=selected_only)
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
            block = model_to_mol_block_for(self.canvas, export_model, atom_annotations=atom_annotations)
            if block is None:
                reason = rdkit_last_error_for(self.canvas)
                if not reason or "not available" in reason.lower():
                    raise ValueError(
                        f"{exc} Install RDKit to expand these abbreviations automatically."
                    ) from exc
                raise ValueError(reason) from exc
        atomic_write_text(path, block)

    def export_xyz_async(self, path: str, *, on_success, on_error, selected_only: bool = False) -> None:
        try:
            export_model, atom_annotations = self._build_xyz_payload(selected_only=selected_only)
        except Exception as exc:
            on_error(str(exc) or "Failed to export 3D XYZ.")
            return
        if not rdkit_is_loaded_for(self.canvas) and not preload_rdkit_for(self.canvas):
            on_error(rdkit_last_error_for(self.canvas) or "RDKit is not available in this environment.")
            return

        from ui.rdkit_async_jobs import export_xyz_in_thread

        export_xyz_in_thread(
            self.canvas,
            rdkit_adapter=rdkit_adapter_for(self.canvas),
            model=export_model,
            atom_annotations=atom_annotations,
            path=path,
            on_success=on_success,
            on_error=on_error,
            rdkit_adapter_factory=new_rdkit_adapter,
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
        from ui.export_plan_logic import points_for_mm

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
            scene_item_state_getter=lambda item: scene_item_state_for(self.canvas, item),
            version=clipboard_selection_version_for(self.canvas),
        )
        if selection_payload is None:
            raise ValueError("Select something to export, or choose Whole canvas.")
        return selection_payload_to_canvas_state(
            selection_payload,
            self.snapshot_state()["settings"],
        )


__all__ = ["CanvasDocumentSessionService"]
