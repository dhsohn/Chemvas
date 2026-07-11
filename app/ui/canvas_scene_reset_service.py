from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.model import MoleculeModel
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsScene

from ui.atom_coords_access import clear_atom_coords_3d_for
from ui.benzene_preview_access import clear_benzene_preview_for
from ui.canvas_atom_graphics_state import clear_atom_graphics_for
from ui.canvas_bond_graphics_state import clear_bond_graphics_for
from ui.canvas_document_state import snapshot_canvas_document_state
from ui.canvas_graph_state import graph_state_for
from ui.canvas_group_state import clear_groups_for
from ui.canvas_hover_state import (
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_insert_state import insert_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import set_model_for
from ui.canvas_rotation_preview_state import rotation_preview_state_for
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_scene_items_state import clear_scene_item_collections_for
from ui.handle_state import set_active_handles_for, set_handle_target_for
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.insert_mode_logic import clear_insert_session
from ui.insert_session_access import (
    apply_insert_session_state_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)
from ui.scene_signal_blocking import blocked_scene_signals
from ui.selection_info_state import SelectionInfoState, selection_info_state_for
from ui.selection_outline_state import clear_selection_outlines_for
from ui.selection_style_state import SelectionStyleState, selection_style_state_for
from ui.spatial_index_state import mark_spatial_index_dirty_for

_MISSING_ATTRIBUTE = object()


def _capture_optional_attribute(target: object, name: str) -> object:
    """Read an optional port without hiding a live descriptor failure."""
    try:
        return getattr(target, name)
    except AttributeError:
        static_value = inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
        if static_value is not _MISSING_ATTRIBUTE:
            raise
        return _MISSING_ATTRIBUTE


def _capture_optional_callable(
    target: object,
    name: str,
) -> Callable[..., Any] | None:
    value = _capture_optional_attribute(target, name)
    if value is _MISSING_ATTRIBUTE:
        return None
    if not callable(value):
        raise TypeError(f"{type(target).__name__}.{name} is not callable")
    return value


@dataclass(frozen=True, slots=True)
class _GraphicsSceneClearPorts:
    scene: Any
    clear: Callable[..., Any]
    clear_selection: Callable[..., Any] | None
    block_signals: Callable[..., Any] | None
    signals_blocked: Callable[..., Any] | None
    items: Callable[..., Any] | None


class _ResetSnapshotCanvasProxy:
    __slots__ = ("_canvas", "_scene")

    def __init__(self, canvas: object, scene: object) -> None:
        object.__setattr__(self, "_canvas", canvas)
        object.__setattr__(self, "_scene", scene)

    def scene(self) -> object:
        return self._scene

    def __getattr__(self, name: str) -> object:
        return getattr(self._canvas, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._canvas, name, value)


class CanvasSceneResetService:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph = graph_state_for(canvas)
        self.rotation = rotation_state_for(canvas)
        self.rotation_preview = rotation_preview_state_for(canvas)
        self.insert_state = insert_state_for(canvas)
        self.marks = mark_registry_for(canvas)
        self._empty_status_publication_active = False

    def _capture_graphics_scene_clear_ports(self) -> _GraphicsSceneClearPorts:
        scene_method = _capture_optional_callable(self.canvas, "scene")
        if scene_method is None:
            raise AttributeError("canvas has no callable scene accessor")
        scene = scene_method()
        if scene is None:
            raise RuntimeError("canvas scene accessor returned no scene")

        # Capture every port before the first reset mutation.  In particular,
        # a fail-once descriptor must abort cleanly instead of being treated as
        # an absent optional port and then succeeding after state was changed.
        clear_selection = _capture_optional_callable(scene, "clearSelection")
        clear = _capture_optional_callable(scene, "clear")
        block_signals = _capture_optional_callable(scene, "blockSignals")
        signals_blocked = (
            _capture_optional_callable(scene, "signalsBlocked")
            if block_signals is not None
            else None
        )
        if clear is None:
            raise AttributeError("canvas scene has no callable clear port")
        items = _capture_optional_callable(scene, "items")
        if items is None and isinstance(scene, QObject):
            raise AttributeError("canvas scene has no callable items port")
        return _GraphicsSceneClearPorts(
            scene=scene,
            clear=clear,
            clear_selection=clear_selection,
            block_signals=block_signals,
            signals_blocked=signals_blocked,
            items=items,
        )

    def _clear_graphics_scene_without_callbacks(
        self,
        ports: _GraphicsSceneClearPorts | None = None,
    ) -> None:
        ports = ports or self._capture_graphics_scene_clear_ports()
        if ports.block_signals is None:
            if ports.clear_selection is not None:
                ports.clear_selection()
            ports.clear()
            return
        with blocked_scene_signals(
            ports.scene,
            block_signals=ports.block_signals,
            signals_blocked=ports.signals_blocked,
        ):
            if ports.clear_selection is not None:
                ports.clear_selection()
            ports.clear()

    @staticmethod
    def _clear_selection_runtime_state(
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
    ) -> Callable[[str, str], None] | None:
        selection_callback = selection_info.callback
        selection_style.selected_items.clear()
        selection_style.suspend_outline = False
        selection_info.signature = None
        selection_info.pending_signature = None
        selection_info.cache = ("", "")
        selection_info.rdkit_warmup_pending = False
        return selection_callback

    @staticmethod
    def _set_selection_callback_verified(
        selection_info: SelectionInfoState,
        callback: Callable[[str, str], None] | None,
    ) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                selection_info.callback = callback
                if selection_info.callback is not callback:
                    raise RuntimeError(
                        "selection callback setter did not restore identity"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "scene reset could not set the selection callback authority",
            errors,
        )

    def _apply_clear_without_publication(
        self,
        scene_clear_ports: _GraphicsSceneClearPorts,
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
        *,
        empty_model: MoleculeModel | None = None,
        silent_reassert: bool = False,
    ) -> MoleculeModel:
        self._clear_selection_runtime_state(
            selection_style,
            selection_info,
        )
        clear_selection_outlines_for(self.canvas)
        set_active_handles_for(self.canvas, [])
        set_handle_target_for(self.canvas, None)
        # A preview group owns references to graphics from the current model.
        # Clear its registry before scene signals can observe deleted wrappers.
        self.rotation_preview.reset()
        # QGraphicsScene.clear() destroys C++ items before the registries below
        # are reset. Suppress selectionChanged while that destruction is in
        # progress so callbacks cannot dereference a just-deleted bond/atom.
        self._clear_graphics_scene_without_callbacks(scene_clear_ports)
        set_hover_items_for(self.canvas, [])
        set_hover_atom_id_for(self.canvas, None)
        set_hover_bond_id_for(self.canvas, None)
        target_model = empty_model if empty_model is not None else MoleculeModel()
        if empty_model is not None:
            target_model.atoms.clear()
            target_model.bonds.clear()
            target_model.next_atom_id = 0
            target_model.atom_annotations.clear()
        set_model_for(self.canvas, target_model)
        if silent_reassert:
            mark_spatial_index_dirty_for(self.canvas)
        else:
            self.hit_testing_service.mark_spatial_index_dirty()
        clear_atom_coords_3d_for(self.canvas)
        self.rotation.reset_all()
        clear_atom_graphics_for(self.canvas)
        self.graph.reset()
        clear_bond_graphics_for(self.canvas)
        clear_scene_item_collections_for(self.canvas)
        clear_groups_for(self.canvas)
        self.marks.clear()
        if not silent_reassert:
            clear_template_preview_for(self.canvas)
            clear_benzene_preview_for(self.canvas)
            clear_smiles_preview_for(self.canvas)
            apply_insert_session_state_for(self.canvas, clear_insert_session())
        self._clear_insert_runtime_directly()
        return target_model

    def _clear_insert_runtime_directly(self) -> None:
        state = self.insert_state
        state.smiles_active = False
        state.smiles_preview_model = None
        state.smiles_preview_items.clear()
        state.smiles_preview_bond_items.clear()
        state.smiles_preview_atom_items.clear()
        state.smiles_preview_center = None
        state.smiles_preview_smiles = None
        state.template_active = False
        state.template_ring_size = None
        state.template_ring_style = None
        state.template_preview_items.clear()
        state.template_preview_lines.clear()
        state.template_preview_dots.clear()
        state.benzene_preview_items.clear()

    def _verify_clear_authorities(
        self,
        *,
        scene_clear_ports: _GraphicsSceneClearPorts,
        empty_model: MoleculeModel,
        empty_document_state: dict,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        history_snapshot: HistoryStackSnapshot | None,
        history_first: bool = False,
    ) -> None:
        def verify_history() -> None:
            if history_snapshot is not None and not history_snapshot.is_exact():
                raise RuntimeError("scene reset history was re-mutated")

        def verify_document() -> None:
            snapshot_proxy = _ResetSnapshotCanvasProxy(
                self.canvas,
                scene_clear_ports.scene,
            )
            if snapshot_canvas_document_state(snapshot_proxy) != empty_document_state:
                raise RuntimeError("scene reset document state was re-mutated")

        def verify_scene() -> None:
            if scene_clear_ports.items is None:
                return
            scene = scene_clear_ports.scene
            # A Python QGraphicsScene subclass can override ``items`` and return
            # an empty sequence while re-populating another reset authority.
            # Production scenes therefore close on Qt's base implementation.
            current_items = (
                tuple(QGraphicsScene.items(scene))
                if isinstance(scene, QGraphicsScene)
                else tuple(scene_clear_ports.items())
            )
            if current_items:
                raise RuntimeError("scene reset left graphics items behind")

        def verify_model_callback_free() -> None:
            try:
                namespace = object.__getattribute__(self.canvas, "__dict__")
            except BaseException:
                current_model = object.__getattribute__(self.canvas, "model")
            else:
                current_model = (
                    dict.__getitem__(namespace, "model")
                    if isinstance(namespace, dict) and "model" in namespace
                    else object.__getattribute__(self.canvas, "model")
                )
            if current_model is not empty_model:
                raise RuntimeError("scene reset model identity was re-mutated")

        def verify_callback_identity() -> None:
            current_callback = object.__getattribute__(selection_info, "callback")
            if current_callback is not selection_callback:
                raise RuntimeError("scene reset changed selection callback identity")

        if not history_first:
            verify_model_callback_free()
            verify_scene()
            verify_callback_identity()
            verify_document()
            verify_history()
            return

        # Reverse the independent authorities after the forward sweep.  History
        # list iterators/config getters are observer-controlled and may return
        # exact values while re-mutating the just-cleared canvas.  Run them
        # first, then close on the document and callback-free Qt/model roots;
        # another history read must not be the final operation.
        verify_history()
        verify_document()
        verify_callback_identity()
        verify_scene()
        verify_model_callback_free()

    def clear_scene(self) -> None:
        # Finish every fallible capture before the first reset mutation.
        scene_clear_ports = self._capture_graphics_scene_clear_ports()
        selection_style = selection_style_state_for(self.canvas)
        selection_info = selection_info_state_for(self.canvas)
        selection_callback = selection_info.callback
        services = getattr(self.canvas, "services", None)
        history_snapshot = HistoryStackSnapshot.capture(
            getattr(services, "history_service", None)
        )

        self._set_selection_callback_verified(selection_info, None)
        try:
            empty_model = self._apply_clear_without_publication(
                scene_clear_ports,
                selection_style,
                selection_info,
            )
            snapshot_proxy = _ResetSnapshotCanvasProxy(
                self.canvas,
                scene_clear_ports.scene,
            )
            empty_document_state = snapshot_canvas_document_state(snapshot_proxy)
        except BaseException:
            self._set_selection_callback_verified(
                selection_info,
                selection_callback,
            )
            raise
        self._set_selection_callback_verified(
            selection_info,
            selection_callback,
        )

        publication_error: BaseException | None = None
        should_publish = callable(selection_callback) and not getattr(
            self,
            "_empty_status_publication_active",
            False,
        )
        if should_publish:
            self._empty_status_publication_active = True
            try:
                assert selection_callback is not None
                selection_callback("", "")
            except BaseException as error:
                publication_error = error
            finally:
                self._empty_status_publication_active = False
        else:
            self._verify_clear_authorities(
                scene_clear_ports=scene_clear_ports,
                empty_model=empty_model,
                empty_document_state=empty_document_state,
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
            )
            self._verify_clear_authorities(
                scene_clear_ports=scene_clear_ports,
                empty_model=empty_model,
                empty_document_state=empty_document_state,
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
                history_first=True,
            )
            return

        reassert_errors: list[BaseException] = []
        for attempt in range(2):
            diagnostic = RuntimeError(
                "scene reset post-publication reassertion failed"
            )
            try:
                self._set_selection_callback_verified(selection_info, None)
                if attempt == 0:
                    self._apply_clear_without_publication(
                        scene_clear_ports,
                        selection_style,
                        selection_info,
                        empty_model=empty_model,
                        silent_reassert=True,
                    )
                if history_snapshot is not None and not history_snapshot.restore_silently(
                    diagnostic,
                    phase="scene reset",
                ):
                    raise diagnostic
                if attempt == 1:
                    self._apply_clear_without_publication(
                        scene_clear_ports,
                        selection_style,
                        selection_info,
                        empty_model=empty_model,
                        silent_reassert=True,
                    )
                self._set_selection_callback_verified(
                    selection_info,
                    selection_callback,
                )
                self._verify_clear_authorities(
                    scene_clear_ports=scene_clear_ports,
                    empty_model=empty_model,
                    empty_document_state=empty_document_state,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    history_first=True,
                )
            except BaseException as error:
                reassert_errors.append(error)
                continue
            break
        else:
            if publication_error is None:
                raise BaseExceptionGroup(
                    "scene reset remained non-authoritative",
                    reassert_errors,
                )
            for reassert_error in reassert_errors:
                try:
                    publication_error.add_note(
                        "Scene reset recovery also failed: "
                        f"{type(reassert_error).__name__}: {reassert_error}"
                    )
                except BaseException:
                    pass

        if publication_error is not None:
            raise publication_error


__all__ = ["CanvasSceneResetService"]
