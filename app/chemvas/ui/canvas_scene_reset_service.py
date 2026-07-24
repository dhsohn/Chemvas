from __future__ import annotations

from typing import cast

from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from chemvas.domain.document import MoleculeModel
from chemvas.ui.atom_coords_access import clear_atom_coords_3d_for
from chemvas.ui.canvas_atom_graphics_state import clear_atom_graphics_for
from chemvas.ui.canvas_bond_graphics_state import clear_bond_graphics_for
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_group_state import clear_groups_for
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import set_model_for
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_scene_items_state import clear_scene_item_collections_for
from chemvas.ui.handle_state import set_active_handles_for, set_handle_target_for
from chemvas.ui.insert_mode_logic import clear_insert_session
from chemvas.ui.insert_session_access import (
    apply_insert_session_state_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_outline_state import clear_selection_outlines_for
from chemvas.ui.selection_style_state import selection_style_state_for

_MISSING_ATTRIBUTE = object()


def _add_reset_recovery_note(
    original_error: BaseException,
    recovery_error: BaseException,
) -> None:
    original_error.add_note(
        "Scene reset recovery also failed with "
        f"{type(recovery_error).__name__}: {recovery_error}"
    )


class CanvasSceneResetService:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph = graph_state_for(canvas)
        self.rotation = rotation_state_for(canvas)
        self.insert_state = insert_state_for(canvas)
        self.marks = mark_registry_for(canvas)
        self._empty_status_publication_active = False

    def _scene_and_qt_items(self) -> tuple[object, tuple[object, ...] | None]:
        scene: object | None
        if isinstance(self.canvas, QGraphicsView):
            scene = QGraphicsView.scene(self.canvas)
        else:
            scene_method = getattr(self.canvas, "scene", None)
            if not callable(scene_method):
                raise AttributeError("canvas has no callable scene accessor")
            scene = scene_method()
        if scene is None:
            raise RuntimeError("canvas scene accessor returned no scene")
        qt_items_before_clear = (
            tuple(QGraphicsScene.items(scene))
            if isinstance(scene, QGraphicsScene)
            else None
        )
        return scene, qt_items_before_clear

    def _clear_graphics_scene(
        self,
        scene: object,
        qt_items_before_clear: tuple[object, ...] | None,
        mark_destructive_started,
    ) -> None:
        def clear_scene_root() -> None:
            if qt_items_before_clear is None:
                # A duck scene's clear cannot be probed afterward, so any
                # attempt counts as destruction.
                mark_destructive_started()
            try:
                scene.clear()  # type: ignore[attr-defined]
            except BaseException:
                if qt_items_before_clear is not None and (
                    tuple(QGraphicsScene.items(cast(QGraphicsScene, scene)))
                    != qt_items_before_clear
                ):
                    mark_destructive_started()
                raise
            mark_destructive_started()
            # QGraphicsScene.clear() removes every item, which already drops
            # the selection; duck scenes need the explicit call.
            if qt_items_before_clear is None:
                clear_selection = getattr(scene, "clearSelection", None)
                if callable(clear_selection):
                    clear_selection()

        block_signals = getattr(scene, "blockSignals", _MISSING_ATTRIBUTE)
        if block_signals is _MISSING_ATTRIBUTE:
            clear_scene_root()
            return
        if not callable(block_signals):
            # A sparse duck scene may omit the port entirely, but a present
            # non-callable port is a malformed scene: destruction must never
            # run while change callbacks are live.
            raise TypeError("scene blockSignals is not callable")
        with blocked_scene_signals(scene):
            clear_scene_root()

    def _runtime_reset_steps(self, empty_model: MoleculeModel) -> tuple:
        canvas = self.canvas
        selection_style = selection_style_state_for(canvas)
        selection_info = selection_info_state_for(canvas)

        def clear_selection_runtime() -> None:
            selection_style.selected_items.clear()
            selection_style.suspend_outline = False
            selection_info.signature = None
            selection_info.pending_signature = None
            selection_info.cache = ("", "")
            selection_info.rdkit_warmup_pending = False

        def clear_hover() -> None:
            hover_state = hover_state_for(canvas)
            hover_state.items.clear()
            hover_state.atom_id = None
            hover_state.bond_id = None
            hover_state.style = None

        def clear_insert_runtime() -> None:
            insert_state = self.insert_state
            insert_state.smiles_active = False
            insert_state.smiles_preview_model = None
            insert_state.smiles_preview_items.clear()
            insert_state.smiles_preview_bond_items.clear()
            insert_state.smiles_preview_atom_items.clear()
            insert_state.smiles_preview_center = None
            insert_state.smiles_preview_smiles = None
            insert_state.template_active = False
            insert_state.template_ring_size = None
            insert_state.template_ring_style = None
            insert_state.template_preview_items.clear()
            insert_state.template_preview_lines.clear()
            insert_state.template_preview_dots.clear()

        return (
            clear_selection_runtime,
            lambda: clear_selection_outlines_for(canvas),
            lambda: set_active_handles_for(canvas, []),
            lambda: set_handle_target_for(canvas, None),
            clear_hover,
            lambda: set_model_for(canvas, empty_model),
            self.hit_testing_service.mark_spatial_index_dirty,
            lambda: clear_atom_coords_3d_for(canvas),
            self.rotation.reset_all,
            lambda: clear_atom_graphics_for(canvas),
            self.graph.reset,
            lambda: clear_bond_graphics_for(canvas),
            lambda: clear_scene_item_collections_for(canvas),
            lambda: clear_groups_for(canvas),
            self.marks.clear,
            lambda: clear_template_preview_for(canvas),
            lambda: clear_smiles_preview_for(canvas),
            lambda: apply_insert_session_state_for(canvas, clear_insert_session()),
            clear_insert_runtime,
        )

    def _discard_history_in_place(self) -> None:
        # Emptying the stacks through their live lists keeps list identity
        # for every alias holder and deliberately skips the history change
        # notification: the reset caller publishes the new document itself.
        services = getattr(self.canvas, "services", None)
        history_service = getattr(services, "history_service", None)
        state = getattr(history_service, "state", None)
        if state is None:
            return
        history = getattr(state, "history", None)
        if isinstance(history, list):
            history[:] = []
        redo_stack = getattr(state, "redo_stack", None)
        if isinstance(redo_stack, list):
            redo_stack[:] = []

    def clear_scene(self) -> None:
        """Reset the canvas to a blank document.

        Everything before the scene clear is a pure read, and the clear
        itself is probed: a failure with scene membership intact propagates
        with nothing mutated. Once destruction has started, Qt may have
        already destroyed C++ item wrappers, so recovery converges on an
        empty canvas — every remaining reset step still runs, collected
        failures are attached to the first error as notes — and the empty
        status is published once only after a fully clean reset.
        """

        scene, qt_items_before_clear = self._scene_and_qt_items()
        discard_history = bool(qt_items_before_clear)
        selection_info = selection_info_state_for(self.canvas)
        selection_callback = selection_info.callback
        empty_model = MoleculeModel()

        destructive_started = False

        def mark_destructive_started() -> None:
            nonlocal destructive_started
            destructive_started = True

        # Suppress selection publications while teardown runs; the single
        # empty-status publication happens below, after the canvas is blank.
        selection_info.callback = None
        errors: list[BaseException] = []
        try:
            try:
                self._clear_graphics_scene(
                    scene,
                    qt_items_before_clear,
                    mark_destructive_started,
                )
            except BaseException as error:
                if not destructive_started:
                    raise
                errors.append(error)
                # Converge on an empty scene through the base Qt port so a
                # buggy clear override cannot fail the recovery again.
                if isinstance(scene, QGraphicsScene):
                    try:
                        QGraphicsScene.clear(scene)
                    except BaseException as retry_error:
                        errors.append(retry_error)
            for step in self._runtime_reset_steps(empty_model):
                try:
                    step()
                except BaseException as error:
                    errors.append(error)
            if discard_history:
                try:
                    self._discard_history_in_place()
                except BaseException as error:
                    errors.append(error)
        finally:
            selection_info.callback = selection_callback
        if errors:
            original_error = errors[0]
            for recovery_error in errors[1:]:
                _add_reset_recovery_note(original_error, recovery_error)
            raise original_error

        if not callable(selection_callback) or self._empty_status_publication_active:
            return
        self._empty_status_publication_active = True
        try:
            selection_callback("", "")
        finally:
            self._empty_status_publication_active = False


__all__ = ["CanvasSceneResetService"]
